import json
import logging
from typing import Any, Callable, Dict, List, Optional, Sequence

from normalizers.servernormalizer import ServerNormalizer
from utils.common_rest import safe_exception_message
from utils.response_validation import validate_collection_response

logger = logging.getLogger(__name__)


class ServerCollector:
    PAGE_SIZE = 100
    MAX_PAGES = 10_000

    def __init__(self, api_factory: Any):
        self.api_factory = api_factory
        self.normalizer = ServerNormalizer()
        self.last_errors: List[Dict[str, Any]] = []

    def collect(self) -> List[Dict[str, Any]]:
        logger.info("서버 데이터 수집을 시작합니다.")
        self.last_errors = []

        try:
            raw_data = self.collect_raw()
            server_list = self.normalizer.normalize(raw_data)

            logger.info("서버 데이터 수집이 완료되었습니다: %s대", len(server_list))
            return server_list

        except Exception as exc:
            logger.error(
                "서버 데이터 수집 중 오류가 발생했습니다: %s",
                safe_exception_message(exc),
            )
            self._record_error(
                stage="collect",
                api="vserver",
                exc=exc,
            )
            return []

    def collect_raw(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "servers": self._get_all_servers(),
            "nics": self._get_all_nics(),
            "storages": self._get_all_storages(),
        }

    def _get_all_servers(self) -> List[Dict[str, Any]]:
        vserver_api = self.api_factory.get("vserver")
        return self._collect_paginated(
            fetch_page=lambda page_no: vserver_api.get_server_instance_list(
                page_no=page_no,
                page_size=self.PAGE_SIZE,
            ),
            extract_items=self._extract_servers,
            identity_fields=("serverInstanceNo",),
            target_type="server",
            api_name="get_server_instance_list",
        )

    def _get_all_nics(self) -> List[Dict[str, Any]]:
        vserver_api = self.api_factory.get("vserver")
        return self._collect_paginated(
            fetch_page=lambda page_no: (
                vserver_api.get_network_interface_instance_list(
                    page_no=page_no,
                    page_size=self.PAGE_SIZE,
                )
            ),
            extract_items=self._extract_nics,
            identity_fields=("networkInterfaceNo",),
            target_type="network_interface",
            api_name="get_network_interface_instance_list",
        )

    def _get_all_storages(self) -> List[Dict[str, Any]]:
        vserver_api = self.api_factory.get("vserver")
        return self._collect_paginated(
            fetch_page=lambda page_no: (
                vserver_api.get_block_storage_instance_list(
                    page_no=page_no,
                    page_size=self.PAGE_SIZE,
                )
            ),
            extract_items=self._extract_storages,
            identity_fields=("blockStorageInstanceNo",),
            target_type="block_storage",
            api_name="get_block_storage_instance_list",
        )

    def _extract_servers(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        validate_collection_response(
            response,
            expected_keys=("getServerInstanceListResponse",),
            api_name="get_server_instance_list",
        )
        if not isinstance(response, dict):
            return []

        container = response.get("getServerInstanceListResponse", {})
        items = (
            container.get("serverInstanceList", [])
            if isinstance(container, dict)
            else []
        )
        return self._dict_items(items)

    def _extract_nics(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        validate_collection_response(
            response,
            expected_keys=("getNetworkInterfaceListResponse",),
            api_name="get_network_interface_instance_list",
        )
        if not isinstance(response, dict):
            return []

        container = response.get("getNetworkInterfaceListResponse", {})
        items = (
            container.get("networkInterfaceList", [])
            if isinstance(container, dict)
            else []
        )
        return self._dict_items(items)

    def _extract_storages(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        validate_collection_response(
            response,
            expected_keys=("getBlockStorageInstanceListResponse",),
            api_name="get_block_storage_instance_list",
        )
        if not isinstance(response, dict):
            return []

        container = response.get("getBlockStorageInstanceListResponse", {})
        items = (
            container.get("blockStorageInstanceList", [])
            if isinstance(container, dict)
            else []
        )
        return self._dict_items(items)

    def _collect_paginated(
        self,
        fetch_page: Callable[[int], Any],
        extract_items: Callable[[Any], List[Dict[str, Any]]],
        identity_fields: Sequence[str],
        target_type: str,
        api_name: str,
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        seen_identities = set()
        previous_fingerprint = None

        for page_no in range(1, self.MAX_PAGES + 1):
            try:
                response = fetch_page(page_no)
            except Exception as exc:
                self._record_error(
                    stage="pagination",
                    api=api_name,
                    exc=exc,
                    target_type=target_type,
                    page_no=page_no,
                )
                break

            try:
                items = extract_items(response)
            except Exception as exc:
                self._record_error(
                    stage="response",
                    api=api_name,
                    exc=exc,
                    target_type=target_type,
                    page_no=page_no,
                )
                break
            fingerprint = tuple(
                self._item_identity(item, identity_fields)
                for item in items
            )

            if items and fingerprint == previous_fingerprint:
                self._record_error(
                    stage="pagination_guard",
                    api=api_name,
                    target_type=target_type,
                    page_no=page_no,
                    message="동일한 페이지가 반복되어 수집을 중단했습니다.",
                )
                break

            previous_fingerprint = fingerprint
            added_count = 0

            for item in items:
                identity = self._item_identity(item, identity_fields)

                if identity in seen_identities:
                    continue

                seen_identities.add(identity)
                result.append(item)
                added_count += 1

            if items and added_count == 0:
                self._record_error(
                    stage="pagination_guard",
                    api=api_name,
                    target_type=target_type,
                    page_no=page_no,
                    message="페이지가 진행되지 않아 수집을 중단했습니다.",
                )
                break

            if len(items) < self.PAGE_SIZE:
                break
        else:
            self._record_error(
                stage="pagination_guard",
                api=api_name,
                target_type=target_type,
                page_no=self.MAX_PAGES,
                message=(
                    f"최대 페이지 수({self.MAX_PAGES})에 도달해 "
                    "수집을 중단했습니다."
                ),
            )

        return result

    def _item_identity(
        self,
        item: Dict[str, Any],
        identity_fields: Sequence[str],
    ) -> str:
        for field in identity_fields:
            value = item.get(field)

            if value is not None and str(value).strip():
                return f"{field}:{value}"

        return "row:" + json.dumps(
            item,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

    def _dict_items(self, value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []

        return [item for item in value if isinstance(item, dict)]

    def _record_error(
        self,
        stage: str,
        api: str,
        exc: Optional[Exception] = None,
        target_type: str = "server",
        page_no: Optional[int] = None,
        message: Optional[str] = None,
    ) -> None:
        error = {
            "collector": self.__class__.__name__,
            "stage": stage,
            "target_type": target_type,
            "api": api,
            "message": (
                message
                or (
                    safe_exception_message(exc)
                    if exc
                    else "알 수 없는 오류"
                )
            ),
        }

        if page_no is not None:
            error["page_no"] = page_no

        if exc is not None:
            error["exception_type"] = type(exc).__name__

        self.last_errors.append(error)

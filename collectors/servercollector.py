import logging
from typing import Any, Dict, List

from normalizers.servernormalizer import ServerNormalizer

logger = logging.getLogger(__name__)


class ServerCollector:
    PAGE_SIZE = 100

    def __init__(self, api_factory: Any):
        self.api_factory = api_factory
        self.normalizer = ServerNormalizer()

    def collect(self) -> List[Dict[str, Any]]:
        logger.info("서버 데이터 수집을 시작합니다.")

        try:
            raw_data = self.collect_raw()
            server_list = self.normalizer.normalize(raw_data)

            logger.info("서버 데이터 수집이 완료되었습니다: %s대", len(server_list))
            return server_list

        except Exception:
            logger.exception("서버 데이터 수집 중 오류가 발생했습니다.")
            return []

    def collect_raw(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "servers": self._get_all_servers(),
            "nics": self._get_all_nics(),
            "storages": self._get_all_storages(),
        }

    def _get_all_servers(self) -> List[Dict[str, Any]]:
        vserver_api = self.api_factory.get("vserver")
        all_servers = []
        page_no = 1

        while True:
            response = vserver_api.get_server_instance_list(
                page_no=page_no,
                page_size=self.PAGE_SIZE,
            )

            servers = self._extract_servers(response)
            all_servers.extend(servers)

            if len(servers) < self.PAGE_SIZE:
                break

            page_no += 1

        return all_servers

    def _get_all_nics(self) -> List[Dict[str, Any]]:
        vserver_api = self.api_factory.get("vserver")
        all_nics = []
        page_no = 1

        while True:
            response = vserver_api.get_network_interface_instance_list(
                page_no=page_no,
                page_size=self.PAGE_SIZE,
            )

            nics = self._extract_nics(response)
            all_nics.extend(nics)

            if len(nics) < self.PAGE_SIZE:
                break

            page_no += 1

        return all_nics

    def _get_all_storages(self) -> List[Dict[str, Any]]:
        vserver_api = self.api_factory.get("vserver")
        all_storages = []
        page_no = 1

        while True:
            response = vserver_api.get_block_storage_instance_list(
                page_no=page_no,
                page_size=self.PAGE_SIZE,
            )

            storages = self._extract_storages(response)
            all_storages.extend(storages)

            if len(storages) < self.PAGE_SIZE:
                break

            page_no += 1

        return all_storages

    def _extract_servers(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        return response.get(
            "getServerInstanceListResponse",
            {},
        ).get(
            "serverInstanceList",
            [],
        )

    def _extract_nics(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        return response.get(
            "getNetworkInterfaceListResponse",
            {},
        ).get(
            "networkInterfaceList",
            [],
        )

    def _extract_storages(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        return response.get(
            "getBlockStorageInstanceListResponse",
            {},
        ).get(
            "blockStorageInstanceList",
            [],
        )
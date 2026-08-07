"""Collect a representative, allowlisted infrastructure inventory."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import requests

from normalizers.infrastructurenormalizer import InfrastructureNormalizer
from utils.response_validation import validate_collection_response


logger = logging.getLogger(__name__)


class InfrastructureCollector:
    PAGE_SIZE = 100
    MAX_PAGES = 10_000
    WARNING_HTTP_STATUSES = frozenset({401, 403, 404, 405, 501})

    def __init__(self, api_factory: Any):
        self.api_factory = api_factory
        self.normalizer = InfrastructureNormalizer()
        self.last_errors: List[Dict[str, Any]] = []
        self.last_warnings: List[Dict[str, Any]] = []
        credentials = getattr(api_factory, "credentials", None)
        region = getattr(credentials, "region", None)
        self.region_code = (
            region.strip().upper()
            if isinstance(region, str) and region.strip()
            else None
        )

    def collect(
        self,
        servers: list,
        server_raw_data: Optional[dict] = None,
    ) -> List[Dict[str, Any]]:
        """Collect only billable/operational infrastructure resources.

        Server inventory is supplied by ``ServerCollector``. When its raw
        block-storage response is supplied, it is reused so the VServer API is
        not called twice during one report run.
        """

        logger.info("대표 인프라 인벤토리 수집을 시작합니다.")
        self.last_errors = []
        self.last_warnings = []
        resources: List[Dict[str, Any]] = []

        self._extend_normalized(
            resources,
            target_type="server",
            api="server_collector",
            normalize=lambda: self.normalizer.normalize_servers(servers),
        )

        storages = self._server_storages(servers, server_raw_data)
        if storages is None:
            storages = self._collect_paged_service(
                api_key="vserver",
                method_name="get_block_storage_instance_list",
                response_key="getBlockStorageInstanceListResponse",
                list_key="blockStorageInstanceList",
                identity_fields=("blockStorageInstanceNo",),
                target_type="block_storage",
                request_kwargs=self._region_kwargs(),
            )
        self._extend_normalized(
            resources,
            target_type="block_storage",
            api="get_block_storage_instance_list",
            normalize=lambda: self.normalizer.normalize_block_storages(
                storages or []
            ),
        )

        load_balancers = self._collect_paged_service(
            api_key="loadbalancer",
            method_name="get_load_balancer_instance_list",
            response_key="getLoadBalancerInstanceListResponse",
            list_key="loadBalancerInstanceList",
            identity_fields=("loadBalancerInstanceNo",),
            target_type="load_balancer",
            request_kwargs=self._region_kwargs(),
        )
        self._extend_normalized(
            resources,
            target_type="load_balancer",
            api="get_load_balancer_instance_list",
            normalize=lambda: self.normalizer.normalize_load_balancers(
                load_balancers
            ),
        )

        nas_volumes = self._collect_paged_service(
            api_key="vnas",
            method_name="get_nas_volume_instance_list",
            response_key="getNasVolumeInstanceListResponse",
            list_key="nasVolumeInstanceList",
            identity_fields=("nasVolumeInstanceNo",),
            target_type="nas",
            request_kwargs=self._region_kwargs(),
        )
        self._extend_normalized(
            resources,
            target_type="nas",
            api="get_nas_volume_instance_list",
            normalize=lambda: self.normalizer.normalize_nas(nas_volumes),
        )

        cdb_specs = (
            (
                "MYSQL",
                "get_cloud_mysql_instance_list",
                "getCloudMysqlInstanceListResponse",
                "cloudMysqlInstanceList",
                "cloudMysqlInstanceNo",
            ),
            (
                "POSTGRESQL",
                "get_cloud_postgresql_instance_list",
                "getCloudPostgresqlInstanceListResponse",
                "cloudPostgresqlInstanceList",
                "cloudPostgresqlInstanceNo",
            ),
            (
                "MSSQL",
                "get_cloud_mssql_instance_list",
                "getCloudMssqlInstanceListResponse",
                "cloudMssqlInstanceList",
                "cloudMssqlInstanceNo",
            ),
            (
                "MONGODB",
                "get_cloud_mongodb_instance_list",
                "getCloudMongoDbInstanceListResponse",
                "cloudMongoDbInstanceList",
                "cloudMongoDbInstanceNo",
            ),
            (
                "CACHE",
                "get_cloud_cache_instance_list",
                "getCloudCacheInstanceListResponse",
                "cloudCacheInstanceList",
                "cloudCacheInstanceNo",
            ),
        )
        for engine, method_name, response_key, list_key, identity_field in cdb_specs:
            instances = self._collect_paged_service(
                api_key="cloud_db",
                method_name=method_name,
                response_key=response_key,
                list_key=list_key,
                identity_fields=(identity_field,),
                target_type=f"cdb_{engine.lower()}",
                page_start=0,
                request_kwargs=self._region_kwargs(),
            )
            self._extend_normalized(
                resources,
                target_type=f"cdb_{engine.lower()}",
                api=method_name,
                normalize=lambda engine=engine, instances=instances: (
                    self.normalizer.normalize_cdb(engine, instances)
                ),
            )

        clusters = self._collect_single_service(
            api_key="kubernetes",
            method_name="get_nks_cluster_list",
            expected_key="clusters",
            list_key="clusters",
            target_type="nks",
        )
        self._extend_normalized(
            resources,
            target_type="nks",
            api="get_nks_cluster_list",
            normalize=lambda: self.normalizer.normalize_nks(clusters),
        )

        cdn_specs = (
            (
                "GLOBAL_CDN",
                "get_global_cdn_instance_list",
                "getGlobalCdnInstanceListResponse",
                "globalCdnInstanceList",
            ),
            (
                "CDN_PLUS",
                "get_cdn_plus_instance_list",
                "getCdnPlusInstanceListResponse",
                "cdnPlusInstanceList",
            ),
        )
        for variant, method_name, response_key, list_key in cdn_specs:
            instances = self._collect_paged_service(
                api_key="cdn",
                method_name=method_name,
                response_key=response_key,
                list_key=list_key,
                identity_fields=("cdnInstanceNo",),
                target_type=variant.lower(),
                page_start=0,
            )
            self._extend_normalized(
                resources,
                target_type=variant.lower(),
                api=method_name,
                normalize=lambda variant=variant, instances=instances: (
                    self.normalizer.normalize_cdn(variant, instances)
                ),
            )

        resource_manager_items = self._collect_resource_manager()
        self._extend_normalized(
            resources,
            target_type="resource_manager",
            api="get_resource_list",
            normalize=lambda: self.normalizer.normalize_resource_manager(
                resource_manager_items
            ),
        )

        result = self.normalizer.finalize(resources)
        logger.info(
            "대표 인프라 인벤토리 수집이 완료되었습니다: %s개 "
            "(오류 %s, 경고 %s)",
            len(result),
            len(self.last_errors),
            len(self.last_warnings),
        )
        return result

    def _server_storages(
        self,
        servers: list,
        server_raw_data: Optional[dict],
    ) -> Optional[List[Dict[str, Any]]]:
        if isinstance(server_raw_data, Mapping) and "storages" in server_raw_data:
            return self._dict_items(server_raw_data.get("storages"))

        nested_storages: List[Dict[str, Any]] = []
        has_nested_storage_field = False
        for server in self._dict_items(servers):
            if "storages" not in server:
                continue
            has_nested_storage_field = True
            nested_storages.extend(self._dict_items(server.get("storages")))

        if has_nested_storage_field:
            return nested_storages
        return None

    def _collect_paged_service(
        self,
        *,
        api_key: str,
        method_name: str,
        response_key: str,
        list_key: str,
        identity_fields: Sequence[str],
        target_type: str,
        page_start: int = 1,
        request_kwargs: Optional[Mapping[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        try:
            api = self.api_factory.get(api_key)
            method = getattr(api, method_name)
        except Exception as exc:
            self._record_issue(
                stage="initialization",
                api=method_name,
                target_type=target_type,
                exc=exc,
            )
            return []

        result: List[Dict[str, Any]] = []
        seen = set()
        previous_fingerprint = None

        for page_no in range(page_start, page_start + self.MAX_PAGES):
            try:
                call_kwargs = dict(request_kwargs or {})
                call_kwargs.update({
                    "page_no": page_no,
                    "page_size": self.PAGE_SIZE,
                })
                response = method(**call_kwargs)
                items, total_rows = self._extract_wrapped_items(
                    response,
                    response_key=response_key,
                    list_key=list_key,
                    api_name=method_name,
                )
            except Exception as exc:
                self._record_issue(
                    stage="collection",
                    api=method_name,
                    target_type=target_type,
                    page_no=page_no,
                    exc=exc,
                )
                break

            fingerprint = tuple(
                self._item_identity(item, identity_fields)
                for item in items
            )
            if items and fingerprint == previous_fingerprint:
                self._record_warning(
                    stage="pagination_guard",
                    api=method_name,
                    target_type=target_type,
                    page_no=page_no,
                    message="동일한 페이지가 반복되어 수집을 중단했습니다.",
                )
                break
            previous_fingerprint = fingerprint

            added = 0
            for item in items:
                identity = self._item_identity(item, identity_fields)
                if identity in seen:
                    continue
                seen.add(identity)
                result.append(item)
                added += 1

            if items and added == 0:
                self._record_warning(
                    stage="pagination_guard",
                    api=method_name,
                    target_type=target_type,
                    page_no=page_no,
                    message="페이지가 진행되지 않아 수집을 중단했습니다.",
                )
                break
            if total_rows is not None and len(result) >= total_rows:
                break
            if len(items) < self.PAGE_SIZE:
                break
        else:
            self._record_warning(
                stage="pagination_guard",
                api=method_name,
                target_type=target_type,
                page_no=page_start + self.MAX_PAGES - 1,
                message="최대 페이지 수에 도달해 수집을 중단했습니다.",
            )

        return result

    def _region_kwargs(self) -> Dict[str, str]:
        return {"region_code": self.region_code} if self.region_code else {}

    def _collect_single_service(
        self,
        *,
        api_key: str,
        method_name: str,
        expected_key: str,
        list_key: str,
        target_type: str,
    ) -> List[Dict[str, Any]]:
        try:
            api = self.api_factory.get(api_key)
            method = getattr(api, method_name)
            response = method()
            validate_collection_response(
                response,
                expected_keys=(expected_key,),
                api_name=method_name,
            )
            if not isinstance(response, Mapping):
                return []
            return self._dict_items(response.get(list_key))
        except Exception as exc:
            self._record_issue(
                stage="collection",
                api=method_name,
                target_type=target_type,
                exc=exc,
            )
            return []

    def _collect_resource_manager(self) -> List[Dict[str, Any]]:
        method_name = "get_resource_list"
        try:
            api = self.api_factory.get("resource_manager")
            method = getattr(api, method_name)
        except Exception as exc:
            self._record_issue(
                stage="initialization",
                api=method_name,
                target_type="resource_manager",
                exc=exc,
            )
            return []

        result: List[Dict[str, Any]] = []
        seen = set()
        previous_fingerprint = None

        for page_no in range(self.MAX_PAGES):
            try:
                response = method(
                    page=page_no,
                    size=self.PAGE_SIZE,
                    **self._region_kwargs(),
                )
                validate_collection_response(
                    response,
                    expected_keys=("items",),
                    api_name=method_name,
                )
                if not isinstance(response, Mapping):
                    break
                items = self._dict_items(response.get("items"))
            except Exception as exc:
                self._record_issue(
                    stage="collection",
                    api=method_name,
                    target_type="resource_manager",
                    page_no=page_no,
                    exc=exc,
                )
                break

            fingerprint = tuple(
                self._item_identity(item, ("nrn", "resourceId"))
                for item in items
            )
            if items and fingerprint == previous_fingerprint:
                self._record_warning(
                    stage="pagination_guard",
                    api=method_name,
                    target_type="resource_manager",
                    page_no=page_no,
                    message="동일한 페이지가 반복되어 수집을 중단했습니다.",
                )
                break
            previous_fingerprint = fingerprint

            for item in items:
                identity = self._item_identity(item, ("nrn", "resourceId"))
                if identity in seen:
                    continue
                seen.add(identity)
                result.append(item)

            has_more = response.get("hasMore")
            if has_more not in (True, "true", "TRUE", 1, "1"):
                break
            if not items:
                break
        else:
            self._record_warning(
                stage="pagination_guard",
                api=method_name,
                target_type="resource_manager",
                page_no=self.MAX_PAGES - 1,
                message="최대 페이지 수에 도달해 수집을 중단했습니다.",
            )

        return result

    def _extract_wrapped_items(
        self,
        response: Any,
        *,
        response_key: str,
        list_key: str,
        api_name: str,
    ) -> tuple[List[Dict[str, Any]], Optional[int]]:
        validate_collection_response(
            response,
            expected_keys=(response_key,),
            api_name=api_name,
        )
        if not isinstance(response, Mapping):
            return [], None
        container = response.get(response_key)
        if not isinstance(container, Mapping):
            return [], None
        items = self._dict_items(container.get(list_key))
        total_rows = container.get("totalRows")
        try:
            normalized_total = int(total_rows) if total_rows is not None else None
        except (TypeError, ValueError):
            normalized_total = None
        return items, normalized_total

    def _extend_normalized(
        self,
        resources: List[Dict[str, Any]],
        *,
        target_type: str,
        api: str,
        normalize: Callable[[], List[Dict[str, Any]]],
    ) -> None:
        try:
            resources.extend(normalize())
        except Exception as exc:
            self._record_issue(
                stage="normalization",
                api=api,
                target_type=target_type,
                exc=exc,
            )

    def _record_issue(
        self,
        *,
        stage: str,
        api: str,
        target_type: str,
        exc: Exception,
        page_no: Optional[int] = None,
    ) -> None:
        status_code = None
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            status_code = exc.response.status_code

        is_warning = (
            status_code in self.WARNING_HTTP_STATUSES
            or isinstance(exc, (AttributeError, KeyError, NotImplementedError))
        )
        message = (
            "권한이 없거나 현재 환경에서 지원되지 않는 API입니다."
            if is_warning
            else "API 응답을 수집하거나 처리하지 못했습니다."
        )
        issue = {
            "collector": self.__class__.__name__,
            "stage": stage,
            "target_type": target_type,
            "api": api,
            "message": message,
            "exception_type": type(exc).__name__,
        }
        if page_no is not None:
            issue["page_no"] = page_no
        if status_code is not None:
            issue["status_code"] = status_code
            provider_code = self._provider_error_code(exc.response)
            if provider_code:
                issue["error_code"] = provider_code

        if is_warning:
            issue["severity"] = "warning"
            self.last_warnings.append(issue)
        else:
            self.last_errors.append(issue)

    def _record_warning(
        self,
        *,
        stage: str,
        api: str,
        target_type: str,
        message: str,
        page_no: Optional[int] = None,
    ) -> None:
        warning = {
            "collector": self.__class__.__name__,
            "stage": stage,
            "target_type": target_type,
            "api": api,
            "message": message,
            "severity": "warning",
        }
        if page_no is not None:
            warning["page_no"] = page_no
        self.last_warnings.append(warning)

    @staticmethod
    def _provider_error_code(response: requests.Response) -> Optional[str]:
        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, Mapping):
            return None
        error = payload.get("error")
        if isinstance(error, Mapping):
            value = error.get("errorCode") or error.get("code")
            if value is not None:
                return str(value)[:100]
        value = payload.get("errorCode") or payload.get("code")
        return str(value)[:100] if value is not None else None

    @staticmethod
    def _dict_items(value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [dict(item) for item in value if isinstance(item, Mapping)]

    @staticmethod
    def _item_identity(
        item: Mapping[str, Any],
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


__all__ = ["InfrastructureCollector"]

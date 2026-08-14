"""Collect a representative, allowlisted infrastructure inventory."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import requests

from normalizers.infrastructurenormalizer import InfrastructureNormalizer
from utils.response_validation import validate_collection_response


logger = logging.getLogger(__name__)


class InfrastructureCollector:
    PAGE_SIZE = 100
    MAX_PAGES = 10_000
    WARNING_HTTP_STATUSES = frozenset({401, 403, 404, 405, 501})
    _SUB_ACCOUNT_PERMISSION_CODE = "X00004"
    _REQUIRED_ACTION_PATTERN = re.compile(
        r"\b(?:View|Change)/[A-Za-z][A-Za-z0-9_-]{0,99}\b"
    )
    LEGACY_DEFAULT_CATEGORIES = frozenset({
        "SERVER",
        "LOAD_BALANCER",
        "BLOCK_STORAGE",
        "OBJECT_STORAGE",
        "NAS",
        "CLOUD_DB",
        "KUBERNETES",
    })
    RESOURCE_MANAGER_ONLY_CATEGORIES = frozenset({
        "OBJECT_STORAGE",
        "VIRTUAL_PRIVATE_GATEWAY",
        "AUTO_SCALING",
        "GLOBAL_EDGE",
        "GLOBAL_TRAFFIC_MANAGER",
        "API_GATEWAY",
        "BACKUP",
        "ARCHIVE_STORAGE",
        "SEARCH_ENGINE",
        "DATA_STREAMING",
        "CLOUD_HADOOP",
        "DATA_STREAM",
        "CLOUD_FUNCTIONS",
        "SECURITY_SERVICE",
        "IPSEC_VPN",
        "CLOUD_CONNECT",
    })

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
        categories: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """과금·운영 대상 인프라만 수집한다.

        서버 인벤토리는 ``ServerCollector``의 결과를 사용한다. 원본 블록
        스토리지 응답이 있으면 한 번의 보고서 실행에서 VServer API를 중복
        호출하지 않도록 그대로 재사용한다.
        """

        logger.info("대표 인프라 인벤토리 수집을 시작합니다.")
        self.last_errors = []
        self.last_warnings = []
        selected_categories = self._normalize_categories(categories)
        if selected_categories == frozenset():
            return []
        resources: List[Dict[str, Any]] = []

        self._collect_compute_resources(
            resources,
            servers=servers,
            server_raw_data=server_raw_data,
            selected_categories=selected_categories,
        )
        self._collect_network_resources(resources, selected_categories)
        self._collect_platform_resources(resources, selected_categories)
        self._collect_data_resources(resources, selected_categories)
        resources = self._enrich_resource_manager_resources(
            resources,
            selected_categories,
        )

        result = self.normalizer.finalize(resources)
        if selected_categories is not None:
            result = [
                resource
                for resource in result
                if (
                    resource.get("category") in selected_categories
                    or (
                        resource.get("category") == "TARGET_GROUP"
                        and "LOAD_BALANCER" in selected_categories
                    )
                )
            ]
        logger.info(
            "대표 인프라 인벤토리 수집이 완료되었습니다: %s개 "
            "(오류 %s, 경고 %s)",
            len(result),
            len(self.last_errors),
            len(self.last_warnings),
        )
        return result

    def _collect_compute_resources(
        self,
        resources: List[Dict[str, Any]],
        *,
        servers: list,
        server_raw_data: Optional[dict],
        selected_categories: Optional[frozenset[str]],
    ) -> None:
        """서버와 블록 스토리지를 기존 원본 응답을 우선 사용해 수집한다."""

        # ServerCollector의 원본 응답이 있으면 같은 VServer API를 다시 호출하지 않는다.
        network_interfaces: Optional[List[Dict[str, Any]]] = []
        if self._category_enabled(selected_categories, "SERVER"):
            network_interfaces = self._server_network_interfaces(
                servers,
                server_raw_data,
            )
            if network_interfaces is None:
                network_interfaces = self._collect_paged_service(
                    api_key="vserver",
                    method_name="get_network_interface_instance_list",
                    response_key="getNetworkInterfaceListResponse",
                    list_key="networkInterfaceList",
                    identity_fields=("networkInterfaceNo",),
                    target_type="network_interface",
                    optional=True,
                    request_kwargs=self._region_kwargs(),
                )

        if self._category_enabled(selected_categories, "SERVER"):
            self._extend_normalized(
                resources,
                target_type="server",
                api="server_collector",
                normalize=lambda: self.normalizer.normalize_servers(
                    servers,
                    network_interfaces,
                ),
            )

        if self._category_enabled(selected_categories, "BLOCK_STORAGE"):
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

    def _collect_network_resources(
        self,
        resources: List[Dict[str, Any]],
        selected_categories: Optional[frozenset[str]],
    ) -> None:
        """VPC와 선택된 네트워크 구성 자원을 기존 호출 순서대로 수집한다."""

        # Subnet API만 공개 인수가 page이고 실제 요청 키는 pageNo로 변환된다.
        # Public IP 계열은 기존 공급자 페이지 기준에 맞춰 0부터 시작한다.
        if self._category_enabled(selected_categories, "VPC"):
            vpcs = self._collect_wrapped_service(
                api_key="vpc",
                method_name="get_vpc_list",
                response_key="getVpcListResponse",
                list_key="vpcList",
                target_type="vpc",
                request_kwargs=self._region_kwargs(),
            )
            self._extend_normalized(
                resources,
                target_type="vpc",
                api="get_vpc_list",
                normalize=lambda: self.normalizer.normalize_vpcs(vpcs),
            )

        if self._category_enabled(selected_categories, "SUBNET"):
            subnets = self._collect_paged_service(
                api_key="vpc",
                method_name="get_subnet_list",
                response_key="getSubnetListResponse",
                list_key="subnetList",
                identity_fields=("subnetNo",),
                target_type="subnet",
                page_parameter="page",
                request_kwargs=self._region_kwargs(),
            )
            self._extend_normalized(
                resources,
                target_type="subnet",
                api="get_subnet_list",
                normalize=lambda: self.normalizer.normalize_subnets(subnets),
            )

        if self._category_enabled(selected_categories, "ROUTE_TABLE"):
            route_tables = self._collect_paged_service(
                api_key="vpc",
                method_name="get_route_table_list",
                response_key="getRouteTableListResponse",
                list_key="routeTableList",
                identity_fields=("routeTableNo",),
                target_type="route_table",
                request_kwargs=self._region_kwargs(),
            )
            subnets_by_table = self._collect_child_lists(
                route_tables,
                api_key="vpc",
                method_name="get_route_table_subnet_list",
                parent_id_field="routeTableNo",
                parent_parameter="route_table_no",
                response_key="getRouteTableSubnetListResponse",
                list_key="subnetList",
                target_type="route_table_subnet",
            )
            routes_by_table = self._collect_child_lists(
                route_tables,
                api_key="vpc",
                method_name="get_route_list",
                parent_id_field="routeTableNo",
                parent_parameter="route_table_no",
                response_key="getRouteListResponse",
                list_key="routeList",
                target_type="route_table_route",
                parent_request_kwargs=lambda item: {
                    "vpc_no": item.get("vpcNo")
                },
                required_parent_fields=("vpcNo",),
            )
            self._extend_normalized(
                resources,
                target_type="route_table",
                api="get_route_table_list",
                normalize=lambda: self.normalizer.normalize_route_tables(
                    route_tables,
                    subnets_by_table,
                    routes_by_table,
                ),
            )

        if self._category_enabled(
            selected_categories,
            "ACCESS_CONTROL_GROUP",
        ):
            access_control_groups = self._collect_paged_service(
                api_key="vserver",
                method_name="get_access_control_group_list",
                response_key="getAccessControlGroupListResponse",
                list_key="accessControlGroupList",
                identity_fields=("accessControlGroupNo",),
                target_type="access_control_group",
                request_kwargs=self._region_kwargs(),
            )
            rules_by_group = self._collect_child_lists(
                access_control_groups,
                api_key="vserver",
                method_name="get_access_control_group_rule_list",
                parent_id_field="accessControlGroupNo",
                parent_parameter="access_control_group_no",
                response_key="getAccessControlGroupRuleListResponse",
                list_key="accessControlGroupRuleList",
                target_type="access_control_group_rule",
            )
            self._extend_normalized(
                resources,
                target_type="access_control_group",
                api="get_access_control_group_list",
                normalize=lambda: self.normalizer.normalize_access_control_groups(
                    access_control_groups,
                    rules_by_group,
                ),
            )

        if self._category_enabled(selected_categories, "NETWORK_ACL"):
            network_acls = self._collect_paged_service(
                api_key="vpc",
                method_name="get_network_acl_list",
                response_key="getNetworkAclListResponse",
                list_key="networkAclList",
                identity_fields=("networkAclNo",),
                target_type="network_acl",
                request_kwargs=self._region_kwargs(),
            )
            rules_by_acl = self._collect_child_lists(
                network_acls,
                api_key="vpc",
                method_name="get_network_acl_rule_list",
                parent_id_field="networkAclNo",
                parent_parameter="network_acl_no",
                response_key="getNetworkAclRuleListResponse",
                list_key="networkAclRuleList",
                target_type="network_acl_rule",
            )
            self._extend_normalized(
                resources,
                target_type="network_acl",
                api="get_network_acl_list",
                normalize=lambda: self.normalizer.normalize_network_acls(
                    network_acls,
                    rules_by_acl,
                ),
            )

        if self._category_enabled(selected_categories, "NAT_GATEWAY"):
            nat_gateways = self._collect_paged_service(
                api_key="vpc",
                method_name="get_nat_gateway_instance_list",
                response_key="getNatGatewayInstanceListResponse",
                list_key="natGatewayInstanceList",
                identity_fields=("natGatewayInstanceNo",),
                target_type="nat_gateway",
                request_kwargs=self._region_kwargs(),
            )
            self._extend_normalized(
                resources,
                target_type="nat_gateway",
                api="get_nat_gateway_instance_list",
                normalize=lambda: self.normalizer.normalize_nat_gateways(
                    nat_gateways
                ),
            )

        if self._category_enabled(selected_categories, "VPC_PEERING"):
            peerings = self._collect_paged_service(
                api_key="vpc",
                method_name="get_vpc_peering_instance_list",
                response_key="getVpcPeeringInstanceListResponse",
                list_key="vpcPeeringInstanceList",
                identity_fields=("vpcPeeringInstanceNo",),
                target_type="vpc_peering",
                request_kwargs=self._region_kwargs(),
            )
            self._extend_normalized(
                resources,
                target_type="vpc_peering",
                api="get_vpc_peering_instance_list",
                normalize=lambda: self.normalizer.normalize_vpc_peerings(
                    peerings
                ),
            )

        if self._category_enabled(selected_categories, "PUBLIC_IP"):
            public_ips = self._collect_paged_service(
                api_key="vserver",
                method_name="get_public_ip_instance_list",
                response_key="getPublicIpInstanceListResponse",
                list_key="publicIpInstanceList",
                identity_fields=("publicIpInstanceNo",),
                target_type="public_ip",
                page_start=0,
                request_kwargs=self._region_kwargs(),
            )
            self._extend_normalized(
                resources,
                target_type="public_ip",
                api="get_public_ip_instance_list",
                normalize=lambda: self.normalizer.normalize_public_ips(
                    public_ips
                ),
            )

    def _collect_platform_resources(
        self,
        resources: List[Dict[str, Any]],
        selected_categories: Optional[frozenset[str]],
    ) -> None:
        """이미지·인증서 등 보조 플랫폼 자원을 수집한다."""

        # 서비스마다 REST 페이지 표식(last/next)과 NCP pageNo 기준이 다르다.
        if self._category_enabled(
            selected_categories,
            "BLOCK_STORAGE_SNAPSHOT",
        ):
            snapshots = self._collect_paged_service(
                api_key="vserver",
                method_name="get_block_storage_snapshot_instance_list",
                response_key="getBlockStorageSnapshotInstanceListResponse",
                list_key="blockStorageSnapshotInstanceList",
                identity_fields=("blockStorageSnapshotInstanceNo",),
                target_type="block_storage_snapshot",
                page_start=0,
                request_kwargs=self._region_kwargs(),
            )
            self._extend_normalized(
                resources,
                target_type="block_storage_snapshot",
                api="get_block_storage_snapshot_instance_list",
                normalize=lambda: self.normalizer.normalize_snapshots(
                    snapshots
                ),
            )

        if self._category_enabled(selected_categories, "SERVER_IMAGE"):
            server_images = self._collect_paged_service(
                api_key="vserver",
                method_name="get_member_server_instance_list",
                response_key="getMemberServerImageInstanceListResponse",
                list_key="memberServerImageInstanceList",
                identity_fields=("memberServerImageInstanceNo",),
                target_type="server_image",
                page_start=0,
                request_kwargs=self._region_kwargs(),
            )
            self._extend_normalized(
                resources,
                target_type="server_image",
                api="get_member_server_instance_list",
                normalize=lambda: self.normalizer.normalize_server_images(
                    server_images
                ),
            )

        if self._category_enabled(selected_categories, "GLOBAL_DNS"):
            domains = self._collect_rest_pages(
                api_key="global_dns",
                method_name="get_domain",
                list_key="content",
                identity_fields=("id",),
                target_type="global_dns",
                page_start=0,
                page_parameter="page",
                size_parameter="size",
                next_field="last",
                next_field_is_last=True,
            )
            self._extend_normalized(
                resources,
                target_type="global_dns",
                api="get_domain",
                normalize=lambda: self.normalizer.normalize_global_dns(
                    domains
                ),
            )

        if self._category_enabled(selected_categories, "CERTIFICATE"):
            certificates = self._collect_plain_list_service(
                api_key="certificate_manager",
                method_name="get_certificate_list",
                list_key="sslCertificateList",
                target_type="certificate",
            )
            self._extend_normalized(
                resources,
                target_type="certificate",
                api="get_certificate_list",
                normalize=lambda: self.normalizer.normalize_certificates(
                    certificates
                ),
            )

    def _collect_data_resources(
        self,
        resources: List[Dict[str, Any]],
        selected_categories: Optional[frozenset[str]],
    ) -> None:
        """로드밸런서, VPC NAS, DB, NKS 자원을 순서대로 수집한다."""

        # Cloud DB 목록 API는 공급자 계약에 따라 0번 페이지부터 조회한다.
        if self._category_enabled(selected_categories, "LOAD_BALANCER"):
            load_balancers = self._collect_paged_service(
                api_key="loadbalancer",
                method_name="get_load_balancer_instance_list",
                response_key="getLoadBalancerInstanceListResponse",
                list_key="loadBalancerInstanceList",
                identity_fields=("loadBalancerInstanceNo",),
                target_type="load_balancer",
                request_kwargs=self._region_kwargs(),
            )
            target_groups: List[Dict[str, Any]] = []
            if load_balancers:
                target_groups = self._collect_paged_service(
                    api_key="loadbalancer",
                    method_name="get_target_group_list",
                    response_key="getTargetGroupListResponse",
                    list_key="targetGroupList",
                    identity_fields=("targetGroupNo",),
                    target_type="target_group",
                    optional=True,
                    request_kwargs=self._region_kwargs(),
                )
            targets_by_group = self._collect_target_lists(target_groups)
            self._extend_normalized(
                resources,
                target_type="load_balancer",
                api="get_load_balancer_instance_list",
                normalize=lambda: self.normalizer.normalize_load_balancers(
                    load_balancers,
                    target_groups,
                    targets_by_group,
                ),
            )

        if self._category_enabled(selected_categories, "NAS"):
            vpc_nas_volumes = self._collect_paged_service(
                api_key="vnas",
                method_name="get_nas_volume_instance_list",
                response_key="getNasVolumeInstanceListResponse",
                list_key="nasVolumeInstanceList",
                identity_fields=("nasVolumeInstanceNo",),
                target_type="nas_vpc",
                optional=True,
                request_kwargs=self._region_kwargs(),
            )
            self._extend_normalized(
                resources,
                target_type="nas_vpc",
                api="get_nas_volume_instance_list",
                normalize=lambda: self.normalizer.normalize_nas(
                    vpc_nas_volumes,
                    platform="VPC",
                ),
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
        if self._category_enabled(selected_categories, "CLOUD_DB"):
            for (
                engine,
                method_name,
                response_key,
                list_key,
                identity_field,
            ) in cdb_specs:
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

        if self._category_enabled(selected_categories, "KUBERNETES"):
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

    def _enrich_resource_manager_resources(
        self,
        resources: List[Dict[str, Any]],
        selected_categories: frozenset[str],
    ) -> List[Dict[str, Any]]:
        """Resource Manager 정보로 생성 시각과 전용 카테고리를 보강한다."""

        # 직접 서비스 API를 원본으로 유지하고 Resource Manager는 한 번만 조회한다.
        # 생성 시각을 보강하며, 직접 수집기가 없는 카테고리에만 인벤토리를 제공한다.
        resource_manager_items = self._collect_resource_manager()
        resources = self.normalizer.enrich_resource_manager_creation_times(
            resources,
            resource_manager_items,
        )

        resource_manager_categories = (
            selected_categories & self.RESOURCE_MANAGER_ONLY_CATEGORIES
        )
        if resource_manager_categories:
            self._extend_normalized(
                resources,
                target_type="resource_manager",
                api="get_resource_list",
                normalize=lambda: [
                    resource
                    for resource in (
                        self.normalizer.normalize_resource_manager(
                            resource_manager_items
                        )
                    )
                    if resource.get("category")
                    in resource_manager_categories
                ],
            )

        return resources


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

    def _server_network_interfaces(
        self,
        servers: list,
        server_raw_data: Optional[dict],
    ) -> Optional[List[Dict[str, Any]]]:
        if isinstance(server_raw_data, Mapping) and "nics" in server_raw_data:
            return self._dict_items(server_raw_data.get("nics"))

        nested_nics: List[Dict[str, Any]] = []
        has_nested_nic_field = False
        for server in self._dict_items(servers):
            for field in ("raw_nics", "nics"):
                if field not in server:
                    continue
                has_nested_nic_field = True
                nested_nics.extend(self._dict_items(server.get(field)))

        if has_nested_nic_field:
            return nested_nics
        return None

    def _collect_wrapped_service(
        self,
        *,
        api_key: str,
        method_name: str,
        response_key: str,
        list_key: str,
        target_type: str,
        optional: bool = False,
        request_kwargs: Optional[Mapping[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        try:
            api = self.api_factory.get(api_key)
            method = getattr(api, method_name)
            response = method(**dict(request_kwargs or {}))
            items, _ = self._extract_wrapped_items(
                response,
                response_key=response_key,
                list_key=list_key,
                api_name=method_name,
            )
            return items
        except Exception as exc:
            self._record_issue(
                stage="collection",
                api=method_name,
                target_type=target_type,
                exc=exc,
                optional=optional,
            )
            return []

    def _collect_plain_list_service(
        self,
        *,
        api_key: str,
        method_name: str,
        list_key: str,
        target_type: str,
    ) -> List[Dict[str, Any]]:
        try:
            api = self.api_factory.get(api_key)
            method = getattr(api, method_name)
            response = method()
            validate_collection_response(
                response,
                expected_keys=(list_key,),
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

    def _collect_rest_pages(
        self,
        *,
        api_key: str,
        method_name: str,
        list_key: str,
        identity_fields: Sequence[str],
        target_type: str,
        page_start: int,
        page_parameter: str,
        size_parameter: str,
        next_field: str,
        next_field_is_last: bool = False,
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
        for page_no in range(page_start, page_start + self.MAX_PAGES):
            try:
                response = method(
                    **{
                        page_parameter: page_no,
                        size_parameter: self.PAGE_SIZE,
                    }
                )
                validate_collection_response(
                    response,
                    expected_keys=(list_key,),
                    api_name=method_name,
                )
                if not isinstance(response, Mapping):
                    break
                items = self._dict_items(response.get(list_key))
            except Exception as exc:
                self._record_issue(
                    stage="collection",
                    api=method_name,
                    target_type=target_type,
                    page_no=page_no,
                    exc=exc,
                )
                break

            for item in items:
                identity = self._item_identity(item, identity_fields)
                if identity in seen:
                    continue
                seen.add(identity)
                result.append(item)

            marker = response.get(next_field)
            if next_field_is_last:
                if marker in (True, "true", "TRUE", 1, "1"):
                    break
            elif marker in (None, "", False, 0, "0"):
                break
            if not items:
                break
        else:
            self._record_warning(
                stage="pagination_guard",
                api=method_name,
                target_type=target_type,
                page_no=page_start + self.MAX_PAGES - 1,
                message="Maximum page count reached; collection stopped.",
            )
        return result

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
        page_parameter: str = "page_no",
        size_parameter: str = "page_size",
        optional: bool = False,
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
                    page_parameter: page_no,
                    size_parameter: self.PAGE_SIZE,
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
                    optional=optional,
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

    def _collect_target_lists(
        self,
        target_groups: Sequence[Mapping[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        result: Dict[str, List[Dict[str, Any]]] = {}
        if not self._dict_items(target_groups):
            return result
        try:
            api = self.api_factory.get("loadbalancer")
            method = getattr(api, "get_target_list")
        except Exception as exc:
            self._record_issue(
                stage="initialization",
                api="get_target_list",
                target_type="target_group",
                exc=exc,
            )
            return result

        for group in self._dict_items(target_groups):
            target_group_no = group.get("targetGroupNo")
            if target_group_no is None or not str(target_group_no).strip():
                continue
            try:
                response = method(
                    target_group_no=str(target_group_no),
                    **self._region_kwargs(),
                )
                items, _ = self._extract_wrapped_items(
                    response,
                    response_key="getTargetListResponse",
                    list_key="targetList",
                    api_name="get_target_list",
                )
                result[str(target_group_no)] = items
            except Exception as exc:
                self._record_issue(
                    stage="collection",
                    api="get_target_list",
                    target_type="target_group",
                    exc=exc,
                    optional=True,
                )
        return result

    def _collect_child_lists(
        self,
        parents: Sequence[Mapping[str, Any]],
        *,
        api_key: str,
        method_name: str,
        parent_id_field: str,
        parent_parameter: str,
        response_key: str,
        list_key: str,
        target_type: str,
        parent_request_kwargs: Optional[
            Callable[[Mapping[str, Any]], Mapping[str, Any]]
        ] = None,
        required_parent_fields: Sequence[str] = (),
    ) -> Dict[str, List[Dict[str, Any]]]:
        """각 상위 자원에 연결된 규칙·연관 목록을 안전하게 수집한다."""

        normalized_parents = self._dict_items(parents)
        if not normalized_parents:
            return {}
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
            return {}

        result: Dict[str, List[Dict[str, Any]]] = {}
        for parent in normalized_parents:
            parent_id = parent.get(parent_id_field)
            if parent_id is None or not str(parent_id).strip():
                continue
            if any(
                parent.get(field) is None
                or not str(parent.get(field)).strip()
                for field in required_parent_fields
            ):
                self._record_warning(
                    stage="collection",
                    api=method_name,
                    target_type=target_type,
                    message=(
                        "상위 자원의 필수 식별 정보가 없어 상세 조회를 "
                        "생략했습니다."
                    ),
                )
                continue

            try:
                request_kwargs: Dict[str, Any] = dict(self._region_kwargs())
                request_kwargs[parent_parameter] = str(parent_id)
                if parent_request_kwargs is not None:
                    request_kwargs.update(
                        dict(parent_request_kwargs(parent))
                    )
                response = method(**request_kwargs)
                items, _ = self._extract_wrapped_items(
                    response,
                    response_key=response_key,
                    list_key=list_key,
                    api_name=method_name,
                )
                result[str(parent_id)] = items
            except Exception as exc:
                self._record_issue(
                    stage="collection",
                    api=method_name,
                    target_type=target_type,
                    exc=exc,
                    optional=True,
                )
        return result

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
        optional: bool = False,
    ) -> None:
        status_code = None
        provider_code = None
        required_actions: tuple[str, ...] = ()
        is_sub_account_permission_error = False
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            status_code = exc.response.status_code
            provider_code = self._provider_error_code(exc.response)
            required_actions = self._provider_required_actions(exc.response)
            is_sub_account_permission_error = (
                status_code == 400
                and provider_code == self._SUB_ACCOUNT_PERMISSION_CODE
                and self._is_sub_account_permission_response(exc.response)
            )

        is_warning = (
            optional
            or status_code in self.WARNING_HTTP_STATUSES
            or is_sub_account_permission_error
            or isinstance(exc, (AttributeError, KeyError, NotImplementedError))
        )
        if is_sub_account_permission_error:
            message = "Sub Account에 자원 조회 권한이 없습니다."
            if required_actions:
                message += " 필요한 권한: " + ", ".join(required_actions)
        elif is_warning:
            message = "권한이 없거나 현재 환경에서 지원되지 않는 API입니다."
        else:
            message = "API 응답을 수집하거나 처리하지 못했습니다."
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
            if provider_code:
                issue["error_code"] = provider_code
            if required_actions:
                issue["required_actions"] = list(required_actions)

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

    @classmethod
    def _provider_required_actions(
        cls,
        response: requests.Response,
    ) -> tuple[str, ...]:
        """공급자 오류에서 안전한 Sub Account 액션명만 추출한다."""

        error_text = cls._provider_error_text(response)
        if not error_text:
            return ()
        return tuple(dict.fromkeys(cls._REQUIRED_ACTION_PATTERN.findall(error_text)))

    @classmethod
    def _is_sub_account_permission_response(
        cls,
        response: requests.Response,
    ) -> bool:
        """HTTP 400으로 반환되는 NCP Sub Account 권한 오류를 식별한다."""

        error_text = cls._provider_error_text(response)
        if not error_text:
            return False
        normalized_text = error_text.casefold()
        return (
            "sub-account" in normalized_text
            or "sub account" in normalized_text
            or "additional rights" in normalized_text
            or bool(cls._REQUIRED_ACTION_PATTERN.search(error_text))
        )

    @staticmethod
    def _provider_error_text(response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return ""
        if not isinstance(payload, Mapping):
            return ""
        error = payload.get("error")
        sources = (error, payload) if isinstance(error, Mapping) else (payload,)
        values: list[str] = []
        for source in sources:
            for key in ("message", "devMessage", "errorMessage"):
                value = source.get(key)
                if isinstance(value, str) and value:
                    values.append(value[:2_000])
        return " ".join(values)

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

    def _normalize_categories(
        self,
        categories: Optional[Sequence[str]],
    ) -> Optional[frozenset[str]]:
        if categories is None:
            return self.LEGACY_DEFAULT_CATEGORIES
        if isinstance(categories, str):
            categories = [categories]
        result = set()
        for candidate in categories:
            normalized = str(candidate or "").strip().upper()
            category = self.normalizer.CATEGORY_ALIASES.get(normalized)
            if category in self.normalizer.CATEGORY_LABELS:
                result.add(category)
        return frozenset(result)

    @staticmethod
    def _category_enabled(
        selected_categories: Optional[frozenset[str]],
        category: str,
    ) -> bool:
        return selected_categories is None or category in selected_categories


__all__ = ["InfrastructureCollector"]

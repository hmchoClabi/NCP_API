"""수집 API를 NCP Sub Account 조회 권한에 연결한다.

NCP의 일반 오류 응답에는 누락된 Sub Account 액션 전용 필드가 없다.
따라서 공급자 응답이 액션을 명시하지 않은 403은 누락 권한으로 확정하지
않고, 실제 호출 API와 공식 권한표를 대응한 점검 후보만 제공한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Optional


_ACTION_PATTERN = re.compile(
    r"(?:View|Change)/[A-Za-z][A-Za-z0-9_-]{0,99}"
)
_MAX_PROVIDER_ACTIONS = 20
_PERMISSION_ERROR_CODES = frozenset({
    "210",
    "300",
    "X00004",
    "ACCESS_DENIED",
    "PERMISSION_DENIED",
    "SUBACCOUNT_PERMISSION_DENIED",
})
_PERMISSION_MESSAGE_MARKERS = (
    "access denied",
    "additional rights",
    "forbidden",
    "not authorized",
    "permission denied",
    "sub-account",
    "sub account",
    "권한 없음",
    "권한이 없습니다",
    "권한이 필요",
)


@dataclass(frozen=True)
class PermissionHint:
    """공식 Sub Account 권한표에서 확인한 API별 조회 권한."""

    service_name: str
    actions: tuple[str, ...]
    related_actions: tuple[str, ...] = ()
    managed_policy: Optional[str] = None
    basis: str = "official_action_table"
    security_note: Optional[str] = None


def _hint(
    service_name: str,
    *actions: str,
    related_actions: tuple[str, ...] = (),
    managed_policy: Optional[str] = None,
    basis: str = "official_action_table",
    security_note: Optional[str] = None,
) -> PermissionHint:
    return PermissionHint(
        service_name=service_name,
        actions=actions,
        related_actions=related_actions,
        managed_policy=managed_policy,
        basis=basis,
        security_note=security_note,
    )


# 키는 collector가 기록하는 (target_type, api)이며, 값은 NCP 콘솔의
# 서비스별 Sub Account 액션명이다. REST 메서드명과 권한 액션명이 다른
# Detail 계열은 공식 권한표의 대응 액션을 사용한다.
PERMISSION_HINTS: Mapping[tuple[str, str], PermissionHint] = MappingProxyType({
    ("server", "get_server_instance_list"): _hint(
        "Server",
        "View/getServerInstanceList",
        related_actions=("View/getPlacementGroupList",),
        managed_policy="NCP_VPC_SERVER_VIEWER",
    ),
    ("network_interface", "get_network_interface_instance_list"): _hint(
        "Server",
        "View/getNetworkInterfaceList",
        related_actions=("View/getNetworkInterfaceDetail",),
        managed_policy="NCP_VPC_SERVER_VIEWER",
        security_note=(
            "NCP 콘솔이 Change/setSecondaryIP를 연관 액션으로 제시하지만 "
            "보고서 수집에는 쓰기 권한을 권고하지 않습니다."
        ),
    ),
    ("block_storage", "get_block_storage_instance_list"): _hint(
        "Server",
        "View/getBlockStorageInstanceList",
        related_actions=(
            "View/getServerInstanceList",
            "View/getServerInstanceDetail",
            "View/getPlacementGroupList",
        ),
        managed_policy="NCP_VPC_SERVER_VIEWER",
    ),
    ("access_control_group", "get_access_control_group_list"): _hint(
        "Server",
        "View/getACGList",
        managed_policy="NCP_VPC_SERVER_VIEWER",
    ),
    (
        "access_control_group_rule",
        "get_access_control_group_rule_list",
    ): _hint(
        "Server",
        "View/getACGDetail",
        related_actions=("View/getACGList",),
        managed_policy="NCP_VPC_SERVER_VIEWER",
        basis="parent_detail_inference",
    ),
    ("public_ip", "get_public_ip_instance_list"): _hint(
        "Server",
        "View/getPublicIPInstanceList",
        managed_policy="NCP_VPC_SERVER_VIEWER",
    ),
    (
        "block_storage_snapshot",
        "get_block_storage_snapshot_instance_list",
    ): _hint(
        "Server",
        "View/getBlockStorageSnapshotInstanceList",
        managed_policy="NCP_VPC_SERVER_VIEWER",
    ),
    ("server_image", "get_member_server_instance_list"): _hint(
        "Server",
        "View/getMemberServerImageList",
        managed_policy="NCP_VPC_SERVER_VIEWER",
    ),
    ("vpc", "get_vpc_list"): _hint("VPC", "View/getVPCList"),
    ("subnet", "get_subnet_list"): _hint("VPC", "View/getSubnetList"),
    ("route_table", "get_route_table_list"): _hint(
        "VPC",
        "View/getRouteTableList",
    ),
    ("route_table_subnet", "get_route_table_subnet_list"): _hint(
        "VPC",
        "View/getRouteTableDetail",
        related_actions=("View/getRouteTableList",),
        basis="parent_detail_inference",
    ),
    ("route_table_route", "get_route_list"): _hint(
        "VPC",
        "View/getRouteTableDetail",
        related_actions=("View/getRouteTableList",),
        basis="parent_detail_inference",
    ),
    ("network_acl", "get_network_acl_list"): _hint(
        "VPC",
        "View/getNetworkACLList",
    ),
    ("network_acl_rule", "get_network_acl_rule_list"): _hint(
        "VPC",
        "View/getNetworkACLDetail",
        related_actions=("View/getNetworkACLList",),
        basis="parent_detail_inference",
    ),
    ("nat_gateway", "get_nat_gateway_instance_list"): _hint(
        "VPC",
        "View/getNATGatewayList",
    ),
    ("vpc_peering", "get_vpc_peering_instance_list"): _hint(
        "VPC",
        "View/getVPCPeeringList",
    ),
    ("load_balancer", "get_load_balancer_instance_list"): _hint(
        "Load Balancer",
        "View/getLoadBalancerInstanceList",
        managed_policy="NCP_VPC_LOAD_BALANCER_VIEWER",
    ),
    ("target_group", "get_target_group_list"): _hint(
        "Load Balancer",
        "View/getTargetGroupList",
        related_actions=("View/getTargetGroupDetail",),
        managed_policy="NCP_VPC_LOAD_BALANCER_VIEWER",
    ),
    ("target_group", "get_target_list"): _hint(
        "Load Balancer",
        "View/getTargetList",
        related_actions=(
            "View/getTargetGroupList",
            "View/getTargetGroupDetail",
        ),
        managed_policy="NCP_VPC_LOAD_BALANCER_VIEWER",
    ),
    ("nas_vpc", "get_nas_volume_instance_list"): _hint(
        "NAS",
        "View/getNASVolumeInstanceList",
        managed_policy="NCP_VPC_NAS_VIEWER",
    ),
    ("cdb_mysql", "get_cloud_mysql_instance_list"): _hint(
        "Cloud DB for MySQL",
        "View/getDBServiceList",
        managed_policy="NCP_VPC_CLOUD_DB_FOR_MYSQL_VIEWER",
        basis="operation_semantics",
    ),
    ("cdb_postgresql", "get_cloud_postgresql_instance_list"): _hint(
        "Cloud DB for PostgreSQL",
        "View/getDBServiceList",
        managed_policy="NCP_VPC_CLOUD_DB_FOR_POSTGRESQL_VIEWER",
        basis="operation_semantics",
    ),
    ("cdb_mssql", "get_cloud_mssql_instance_list"): _hint(
        "Cloud DB for MSSQL",
        "View/getDBServiceList",
        managed_policy="NCP_VPC_CLOUD_DB_FOR_MSSQL_VIEWER",
        basis="operation_semantics",
    ),
    ("cdb_mongodb", "get_cloud_mongodb_instance_list"): _hint(
        "Cloud DB for MongoDB",
        "View/getServiceList",
        managed_policy="NCP_VPC_CLOUD_DB_FOR_MONGODB_VIEWER",
        basis="operation_semantics",
    ),
    ("cdb_cache", "get_cloud_cache_instance_list"): _hint(
        "Cloud DB for Cache",
        "View/getServiceList",
        managed_policy="NCP_VPC_CLOUD_DB_FOR_CACHE_VIEWER",
        basis="operation_semantics",
    ),
    ("nks", "get_nks_cluster_list"): _hint(
        "Ncloud Kubernetes Service",
        "View/getClusterList",
        related_actions=(
            "View/getWorkerNodeList",
            "View/getNodePoolList",
            "View/getServerInstancesList",
            "View/getVPCList",
            "View/getSubnetList",
        ),
        security_note=(
            "관리형 Kubernetes Service Viewer는 NAS 변경 권한까지 포함할 수 "
            "있어 최소권한 대안으로 표시하지 않습니다."
        ),
    ),
    ("global_dns", "get_domain"): _hint(
        "Global DNS",
        "View/getDomainList",
        managed_policy="NCP_GLOBAL_DNS_VIEWER",
    ),
    ("certificate", "get_certificate_list"): _hint(
        "Certificate Manager",
        "View/getCertificateList",
        managed_policy="NCP_CERTIFICATE_MANAGER_VIEWER",
    ),
    ("resource_manager", "get_resource_list"): _hint(
        "Resource Manager",
        "View/getResourceList",
        managed_policy="NCP_RESOURCE_MANAGER_VIEWER",
    ),
    ("infrastructure_metric", "get_system_schema_key_list"): _hint(
        "Cloud Insight",
        "View/getSystemSchemaKeyList",
        related_actions=("View/getProductSchema",),
        managed_policy="NCP_CLOUD_INSIGHT_VIEWER",
    ),
    ("infrastructure_metric", "get_search_metric_list"): _hint(
        "Cloud Insight",
        "View/getMetric",
        managed_policy="NCP_CLOUD_INSIGHT_VIEWER",
        basis="operation_semantics",
    ),
    ("infrastructure_metric", "get_query_data_multiple"): _hint(
        "Cloud Insight",
        "View/getMetric",
        managed_policy="NCP_CLOUD_INSIGHT_VIEWER",
        basis="operation_semantics",
    ),
    ("event", "get_search_event"): _hint(
        "Cloud Insight",
        "View/getEventList",
        managed_policy="NCP_CLOUD_INSIGHT_VIEWER",
        basis="operation_semantics",
    ),
    ("event", "get_activity_list"): _hint(
        "Cloud Activity Tracer",
        "View/getActivityList",
        managed_policy="NCP_CLOUD_ACTIVITY_TRACER_VIEWER",
    ),
})


def permission_diagnostic_fields(issue: Mapping[str, Any]) -> dict[str, Any]:
    """진단 항목에 표시할 권한, 근거 및 연관 액션을 계산한다."""

    provider_actions, provider_write_actions = _provider_actions(
        issue.get("required_actions")
    )
    hint = permission_hint_for(issue)
    if provider_actions or provider_write_actions:
        return _permission_fields(
            actions=provider_actions,
            write_actions=provider_write_actions,
            source="provider_response",
            hint=hint,
        )

    if not is_permission_related_issue(issue):
        return _permission_fields(source="not_applicable")

    if hint is None:
        return _permission_fields(source="unknown")

    return _permission_fields(
        actions=hint.actions,
        source="api_catalog",
        hint=hint,
    )


def permission_hint_for(issue: Mapping[str, Any]) -> Optional[PermissionHint]:
    """대상과 API가 일치하는 권한 힌트를 반환한다."""

    target_type = _normalized_key(issue.get("target_type"))
    api = _normalized_key(issue.get("api") or issue.get("source"))
    if not api:
        return None

    exact = PERMISSION_HINTS.get((target_type, api))
    if exact is not None:
        return exact

    # 구형 스냅샷에 target_type이 없더라도 API가 한 권한으로만 대응하면
    # 안전하게 복구한다. 서로 다른 서비스에 대응하는 API는 추론하지 않는다.
    candidates = {
        hint
        for (_, candidate_api), hint in PERMISSION_HINTS.items()
        if candidate_api == api
    }
    return next(iter(candidates)) if len(candidates) == 1 else None


def is_permission_related_issue(issue: Mapping[str, Any]) -> bool:
    """응답이 권한 점검 대상인지 보수적으로 판별한다."""

    status = _status_code(issue.get("status_code"))
    code = _text(issue.get("error_code") or issue.get("code")).upper()

    if code in _PERMISSION_ERROR_CODES:
        return True
    if status == 403:
        return True

    # NCP의 404/300은 권한 거부일 수 있지만 일반 404는 미지원 API나
    # 실제 미존재일 수 있으므로 코드 300이 없으면 권한으로 단정하지 않는다.
    if status in {404, 405, 501} or (status is not None and status >= 500):
        return False

    message = _text(issue.get("message")).casefold()
    return any(marker in message for marker in _PERMISSION_MESSAGE_MARKERS)


def _permission_fields(
    *,
    source: str,
    actions: tuple[str, ...] = (),
    write_actions: tuple[str, ...] = (),
    hint: Optional[PermissionHint] = None,
) -> dict[str, Any]:
    return {
        "permission_actions": list(actions),
        "permission_write_actions": list(write_actions),
        "permission_related_actions": (
            list(hint.related_actions) if hint is not None else []
        ),
        "permission_service_name": (
            hint.service_name if hint is not None else ""
        ),
        "permission_managed_policy": (
            hint.managed_policy if hint is not None else None
        ),
        "permission_source": source,
        "permission_basis": hint.basis if hint is not None else "",
        "permission_security_note": (
            hint.security_note if hint is not None else None
        ),
    }


def _provider_actions(value: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not isinstance(value, (list, tuple)):
        return (), ()

    view_actions = []
    write_actions = []
    for candidate in value[:_MAX_PROVIDER_ACTIONS]:
        action = _text(candidate)
        if not _ACTION_PATTERN.fullmatch(action):
            continue
        destination = (
            view_actions if action.startswith("View/") else write_actions
        )
        if action not in destination:
            destination.append(action)
    return tuple(view_actions), tuple(write_actions)


def _status_code(value: Any) -> Optional[int]:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _text(value).casefold()).strip("_")


def _text(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


__all__ = [
    "PERMISSION_HINTS",
    "PermissionHint",
    "is_permission_related_issue",
    "permission_diagnostic_fields",
    "permission_hint_for",
]

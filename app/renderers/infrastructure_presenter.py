"""인프라 인벤토리를 보고서용 자원 현황 행으로 변환한다."""

from __future__ import annotations

import numbers
from typing import Any, Dict, Iterable, Mapping, Sequence

# 금액을 계산하지 않고, 공급자 응답에서 확인된 과금 관련 규모만 표시한다.
# 여러 키를 둔 항목은 서비스 API별 필드명 차이와 이전 스냅샷을 함께 지원한다.
_SIZE_DIMENSIONS: dict[
    str,
    tuple[tuple[tuple[str, ...], str, str], ...],
] = {
    "SERVER": (
        (("server_product_name", "server_product_code"), "상품", ""),
        (("cpu_count",), "vCPU", "개"),
        (("memory_gb",), "메모리", " GB"),
    ),
    "LOAD_BALANCER": (
        (("load_balancer_type",), "유형", ""),
        (("throughput_type",), "처리량 등급", ""),
    ),
    "AUTO_SCALING": (
        (("desired_capacity", "desired_count"), "희망 용량", "대"),
        (("min_size", "min_count"), "최소", "대"),
        (("max_size", "max_count"), "최대", "대"),
    ),
    "BLOCK_STORAGE": (
        (("volume_type", "disk_type"), "볼륨 유형", ""),
        (("size_gb", "storage_size_gb"), "용량", " GB"),
        (("iops",), "IOPS", ""),
        (("throughput_mbps",), "처리량", " MB/s"),
    ),
    "OBJECT_STORAGE": (
        (("storage_size_gb", "size_gb", "total_size_gb"), "저장량", " GB"),
        (("object_count",), "객체", "개"),
        (("request_count",), "요청", "건"),
        (("outbound_traffic_gb",), "외부 전송", " GB"),
    ),
    "NAS": (
        (("protocol",), "프로토콜", ""),
        (("size_gb", "storage_size_gb"), "용량", " GB"),
    ),
    "CLOUD_DB": (
        (("engine",), "엔진", ""),
        (("generation",), "세대", ""),
        (("server_count",), "DB 서버", "대"),
        (("cpu_count_total",), "총 vCPU", "개"),
        (("memory_gb_total",), "총 메모리", " GB"),
        (("data_storage_gb_total",), "데이터 용량", " GB"),
    ),
    "KUBERNETES": (
        (("cluster_type",), "클러스터 유형", ""),
        (("node_count",), "노드", "대"),
        (("node_max_count",), "최대 노드", "대"),
        (("node_pool_count",), "노드풀", "개"),
    ),
    "VPC": ((("ipv4_cidr_block",), "주소 범위", ""),),
    "SUBNET": ((("ipv4_cidr_block",), "주소 범위", ""),),
    "ROUTE_TABLE": (
        (("route_count",), "Route", "개"),
        (("associated_subnet_count",), "연결 Subnet", "개"),
    ),
    "ACCESS_CONTROL_GROUP": (
        (("rule_count",), "규칙", "개"),
        (("inbound_rule_count",), "Inbound", "개"),
        (("outbound_rule_count",), "Outbound", "개"),
    ),
    "NETWORK_ACL": (
        (("rule_count",), "규칙", "개"),
        (("inbound_rule_count",), "Inbound", "개"),
        (("outbound_rule_count",), "Outbound", "개"),
    ),
    "NAT_GATEWAY": (
        (("gateway_type",), "유형", ""),
        (("public_ip_count",), "Public IP", "개"),
    ),
    "PUBLIC_IP": ((("associated",), "서버 연결", ""),),
    "GLOBAL_DNS": ((("record_count",), "레코드", "개"),),
    "GLOBAL_TRAFFIC_MANAGER": (
        (("domain_count",), "도메인", "개"),
        (("endpoint_count",), "Endpoint", "개"),
    ),
    "API_GATEWAY": (
        (("api_count",), "API", "개"),
        (("request_count",), "요청", "건"),
    ),
    "SEARCH_ENGINE": (
        (("node_count",), "노드", "대"),
        (("storage_size_gb", "data_storage_gb_total"), "저장 용량", " GB"),
    ),
    "DATA_STREAMING": (
        (("broker_count", "node_count"), "브로커", "대"),
        (("storage_size_gb",), "저장 용량", " GB"),
    ),
    "CLOUD_HADOOP": (
        (("node_count",), "노드", "대"),
        (("storage_size_gb",), "저장 용량", " GB"),
    ),
    "DATA_STREAM": (
        (("partition_count",), "파티션", "개"),
        (("retention_hours",), "보관", "시간"),
    ),
    "BLOCK_STORAGE_SNAPSHOT": ((("snapshot_volume_size_gb",), "스냅샷 용량", " GB"),),
    "SERVER_IMAGE": ((("block_storage_size_gb",), "이미지 용량", " GB"),),
    "BACKUP": (
        (("storage_size_gb", "backup_size_gb"), "백업 용량", " GB"),
        (("retention_days",), "보관", "일"),
    ),
    "ARCHIVE_STORAGE": ((("storage_size_gb", "size_gb"), "보관 용량", " GB"),),
}


def merge_server_details(
    resource: Mapping[str, Any],
    servers: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    """서버 상세 데이터를 동일한 서버 자원 행에 안전하게 합친다."""
    merged = dict(resource)
    details = _mapping(resource.get("details"))
    if str(resource.get("category") or "").upper() != "SERVER":
        merged["details"] = details
        return merged

    server = _matching_server(resource, servers)
    if server is None:
        merged["details"] = details
        return merged

    raw_server = _mapping(server.get("raw_server"))
    if not _has_value(merged.get("resource_name")):
        merged["resource_name"] = server.get("server_name")
    if not _has_value(merged.get("status")):
        merged["status"] = server.get("status")
    values = {
        "cpu_count": server.get("cpu_count"),
        "memory_gb": server.get("memory_gb"),
        "vpc_no": server.get("vpc_id") or raw_server.get("vpcNo"),
        "subnet_no": server.get("subnet_id") or raw_server.get("subnetNo"),
        "private_ip": server.get("private_ip"),
        "public_ip": server.get("public_ip"),
        "all_private_ips": _server_private_ips(server),
        "storage_count": _server_storage_count(server),
        "storage_size_gb_total": _server_storage_size_gb(server),
        "server_product_code": (
            server.get("server_product_code") or raw_server.get("serverProductCode")
        ),
        "server_product_name": (
            server.get("server_product_name") or raw_server.get("serverProductName")
        ),
    }
    for key, value in values.items():
        if key not in details and _has_value(value):
            details[key] = value
    if not _has_value(merged.get("create_time")):
        create_time = (
            server.get("create_date") or server.get("create_time") or raw_server.get("createDate")
        )
        if _has_value(create_time):
            merged["create_time"] = create_time
    merged["details"] = details
    return merged


def server_spec_summary(details: Mapping[str, Any]) -> str:
    """서버 상품·컴퓨팅 사양과 연결 스토리지 규모를 한 셀로 요약한다."""
    parts = []
    product_name = details.get("server_product_name")
    product_code = details.get("server_product_code")
    if _has_value(product_name):
        _append_value(parts, "상품", product_name)
    elif _has_value(product_code):
        _append_value(parts, "SKU", product_code)
    _append_suffixed_value(parts, "vCPU", details.get("cpu_count"), "개")
    _append_suffixed_value(parts, "메모리", details.get("memory_gb"), " GB")

    storage_count = details.get("storage_count")
    storage_size = details.get("storage_size_gb_total")
    if _has_value(storage_count) or _has_value(storage_size):
        storage_values = []
        if _has_value(storage_count):
            storage_values.append(f"{_display_value(storage_count)}개")
        if _has_value(storage_size):
            storage_values.append(f"{_display_value(storage_size)} GB")
        parts.append(f"연결 스토리지: {' / '.join(storage_values)}")
    return " · ".join(parts) or "수집된 서버 사양 정보 없음"


def resource_size_summary(category: Any, details: Mapping[str, Any]) -> str:
    """수집된 공급자 필드만으로 자원의 과금 관련 규모를 요약한다."""
    normalized_category = str(category or "").strip().upper()
    parts = []
    for keys, label, suffix in _SIZE_DIMENSIONS.get(
        normalized_category,
        (),
    ):
        value = _first_value(details, keys)
        if not _has_value(value):
            continue
        parts.append(f"{label}: {_display_value(value)}{suffix}")
    return " · ".join(parts) or "수집된 규모 정보 없음"


def resource_connection_summary(
    category: Any,
    details: Mapping[str, Any],
) -> str:
    """기존 서버 상세의 주소 정보와 자원 연결 관계를 한 열로 요약한다."""
    normalized_category = str(category or "").strip().upper()
    parts = []

    if normalized_category == "SERVER":
        private_ips = details.get("all_private_ips") or details.get("private_ip")
        _append_value(parts, "Private", private_ips)
        _append_value(parts, "Public", details.get("public_ip"))
        storage_count = details.get("storage_count")
        storage_size = details.get("storage_size_gb_total")
        if _has_value(storage_count) or _has_value(storage_size):
            storage_values = []
            if _has_value(storage_count):
                storage_values.append(f"{_display_value(storage_count)}개")
            if _has_value(storage_size):
                storage_values.append(f"{_display_value(storage_size)} GB")
            parts.append(f"연결 스토리지: {' / '.join(storage_values)}")
    elif normalized_category == "LOAD_BALANCER":
        _append_value(parts, "IP", details.get("ip_addresses"))
        _append_value(parts, "Target Group", details.get("target_group_count"))
        if (
            details.get("target_group_count")
            and details.get("target_health_snapshot_available") is True
        ):
            _append_value(
                parts,
                "등록 Target",
                details.get("registered_target_count"),
            )
            _append_value(parts, "Ready", details.get("ready_target_count"))
            _append_value(
                parts,
                "Unready",
                details.get("unready_target_count"),
            )
            _append_value(
                parts,
                "미평가",
                details.get("unused_target_count"),
            )
            _append_value(
                parts,
                "알 수 없음",
                details.get("unknown_target_count"),
            )
        elif details.get("target_group_count"):
            parts.append("Target 상태: 수집 실패 또는 권한 없음")
    elif normalized_category == "BLOCK_STORAGE":
        _append_value(
            parts,
            "연결 서버",
            details.get("attached_server_name") or details.get("attached_server_id"),
        )
    elif normalized_category == "NAS":
        _append_value(parts, "연결 서버", details.get("server_instance_nos"))
    elif normalized_category == "CLOUD_DB":
        _append_value(parts, "Private", details.get("private_ips"))
    elif normalized_category == "PUBLIC_IP":
        _append_value(parts, "Public", details.get("public_ip"))
        _append_value(parts, "연결 서버", details.get("attached_server_id"))
    elif normalized_category == "NAT_GATEWAY":
        _append_value(parts, "Public", details.get("public_ips"))
        _append_value(parts, "Private", details.get("private_ips"))

    if normalized_category not in {"VPC", "VPC_PEERING"}:
        _append_value(parts, "VPC", details.get("vpc_no"))
    _append_value(
        parts,
        "Subnet",
        details.get("subnet_nos") or details.get("subnet_no"),
    )
    if normalized_category == "VPC_PEERING":
        _append_value(parts, "Source VPC", details.get("source_vpc_no"))
        _append_value(parts, "Target VPC", details.get("target_vpc_no"))
    return " · ".join(parts) or "-"


def _matching_server(
    resource: Mapping[str, Any],
    servers: Iterable[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    candidates = [server for server in servers if isinstance(server, Mapping)]
    resource_id = _normalized_text(resource.get("resource_id"))
    if resource_id:
        for server in candidates:
            if _normalized_text(server.get("server_id")) == resource_id:
                return server

    resource_name = _normalized_text(resource.get("resource_name"))
    if not resource_name:
        return None
    matches = [
        server
        for server in candidates
        if _normalized_text(server.get("server_name")) == resource_name
    ]
    return matches[0] if len(matches) == 1 else None


def _server_private_ips(server: Mapping[str, Any]) -> list[Any]:
    values = []
    for nic in server.get("nics") or []:
        if not isinstance(nic, Mapping):
            continue
        values.extend(nic.get("all_private_ips") or [])
        if not nic.get("all_private_ips"):
            values.append(nic.get("primary_ip"))
            values.extend(nic.get("secondary_ips") or [])
    if not values:
        values.append(server.get("private_ip"))
    return _unique_values(values)


def _server_storage_count(server: Mapping[str, Any]) -> int | None:
    storages = server.get("storages")
    return len(storages) if isinstance(storages, list) else None


def _server_storage_size_gb(server: Mapping[str, Any]) -> float | int | None:
    storages = server.get("storages")
    if not isinstance(storages, list):
        return None
    sizes = [
        storage.get("size_gb")
        for storage in storages
        if isinstance(storage, Mapping)
        and isinstance(storage.get("size_gb"), numbers.Real)
        and not isinstance(storage.get("size_gb"), bool)
    ]
    if not sizes:
        return None
    total = sum(sizes)
    return int(total) if float(total).is_integer() else total


def _append_value(parts: list[str], label: str, value: Any) -> None:
    if _has_value(value):
        parts.append(f"{label}: {_display_value(value)}")


def _append_suffixed_value(
    parts: list[str],
    label: str,
    value: Any,
    suffix: str,
) -> None:
    if _has_value(value):
        parts.append(f"{label}: {_display_value(value)}{suffix}")


def _first_value(details: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = details.get(key)
        if _has_value(value):
            return value
    return None


def _display_value(value: Any) -> str:
    if isinstance(value, bool):
        return "사용" if value else "미사용"
    if isinstance(value, numbers.Real):
        number = float(value)
        if number.is_integer():
            return f"{int(number):,}"
        return f"{number:,.3f}".rstrip("0").rstrip(".")
    if isinstance(value, (list, tuple, set)):
        values = _unique_values(value)
        visible = ", ".join(str(item) for item in values[:5])
        remaining = len(values) - 5
        return f"{visible} 외 {remaining}개" if remaining > 0 else visible
    return str(value).strip()


def _unique_values(values: Iterable[Any]) -> list[Any]:
    result = []
    seen = set()
    for value in values:
        if not _has_value(value):
            continue
        marker = str(value).strip()
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _normalized_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

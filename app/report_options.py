from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


REPORT_OPTIONS_SCHEMA_VERSION = "1.0"

REPORT_SECTION_OPTIONS = (
    "executive_summary",
    "billing",
    "organization_billing",
    "infrastructure_inventory",
    "infrastructure_diagram",
    "monitoring",
    "insight_events",
    "activity_history",
    "collection_diagnostics",
)

REPORT_SECTION_LABELS = {
    "executive_summary": "주요 요약",
    "billing": "청구·예상 비용",
    "organization_billing": "Organization 계정별 비용",
    "infrastructure_inventory": "대표 인프라 목록",
    "infrastructure_diagram": "클라우드 구성도",
    "monitoring": "모니터링 그래프",
    "insight_events": "Cloud Insight 이벤트",
    "activity_history": "Cloud Activity Tracer 이력",
    "collection_diagnostics": "수집 경고·오류",
}

RESOURCE_CATEGORY_OPTIONS = (
    "SERVER",
    "LOAD_BALANCER",
    "AUTO_SCALING",
    "BLOCK_STORAGE",
    "OBJECT_STORAGE",
    "NAS",
    "CLOUD_DB",
    "CDN",
    "KUBERNETES",
    "VPC",
    "SUBNET",
    "NAT_GATEWAY",
    "PUBLIC_IP",
    "VPC_PEERING",
    "VIRTUAL_PRIVATE_GATEWAY",
    "IPSEC_VPN",
    "CLOUD_CONNECT",
    "GLOBAL_EDGE",
    "GLOBAL_DNS",
    "GLOBAL_TRAFFIC_MANAGER",
    "API_GATEWAY",
    "CERTIFICATE",
    "SEARCH_ENGINE",
    "DATA_STREAMING",
    "CLOUD_HADOOP",
    "DATA_STREAM",
    "CLOUD_FUNCTIONS",
    "CONTAINER_REGISTRY",
    "BLOCK_STORAGE_SNAPSHOT",
    "SERVER_IMAGE",
    "BACKUP",
    "ARCHIVE_STORAGE",
    "SECURITY_SERVICE",
)

# Preserve declaration order while preventing accidental duplicate form fields.
RESOURCE_CATEGORY_OPTIONS = tuple(dict.fromkeys(RESOURCE_CATEGORY_OPTIONS))

RESOURCE_CATEGORY_LABELS = {
    "SERVER": "서버",
    "LOAD_BALANCER": "Load Balancer",
    "AUTO_SCALING": "Auto Scaling",
    "BLOCK_STORAGE": "Block Storage",
    "OBJECT_STORAGE": "Object Storage",
    "NAS": "NAS",
    "CLOUD_DB": "Cloud DB",
    "CDN": "CDN",
    "KUBERNETES": "Kubernetes Service",
    "VPC": "VPC",
    "SUBNET": "Subnet",
    "NAT_GATEWAY": "NAT Gateway",
    "PUBLIC_IP": "Public IP",
    "VPC_PEERING": "VPC Peering",
    "VIRTUAL_PRIVATE_GATEWAY": "Virtual Private Gateway",
    "IPSEC_VPN": "IPsec VPN",
    "CLOUD_CONNECT": "Cloud Connect",
    "GLOBAL_EDGE": "Global Edge",
    "GLOBAL_DNS": "Global DNS",
    "GLOBAL_TRAFFIC_MANAGER": "Global Traffic Manager",
    "API_GATEWAY": "API Gateway",
    "CERTIFICATE": "Certificate Manager",
    "SEARCH_ENGINE": "Search Engine Service",
    "DATA_STREAMING": "Cloud Data Streaming Service",
    "CLOUD_HADOOP": "Cloud Hadoop",
    "DATA_STREAM": "Data Stream",
    "CLOUD_FUNCTIONS": "Cloud Functions",
    "CONTAINER_REGISTRY": "Container Registry",
    "BLOCK_STORAGE_SNAPSHOT": "Block Storage Snapshot",
    "SERVER_IMAGE": "Server Image",
    "BACKUP": "Backup",
    "ARCHIVE_STORAGE": "Archive Storage",
    "SECURITY_SERVICE": "보안 서비스 (WAF·IDS·IPS·DDoS)",
}

MONITORING_CATEGORY_OPTIONS = (
    "SERVER",
    "LOAD_BALANCER",
    "CLOUD_DB",
    "KUBERNETES",
    "NAS",
    "OBJECT_STORAGE",
    "AUTO_SCALING",
    "SEARCH_ENGINE",
    "DATA_STREAMING",
    "CLOUD_HADOOP",
    "DATA_STREAM",
)

DIAGRAM_OPTION_LABELS = {
    "enabled": "구성도 생성",
    "show_resource_name": "자원·인스턴스 이름 표시",
    "show_resource_id": "자원·인스턴스 ID 표시",
    "show_private_ip": "사설 IP 표시",
    "show_public_ip": "공인 IP 표시",
    "show_network_cidr": "VPC·Subnet CIDR 표시",
    "show_status": "운영 상태 표시",
    "show_zone": "Zone 표시",
    "show_platform": "플랫폼(VPC/Classic) 표시",
    "include_unmapped_resources": "연결 관계를 확인하지 못한 자원을 별도 표시",
    "group_by_vpc": "VPC·네트워크 계층 기준으로 배치",
}

DIAGRAM_BOOLEAN_OPTIONS = (
    "enabled",
    "show_resource_name",
    "show_resource_id",
    "show_private_ip",
    "show_public_ip",
    "show_network_cidr",
    "show_status",
    "show_zone",
    "show_platform",
    "include_unmapped_resources",
    "group_by_vpc",
)

DEFAULT_DIAGRAM_MAX_NODES = 120
MIN_DIAGRAM_MAX_NODES = 10
MAX_DIAGRAM_MAX_NODES = 200

DEFAULT_REPORT_OPTIONS: dict[str, Any] = {
    "schema_version": REPORT_OPTIONS_SCHEMA_VERSION,
    "sections": list(REPORT_SECTION_OPTIONS),
    "resource_categories": list(RESOURCE_CATEGORY_OPTIONS),
    "monitoring_categories": list(MONITORING_CATEGORY_OPTIONS),
    "diagram": {
        **{key: True for key in DIAGRAM_BOOLEAN_OPTIONS},
        "max_nodes": DEFAULT_DIAGRAM_MAX_NODES,
    },
}

LEGACY_RESOURCE_CATEGORY_OPTIONS = (
    "SERVER",
    "LOAD_BALANCER",
    "BLOCK_STORAGE",
    "OBJECT_STORAGE",
    "NAS",
    "CLOUD_DB",
    "CDN",
    "KUBERNETES",
)

LEGACY_MONITORING_CATEGORY_OPTIONS = (
    "SERVER",
    "LOAD_BALANCER",
    "CLOUD_DB",
    "KUBERNETES",
)


class ReportOptions:
    """Immutable-by-interface access to normalized report configuration."""

    def __init__(self, value: Any = None):
        self._value = normalize_report_options(value)

    @classmethod
    def from_value(cls, value: Any) -> "ReportOptions":
        return value if isinstance(value, cls) else cls(value)

    def section_enabled(self, name: str) -> bool:
        return str(name) in self._value["sections"]

    def resource_enabled(self, category: str) -> bool:
        return str(category).upper() in self._value["resource_categories"]

    def monitoring_enabled(self, category: str) -> bool:
        return str(category).upper() in self._value["monitoring_categories"]

    def diagram_option(self, name: str, default: Any = None) -> Any:
        return self._value["diagram"].get(str(name), default)

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._value)


def default_report_options() -> dict[str, Any]:
    """Return an isolated copy of the backwards-compatible report defaults."""
    return deepcopy(DEFAULT_REPORT_OPTIONS)


def legacy_report_options() -> dict[str, Any]:
    """Return the rendering contract used before report options existed.

    A stored report must not acquire new sections or sensitive topology fields
    merely because it is opened with a newer renderer.
    """
    options = default_report_options()
    options["sections"] = [
        section
        for section in REPORT_SECTION_OPTIONS
        if section != "infrastructure_diagram"
    ]
    options["resource_categories"] = list(
        LEGACY_RESOURCE_CATEGORY_OPTIONS
    )
    options["monitoring_categories"] = list(
        LEGACY_MONITORING_CATEGORY_OPTIONS
    )
    options["diagram"] = {
        **options["diagram"],
        "enabled": False,
        "show_resource_id": False,
        "show_private_ip": False,
        "show_public_ip": False,
        "show_network_cidr": False,
    }
    return options


def normalize_report_options(value: Any) -> dict[str, Any]:
    """Normalize persisted options through explicit allowlists.

    Missing settings use all current report capabilities, keeping tenants made
    before this feature backwards compatible. Unknown keys and values are
    discarded so stored JSON cannot enable arbitrary collectors or fields.
    """
    defaults = default_report_options()
    if not isinstance(value, Mapping):
        return defaults

    normalized = {
        "schema_version": REPORT_OPTIONS_SCHEMA_VERSION,
        "sections": _allowed_list(
            value, "sections", REPORT_SECTION_OPTIONS, defaults["sections"]
        ),
        "resource_categories": _allowed_list(
            value,
            "resource_categories",
            RESOURCE_CATEGORY_OPTIONS,
            defaults["resource_categories"],
        ),
        "monitoring_categories": _allowed_list(
            value,
            "monitoring_categories",
            MONITORING_CATEGORY_OPTIONS,
            defaults["monitoring_categories"],
        ),
        "diagram": _normalize_diagram(value.get("diagram")),
    }
    return normalized


def validate_report_options(value: Any) -> dict[str, Any]:
    """Validate an explicit portal update and return its canonical form."""
    if not isinstance(value, Mapping):
        raise ValueError("보고서 출력 설정은 객체 형식이어야 합니다.")
    for key in ("sections", "resource_categories", "monitoring_categories"):
        if key not in value or not isinstance(value[key], (list, tuple, set)):
            raise ValueError(f"{key} 선택값이 올바르지 않습니다.")

    normalized = normalize_report_options(value)
    if not normalized["sections"]:
        raise ValueError("보고서 섹션을 하나 이상 선택하세요.")

    selected_sections = set(normalized["sections"])
    if (
        {"infrastructure_inventory", "infrastructure_diagram"}
        & selected_sections
        and not normalized["resource_categories"]
    ):
        raise ValueError("인프라 자원 범주를 하나 이상 선택하세요.")
    if (
        "monitoring" in selected_sections
        and not normalized["monitoring_categories"]
    ):
        raise ValueError("모니터링 그래프 대상을 하나 이상 선택하세요.")
    return normalized


def _allowed_list(
    value: Mapping[str, Any],
    key: str,
    allowed: tuple[str, ...],
    default: list[str],
) -> list[str]:
    if key not in value:
        return list(default)
    raw = value.get(key)
    if not isinstance(raw, (list, tuple, set)):
        return list(default)
    requested = {str(item).strip() for item in raw}
    return [item for item in allowed if item in requested]


def _normalize_diagram(value: Any) -> dict[str, Any]:
    defaults = default_report_options()["diagram"]
    if not isinstance(value, Mapping):
        return defaults

    result = {
        key: _strict_bool(value.get(key), defaults[key])
        for key in DIAGRAM_BOOLEAN_OPTIONS
    }
    max_nodes = value.get("max_nodes", defaults["max_nodes"])
    try:
        max_nodes = int(max_nodes)
    except (TypeError, ValueError):
        max_nodes = defaults["max_nodes"]
    result["max_nodes"] = min(
        MAX_DIAGRAM_MAX_NODES,
        max(MIN_DIAGRAM_MAX_NODES, max_nodes),
    )
    return result


def _strict_bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default

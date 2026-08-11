from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


REPORT_OPTIONS_SCHEMA_VERSION = "1.1"

REPORT_SECTION_OPTIONS = (
    "executive_summary",
    "billing",
    "organization_billing",
    "infrastructure_inventory",
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
    "monitoring": "모니터링 그래프",
    "insight_events": "Cloud Insight 이벤트",
    "activity_history": "Cloud Activity Tracer 이력",
    "collection_diagnostics": "수집 경고·오류",
}

NETWORK_CONFIGURATION_CATEGORY_OPTIONS = (
    "ROUTE_TABLE",
    "ACCESS_CONTROL_GROUP",
    "NETWORK_ACL",
)

RESOURCE_CATEGORY_OPTIONS = (
    "SERVER",
    "LOAD_BALANCER",
    "AUTO_SCALING",
    "BLOCK_STORAGE",
    "OBJECT_STORAGE",
    "NAS",
    "CLOUD_DB",
    "KUBERNETES",
    "VPC",
    "SUBNET",
    *NETWORK_CONFIGURATION_CATEGORY_OPTIONS,
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
    "KUBERNETES": "Kubernetes Service",
    "VPC": "VPC",
    "SUBNET": "Subnet",
    "ROUTE_TABLE": "Route Table",
    "ACCESS_CONTROL_GROUP": "ACG",
    "NETWORK_ACL": "Network ACL",
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

DEFAULT_REPORT_OPTIONS: dict[str, Any] = {
    "schema_version": REPORT_OPTIONS_SCHEMA_VERSION,
    "sections": list(REPORT_SECTION_OPTIONS),
    "resource_categories": list(RESOURCE_CATEGORY_OPTIONS),
    "monitoring_categories": list(MONITORING_CATEGORY_OPTIONS),
}

LEGACY_RESOURCE_CATEGORY_OPTIONS = (
    "SERVER",
    "LOAD_BALANCER",
    "BLOCK_STORAGE",
    "OBJECT_STORAGE",
    "NAS",
    "CLOUD_DB",
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

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._value)


def default_report_options() -> dict[str, Any]:
    """Return an isolated copy of the backwards-compatible report defaults."""
    return deepcopy(DEFAULT_REPORT_OPTIONS)


def legacy_report_options() -> dict[str, Any]:
    """Return the rendering contract used before report options existed.

    A stored report must not acquire new sections merely because it is opened
    with a newer renderer.
    """
    options = default_report_options()
    options["sections"] = list(REPORT_SECTION_OPTIONS)
    options["resource_categories"] = list(
        LEGACY_RESOURCE_CATEGORY_OPTIONS
    )
    options["monitoring_categories"] = list(
        LEGACY_MONITORING_CATEGORY_OPTIONS
    )
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

    sections_value = value
    raw_sections = value.get("sections")
    if (
        isinstance(raw_sections, (list, tuple, set))
        and "infrastructure_diagram" in raw_sections
    ):
        # 기존 구성도 전용 설정은 대표 인프라 목록으로 안전하게 승계한다.
        sections_value = dict(value)
        sections_value["sections"] = [
            *raw_sections,
            "infrastructure_inventory",
        ]

    normalized = {
        "schema_version": REPORT_OPTIONS_SCHEMA_VERSION,
        "sections": _allowed_list(
            sections_value,
            "sections",
            REPORT_SECTION_OPTIONS,
            defaults["sections"],
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
        "infrastructure_inventory" in selected_sections
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

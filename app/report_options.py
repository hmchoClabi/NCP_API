from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

REPORT_OPTIONS_SCHEMA_VERSION = "1.4"
UTILIZATION_ALERT_MIN_PERCENT = 90.0
UTILIZATION_ALERT_MAX_PERCENT = 100.0
UTILIZATION_CRITICAL_PERCENT = 95.0
UTILIZATION_MIN_SUSTAINED_MINUTES = 1
UTILIZATION_MAX_SUSTAINED_MINUTES = 1440
UTILIZATION_SUSTAINED_MINUTES = 15

DEFAULT_OPERATIONAL_ANALYSIS: dict[str, Any] = {
    "enabled": True,
    # 추가 권한이 필요한 데이터 원본은 기존 고객에게 자동 활성화하지 않는다.
    "collect_wms": False,
    "collect_security_monitoring": False,
    "thresholds": {
        "cpu_warning_percent": UTILIZATION_ALERT_MIN_PERCENT,
        "cpu_critical_percent": UTILIZATION_CRITICAL_PERCENT,
        "memory_warning_percent": UTILIZATION_ALERT_MIN_PERCENT,
        "memory_critical_percent": UTILIZATION_CRITICAL_PERCENT,
        "disk_warning_percent": UTILIZATION_ALERT_MIN_PERCENT,
        "disk_critical_percent": UTILIZATION_CRITICAL_PERCENT,
        "sustained_minutes": UTILIZATION_SUSTAINED_MINUTES,
        "cost_increase_warning_percent": 20.0,
        "availability_warning_percent": 99.0,
        "availability_critical_percent": 95.0,
        "response_time_warning_ms": 3000.0,
    },
}

ANALYSIS_THRESHOLD_LIMITS: dict[str, tuple[float, float]] = {
    "cpu_warning_percent": (
        UTILIZATION_ALERT_MIN_PERCENT,
        UTILIZATION_ALERT_MAX_PERCENT,
    ),
    "cpu_critical_percent": (
        UTILIZATION_ALERT_MIN_PERCENT,
        UTILIZATION_ALERT_MAX_PERCENT,
    ),
    "memory_warning_percent": (
        UTILIZATION_ALERT_MIN_PERCENT,
        UTILIZATION_ALERT_MAX_PERCENT,
    ),
    "memory_critical_percent": (
        UTILIZATION_ALERT_MIN_PERCENT,
        UTILIZATION_ALERT_MAX_PERCENT,
    ),
    "disk_warning_percent": (
        UTILIZATION_ALERT_MIN_PERCENT,
        UTILIZATION_ALERT_MAX_PERCENT,
    ),
    "disk_critical_percent": (
        UTILIZATION_ALERT_MIN_PERCENT,
        UTILIZATION_ALERT_MAX_PERCENT,
    ),
    "sustained_minutes": (
        UTILIZATION_MIN_SUSTAINED_MINUTES,
        UTILIZATION_MAX_SUSTAINED_MINUTES,
    ),
    "cost_increase_warning_percent": (0.0, 10000.0),
    "availability_warning_percent": (0.0, 100.0),
    "availability_critical_percent": (0.0, 100.0),
    "response_time_warning_ms": (0.0, 3600000.0),
}

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

DEFAULT_REPORT_SECTION_ORDER = (
    "executive_summary",
    "infrastructure_inventory",
    "monitoring",
    "billing",
    "organization_billing",
    "insight_events",
    "activity_history",
    "collection_diagnostics",
)

REPORT_SECTION_LABELS = {
    "executive_summary": "주요 요약·운영 판정",
    "billing": "청구·예상 비용",
    "organization_billing": "Organization 계정별 비용",
    "infrastructure_inventory": "자원 현황",
    "monitoring": "모니터링 그래프",
    "insight_events": "Cloud Insight 이벤트",
    "activity_history": "Cloud Activity Tracer 이력",
    "collection_diagnostics": "수집 진단",
}

REPORT_SECTION_DESCRIPTIONS = {
    "executive_summary": (
        "상태 카드·즉시 확인·데이터 수집 상태·WMS/보안·비용 전기 비교를 표시합니다."
    ),
    "billing": ("과금 기준·서비스별 예상 비용·네트워크/서비스 사용량을 표시합니다."),
    "organization_billing": ("Organization 멤버 계정별 비용 내역을 표시합니다."),
    "infrastructure_inventory": (
        "선택한 서버·스토리지·DB·네트워크 자원과 네트워크 규칙을 표시합니다."
    ),
    "monitoring": ("선택한 자원의 CPU·메모리·디스크 사용량과 서비스 지표를 표시합니다."),
    "insight_events": "Cloud Insight 이벤트와 상태를 표시합니다.",
    "activity_history": ("Cloud Activity Tracer의 API 호출과 자원 변경 이력을 표시합니다."),
    "collection_diagnostics": ("수집 중 발생한 경고·오류와 필요한 권한 진단을 표시합니다."),
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
    "section_order": list(DEFAULT_REPORT_SECTION_ORDER),
    "resource_categories": list(RESOURCE_CATEGORY_OPTIONS),
    "monitoring_categories": list(MONITORING_CATEGORY_OPTIONS),
    "operational_analysis": deepcopy(DEFAULT_OPERATIONAL_ANALYSIS),
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

    @property
    def ordered_sections(self) -> tuple[str, ...]:
        selected = set(self._value["sections"])
        return tuple(section for section in self._value["section_order"] if section in selected)

    def resource_enabled(self, category: str) -> bool:
        return str(category).upper() in self._value["resource_categories"]

    def monitoring_enabled(self, category: str) -> bool:
        return str(category).upper() in self._value["monitoring_categories"]

    def analysis_enabled(self) -> bool:
        return self.section_enabled("executive_summary") and bool(
            self._value["operational_analysis"]["enabled"]
        )

    def analysis_collector_enabled(self, name: str) -> bool:
        key = {
            "wms": "collect_wms",
            "security_monitoring": "collect_security_monitoring",
        }.get(str(name).strip().casefold())
        return bool(key and self._value["operational_analysis"].get(key, False))

    @property
    def operational_analysis(self) -> dict[str, Any]:
        return deepcopy(self._value["operational_analysis"])

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
    options["resource_categories"] = list(LEGACY_RESOURCE_CATEGORY_OPTIONS)
    options["monitoring_categories"] = list(LEGACY_MONITORING_CATEGORY_OPTIONS)
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
    if isinstance(raw_sections, (list, tuple, set)) and "infrastructure_diagram" in raw_sections:
        # 기존 구성도 전용 설정은 자원 현황으로 안전하게 승계한다.
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
        "section_order": _normalize_section_order(value),
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
        "operational_analysis": _normalize_operational_analysis(value.get("operational_analysis")),
    }
    return normalized


def validate_report_options(value: Any) -> dict[str, Any]:
    """Validate an explicit portal update and return its canonical form."""
    if not isinstance(value, Mapping):
        raise ValueError("보고서 출력 설정은 객체 형식이어야 합니다.")
    for key in ("sections", "resource_categories", "monitoring_categories"):
        if key not in value or not isinstance(value[key], (list, tuple, set)):
            raise ValueError(f"{key} 선택값이 올바르지 않습니다.")
    if "section_order" in value and not isinstance(value["section_order"], (list, tuple)):
        raise ValueError("section_order 선택값이 올바르지 않습니다.")

    normalized = normalize_report_options(value)
    if not normalized["sections"]:
        raise ValueError("보고서 섹션을 하나 이상 선택하세요.")

    selected_sections = set(normalized["sections"])
    if "infrastructure_inventory" in selected_sections and not normalized["resource_categories"]:
        raise ValueError("인프라 자원 범주를 하나 이상 선택하세요.")
    if "monitoring" in selected_sections and not normalized["monitoring_categories"]:
        raise ValueError("모니터링 그래프 대상을 하나 이상 선택하세요.")
    thresholds = normalized["operational_analysis"]["thresholds"]
    for prefix in ("cpu", "memory", "disk"):
        if thresholds[f"{prefix}_critical_percent"] < thresholds[f"{prefix}_warning_percent"]:
            raise ValueError(f"{prefix.upper()} 위험 임계치는 주의 임계치 이상이어야 합니다.")
    if thresholds["availability_critical_percent"] > thresholds["availability_warning_percent"]:
        raise ValueError("가용성 위험 임계치는 주의 임계치 이하여야 합니다.")
    return normalized


def _normalize_operational_analysis(value: Any) -> dict[str, Any]:
    defaults = deepcopy(DEFAULT_OPERATIONAL_ANALYSIS)
    if not isinstance(value, Mapping):
        return defaults

    normalized = {
        "enabled": _as_bool(value.get("enabled"), defaults["enabled"]),
        "collect_wms": _as_bool(value.get("collect_wms"), defaults["collect_wms"]),
        "collect_security_monitoring": _as_bool(
            value.get("collect_security_monitoring"),
            defaults["collect_security_monitoring"],
        ),
        "thresholds": {},
    }

    raw_thresholds = value.get("thresholds")
    if not isinstance(raw_thresholds, Mapping):
        raw_thresholds = {}
    for name, default in defaults["thresholds"].items():
        minimum, maximum = ANALYSIS_THRESHOLD_LIMITS[name]
        normalized["thresholds"][name] = _bounded_number(
            raw_thresholds.get(name),
            default=default,
            minimum=minimum,
            maximum=maximum,
            integer=name == "sustained_minutes",
        )

    return normalized


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return default


def _bounded_number(
    value: Any,
    *,
    default: float | int,
    minimum: float,
    maximum: float,
    integer: bool = False,
) -> float | int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if number < minimum or number > maximum:
        number = float(default)
    return int(round(number)) if integer else round(number, 2)


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


def _normalize_section_order(value: Mapping[str, Any]) -> list[str]:
    raw = value.get("section_order")
    if not isinstance(raw, (list, tuple)):
        return list(DEFAULT_REPORT_SECTION_ORDER)

    allowed = set(REPORT_SECTION_OPTIONS)
    ordered = list(dict.fromkeys(str(item).strip() for item in raw if str(item).strip() in allowed))
    ordered.extend(section for section in DEFAULT_REPORT_SECTION_ORDER if section not in ordered)
    return ordered

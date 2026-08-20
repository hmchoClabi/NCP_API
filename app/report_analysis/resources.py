"""Compare trustworthy adjacent monthly infrastructure snapshots."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from app.report_models import ReportResult
from app.report_options import (
    NETWORK_CONFIGURATION_CATEGORY_OPTIONS,
    REPORT_OPTIONS_SCHEMA_VERSION,
    RESOURCE_CATEGORY_LABELS,
    validate_report_options,
)

from .provenance import CALCULATED, UNAVAILABLE
from .support import field, mapping, normalize_period_type


_EXCLUDED_CATEGORIES = frozenset(NETWORK_CONFIGURATION_CATEGORY_OPTIONS)
_KNOWN_INVENTORY_CATEGORIES = frozenset(RESOURCE_CATEGORY_LABELS) | {
    "TARGET_GROUP"
}
_KST = ZoneInfo("Asia/Seoul")
_COMPLETE_SNAPSHOT_STATES = {
    "COMPLETE_FOR_SELECTED_SCOPE",
    "COMPLETE_FOR_SNAPSHOT_SCOPE",
}
_CHANGE_ORDER = {"CREATED": 0, "REMOVED": 1, "SPEC_CHANGED": 2}

# Only provider fields that describe provisioned capacity or configuration are
# compared. Runtime usage, status and connection data intentionally stay out.
_SPEC_FIELDS: dict[
    str,
    tuple[tuple[str, str, tuple[str, ...]], ...],
] = {
    "SERVER": (
        ("product", "상품", ("server_product_code", "server_product_name")),
        ("cpu_count", "vCPU", ("cpu_count",)),
        ("memory_gb", "메모리(GB)", ("memory_gb",)),
    ),
    "LOAD_BALANCER": (
        ("load_balancer_type", "유형", ("load_balancer_type",)),
        ("network_type", "네트워크 유형", ("network_type",)),
        ("throughput_type", "처리량 등급", ("throughput_type",)),
    ),
    "BLOCK_STORAGE": (
        ("volume_type", "볼륨 유형", ("volume_type", "disk_type")),
        ("size_gb", "용량(GB)", ("size_gb", "storage_size_gb")),
        ("iops", "IOPS", ("iops",)),
        ("throughput_mbps", "처리량(MB/s)", ("throughput_mbps",)),
    ),
    "NAS": (
        ("protocol", "프로토콜", ("protocol",)),
        ("size_gb", "용량(GB)", ("size_gb", "storage_size_gb")),
    ),
    "CLOUD_DB": (
        ("engine", "엔진", ("engine",)),
        ("generation", "세대", ("generation",)),
        ("server_count", "서버 수", ("server_count",)),
        ("cpu_count_total", "총 vCPU", ("cpu_count_total",)),
        ("memory_gb_total", "총 메모리(GB)", ("memory_gb_total",)),
        (
            "data_storage_gb_total",
            "데이터 용량(GB)",
            ("data_storage_gb_total",),
        ),
        ("high_availability", "고가용성", ("high_availability",)),
    ),
    "KUBERNETES": (
        ("kubernetes_version", "Kubernetes 버전", ("kubernetes_version",)),
        ("cluster_type", "클러스터 유형", ("cluster_type",)),
        ("node_count", "노드 수", ("node_count",)),
        ("node_max_count", "최대 노드 수", ("node_max_count",)),
        ("node_pool_count", "노드풀 수", ("node_pool_count",)),
    ),
    "VPC": (("ipv4_cidr_block", "주소 범위", ("ipv4_cidr_block",)),),
    "SUBNET": (
        ("ipv4_cidr_block", "주소 범위", ("ipv4_cidr_block",)),
        (
            "subnet_type",
            "Subnet 유형",
            ("subnet_type", "supported_subnet_type"),
        ),
    ),
    "NAT_GATEWAY": (("gateway_type", "Gateway 유형", ("gateway_type",)),),
    "VPC_PEERING": (
        ("source_vpc_no", "요청 VPC", ("source_vpc_no",)),
        ("target_vpc_no", "수락 VPC", ("target_vpc_no",)),
    ),
    "BLOCK_STORAGE_SNAPSHOT": (
        (
            "snapshot_volume_size_gb",
            "스냅샷 용량(GB)",
            ("snapshot_volume_size_gb",),
        ),
    ),
    "SERVER_IMAGE": (
        (
            "block_storage_size_gb",
            "이미지 용량(GB)",
            ("block_storage_size_gb",),
        ),
    ),
    "GLOBAL_DNS": (
        ("dnssec_enabled", "DNSSEC", ("dnssec_enabled",)),
    ),
}

_SPEC_VALUE_KINDS = {
    ("SERVER", "cpu_count"): "number",
    ("SERVER", "memory_gb"): "number",
    ("LOAD_BALANCER", "load_balancer_type"): "enum",
    ("LOAD_BALANCER", "network_type"): "enum",
    ("LOAD_BALANCER", "throughput_type"): "enum",
    ("BLOCK_STORAGE", "volume_type"): "enum",
    ("BLOCK_STORAGE", "size_gb"): "number",
    ("BLOCK_STORAGE", "iops"): "number",
    ("BLOCK_STORAGE", "throughput_mbps"): "number",
    ("NAS", "protocol"): "enum",
    ("NAS", "size_gb"): "number",
    ("CLOUD_DB", "engine"): "enum",
    ("CLOUD_DB", "generation"): "enum",
    ("CLOUD_DB", "server_count"): "number",
    ("CLOUD_DB", "cpu_count_total"): "number",
    ("CLOUD_DB", "memory_gb_total"): "number",
    ("CLOUD_DB", "data_storage_gb_total"): "number",
    ("CLOUD_DB", "high_availability"): "boolean",
    ("KUBERNETES", "kubernetes_version"): "enum",
    ("KUBERNETES", "cluster_type"): "enum",
    ("KUBERNETES", "node_count"): "number",
    ("KUBERNETES", "node_max_count"): "number",
    ("KUBERNETES", "node_pool_count"): "number",
    ("SUBNET", "subnet_type"): "enum",
    ("NAT_GATEWAY", "gateway_type"): "enum",
    ("BLOCK_STORAGE_SNAPSHOT", "snapshot_volume_size_gb"): "number",
    ("SERVER_IMAGE", "block_storage_size_gb"): "number",
    ("GLOBAL_DNS", "dnssec_enabled"): "boolean",
}


def analyze_resource_changes(
    report: Any,
    baseline: Any = None,
) -> dict[str, Any]:
    """Return resource changes only when both snapshots are comparable."""
    current_period = _monthly_period(report)
    if current_period is None:
        return _empty_result(
            "NOT_APPLICABLE",
            "MONTHLY_REPORT_REQUIRED",
            "자원 변화 비교는 전체 월간 보고서에만 적용됩니다.",
        )

    current_options = _options(report)
    if current_options is None:
        return _empty_result(
            "UNAVAILABLE",
            "OPTIONS_UNAVAILABLE",
            "현재 보고서의 선택 자원 범위를 확인할 수 없어 비교하지 않았습니다.",
        )
    if "infrastructure_inventory" not in current_options["sections"]:
        return _empty_result(
            "NOT_REQUESTED",
            "INFRASTRUCTURE_NOT_REQUESTED",
            "자원 현황이 선택되지 않아 자원 변화를 비교하지 않았습니다.",
        )
    if baseline is None:
        return _empty_result(
            "UNAVAILABLE",
            "BASELINE_UNAVAILABLE",
            "비교할 이전 월 보고서가 없습니다.",
        )

    baseline_period = _monthly_period(baseline)
    if baseline_period is None:
        return _empty_result(
            "UNAVAILABLE",
            "BASELINE_NOT_MONTHLY",
            "이전 보고서가 전체 월간 기간이 아니어서 비교하지 않았습니다.",
        )
    if baseline_period[1] + timedelta(days=1) != current_period[0]:
        return _empty_result(
            "UNAVAILABLE",
            "BASELINE_NOT_ADJACENT",
            "직전 월 보고서가 아니어서 자원 변화를 비교하지 않았습니다.",
        )

    current_schema = _schema_version(report)
    baseline_schema = _schema_version(baseline)
    if not (
        current_schema
        == baseline_schema
        == ReportResult.SCHEMA_VERSION
    ):
        return _empty_result(
            "UNAVAILABLE",
            "SCHEMA_MISMATCH",
            "보고서 데이터 형식이 달라 자원 변화를 비교하지 않았습니다.",
        )

    baseline_options = _options(baseline)
    if baseline_options is None:
        return _empty_result(
            "UNAVAILABLE",
            "OPTIONS_UNAVAILABLE",
            "이전 보고서의 선택 자원 범위를 확인할 수 없어 비교하지 않았습니다.",
        )
    current_scope = set(current_options["resource_categories"])
    baseline_scope = set(baseline_options["resource_categories"])
    if current_scope != baseline_scope:
        return _empty_result(
            "UNAVAILABLE",
            "RESOURCE_SCOPE_MISMATCH",
            "현재 월과 이전 월의 선택 자원 범위가 달라 비교하지 않았습니다.",
        )

    comparable_scope = current_scope - _EXCLUDED_CATEGORIES
    if not comparable_scope:
        return _empty_result(
            "NOT_REQUESTED",
            "NO_COMPARABLE_RESOURCE_SCOPE",
            "선택 범위에 월간 비교를 지원하는 자원이 없습니다.",
        )

    if not _complete_snapshot(
        report,
        comparable_scope,
    ) or not _complete_snapshot(baseline, comparable_scope):
        return _empty_result(
            "PARTIAL",
            "SNAPSHOT_INCOMPLETE",
            "두 월 중 하나의 자원 스냅샷이 불완전해 변화 수치를 확정하지 않았습니다.",
        )

    spec_scope = comparable_scope & set(_SPEC_FIELDS)
    current_resources, current_error = _resource_index(
        report,
        comparable_scope,
        spec_scope,
    )
    baseline_resources, baseline_error = _resource_index(
        baseline,
        comparable_scope,
        spec_scope,
    )
    snapshot_errors = {current_error, baseline_error}
    snapshot_error = (
        "MALFORMED_SNAPSHOT"
        if "MALFORMED_SNAPSHOT" in snapshot_errors
        else current_error or baseline_error
    )
    if snapshot_error:
        malformed = snapshot_error == "MALFORMED_SNAPSHOT"
        return _empty_result(
            "PARTIAL",
            snapshot_error,
            (
                "자원 스냅샷 구조가 올바르지 않아 변화 수치를 확정하지 않았습니다."
                if malformed
                else "일부 자원의 식별자가 중복되어 변화 수치를 확정하지 않았습니다."
            ),
        )

    items: list[dict[str, Any]] = []
    current_keys = set(current_resources)
    baseline_keys = set(baseline_resources)
    for identity in current_keys - baseline_keys:
        items.append(_change_item("CREATED", current_resources[identity]))
    for identity in baseline_keys - current_keys:
        items.append(_change_item("REMOVED", baseline_resources[identity]))
    for identity in current_keys & baseline_keys:
        if identity[0] not in spec_scope:
            continue
        changed_fields = _changed_fields(
            baseline_resources[identity],
            current_resources[identity],
        )
        if changed_fields:
            items.append(_change_item(
                "SPEC_CHANGED",
                current_resources[identity],
                changed_fields=changed_fields,
            ))

    items.sort(key=lambda item: (
        _CHANGE_ORDER[item["change_type"]],
        item["category"],
        str(item.get("resource_name") or "").casefold(),
        item["platform"],
        item["resource_id"],
    ))
    return {
        "status": "AVAILABLE",
        "source_state": CALCULATED,
        "reason_code": None,
        "message": (
            "생성·제거는 동일 범위 자원을 비교했고, 스펙 변경은 "
            "명시된 지원 범주와 필드만 비교했습니다."
        ),
        "baseline_period_start": baseline_period[0].isoformat(),
        "baseline_period_end": baseline_period[1].isoformat(),
        "lifecycle_compared_categories": sorted(comparable_scope),
        "spec_compared_categories": sorted(spec_scope),
        "lifecycle_only_categories": sorted(
            comparable_scope - spec_scope
        ),
        "created_count": sum(
            item["change_type"] == "CREATED" for item in items
        ),
        "removed_count": sum(
            item["change_type"] == "REMOVED" for item in items
        ),
        "spec_changed_count": sum(
            item["change_type"] == "SPEC_CHANGED" for item in items
        ),
        "items": items,
    }


def _monthly_period(report: Any) -> tuple[date, date] | None:
    period = mapping(field(report, "period", {}))
    if normalize_period_type(period.get("period_type")) != "MONTHLY":
        return None
    start_dt = _kst_datetime(period.get("start_dt"))
    end_dt = _kst_datetime(period.get("end_dt"))
    start_boundary = (
        start_dt.hour,
        start_dt.minute,
        start_dt.second,
        start_dt.microsecond,
    ) if start_dt is not None else None
    end_boundary = (
        end_dt.hour,
        end_dt.minute,
        end_dt.second,
        end_dt.microsecond,
    ) if end_dt is not None else None
    if (
        start_dt is None
        or end_dt is None
        or start_boundary != (0, 0, 0, 0)
        or end_boundary != (23, 59, 59, 0)
        or (
            "is_full_month" in period
            and period.get("is_full_month") is not True
        )
    ):
        return None
    start = start_dt.date()
    end = end_dt.date()
    if start.day != 1:
        return None
    next_month = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return (start, end) if end == next_month - timedelta(days=1) else None


def _kst_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=_KST)
    return parsed.astimezone(_KST)


def _options(report: Any) -> dict[str, Any] | None:
    raw_options = field(report, "report_options", None)
    if (
        not isinstance(raw_options, Mapping)
        or str(raw_options.get("schema_version") or "").strip()
        != REPORT_OPTIONS_SCHEMA_VERSION
    ):
        return None
    try:
        normalized = validate_report_options(raw_options)
    except (TypeError, ValueError):
        return None

    # Validation normalizes through allowlists.  Reject, rather than silently
    # dropping, any persisted scope token that the current schema cannot read.
    for key in ("sections", "resource_categories", "monitoring_categories"):
        raw_values = raw_options.get(key)
        if not isinstance(raw_values, (list, tuple, set)) or any(
            not isinstance(value, str) or not value.strip()
            for value in raw_values
        ):
            return None
        if {value.strip() for value in raw_values} != set(normalized[key]):
            return None
    return normalized


def _schema_version(report: Any) -> str:
    return str(
        field(report, "schema_version", None)
        or field(report, "SCHEMA_VERSION", "")
    ).strip()


def _complete_snapshot(
    report: Any,
    selected_scope: set[str],
) -> bool:
    metadata = mapping(field(report, "collection_metadata", {}))
    infrastructure = mapping(metadata.get("infrastructure"))
    raw_categories = infrastructure.get("collected_categories")
    if not isinstance(raw_categories, (list, tuple, set, frozenset)):
        return False
    collected_categories: set[str] = set()
    for value in raw_categories:
        if not isinstance(value, str):
            return False
        category = value.strip().upper()
        if category not in _KNOWN_INVENTORY_CATEGORIES:
            return False
        collected_categories.add(category)
    try:
        issue_count = int(infrastructure.get("collection_issue_count"))
    except (TypeError, ValueError, OverflowError):
        return False
    return (
        str(infrastructure.get("time_basis") or "").upper()
        == "REPORT_PERIOD"
        and str(
            infrastructure.get("inventory_completeness") or ""
        ).upper()
        in _COMPLETE_SNAPSHOT_STATES
        and issue_count == 0
        and selected_scope <= collected_categories
    )


def _resource_index(
    report: Any,
    selected_scope: set[str],
    spec_scope: set[str],
) -> tuple[dict[tuple[str, str, str], dict[str, Any]], str | None]:
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    inventory = field(report, "infrastructure", None)
    if not isinstance(inventory, (list, tuple)):
        return {}, "MALFORMED_SNAPSHOT"
    for resource in inventory:
        if not isinstance(resource, Mapping):
            return {}, "MALFORMED_SNAPSHOT"
        category = str(resource.get("category") or "").strip().upper()
        if category not in _KNOWN_INVENTORY_CATEGORIES:
            return {}, "MALFORMED_SNAPSHOT"
        if category not in selected_scope:
            continue
        resource_id = str(resource.get("resource_id") or "").strip()
        if not resource_id:
            return {}, "MALFORMED_SNAPSHOT"
        if category in spec_scope and not isinstance(
            resource.get("details"),
            Mapping,
        ):
            return {}, "MALFORMED_SNAPSHOT"
        platform = str(resource.get("platform") or "").strip().upper()
        if not platform:
            return {}, "MALFORMED_SNAPSHOT"
        identity = (category, platform, resource_id)
        if identity in result:
            return {}, "RESOURCE_IDENTITY_INCOMPLETE"
        result[identity] = dict(resource)
    return result, None


def _change_item(
    change_type: str,
    resource: Mapping[str, Any],
    *,
    changed_fields: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    category = str(resource.get("category") or "").strip().upper()
    return {
        "source_state": CALCULATED,
        "change_type": change_type,
        "category": category,
        "category_label": (
            resource.get("category_label")
            or RESOURCE_CATEGORY_LABELS.get(category)
            or category
        ),
        "platform": str(resource.get("platform") or "").strip().upper(),
        "resource_id": str(resource.get("resource_id") or "").strip(),
        "resource_name": (
            resource.get("resource_name")
            or resource.get("resource_id")
            or "-"
        ),
        "changed_fields": changed_fields or [],
    }


def _changed_fields(
    before_resource: Mapping[str, Any],
    after_resource: Mapping[str, Any],
) -> list[dict[str, Any]]:
    category = str(after_resource.get("category") or "").strip().upper()
    before = mapping(before_resource.get("details"))
    after = mapping(after_resource.get("details"))
    result = []
    for name, label, aliases in _SPEC_FIELDS.get(category, ()):
        before_present, before_value = _first_value(before, aliases)
        after_present, after_value = _first_value(after, aliases)
        if not before_present and not after_present:
            continue
        if _canonical_spec_value(
            category,
            name,
            before_value,
        ) == _canonical_spec_value(category, name, after_value):
            continue
        result.append({
            "field": name,
            "label": label,
            "before": _public_value(before_value),
            "after": _public_value(after_value),
        })
    return result


def _first_value(
    source: Mapping[str, Any],
    aliases: tuple[str, ...],
) -> tuple[bool, Any]:
    for alias in aliases:
        value = source.get(alias)
        if value not in (None, "", [], {}):
            return True, value
    return False, None


def _canonical_spec_value(category: str, name: str, value: Any) -> Any:
    kind = _SPEC_VALUE_KINDS.get((category, name))
    if kind == "number":
        if isinstance(value, bool):
            return _canonical(value)
        try:
            number = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            return _canonical(value)
        return (
            ("number", number.normalize())
            if number.is_finite()
            else _canonical(value)
        )
    if kind == "boolean":
        if isinstance(value, bool):
            return ("bool", value)
        normalized = str(value).strip().casefold()
        if normalized in {"1", "true", "yes", "y", "on", "enabled"}:
            return ("bool", True)
        if normalized in {"0", "false", "no", "n", "off", "disabled"}:
            return ("bool", False)
    return _canonical(value, casefold_text=kind == "enum")


def _canonical(value: Any, *, casefold_text: bool = False) -> Any:
    if value is None:
        return ("none",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, float, Decimal)):
        try:
            return ("number", Decimal(str(value)).normalize())
        except InvalidOperation:
            return ("text", str(value))
    if isinstance(value, Mapping):
        return (
            "mapping",
            tuple(sorted(
                (
                    str(key),
                    _canonical(item, casefold_text=casefold_text),
                )
                for key, item in value.items()
            )),
        )
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [
            _canonical(item, casefold_text=casefold_text)
            for item in value
        ]
        return (
            "collection",
            tuple(sorted(
                items,
                key=lambda item: json.dumps(item, default=str),
            )),
        )
    text = str(value).strip()
    return ("text", text.casefold() if casefold_text else text)


def _public_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _public_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_public_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_public_value(item) for item in value), key=str)
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral() else float(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _empty_result(status: str, reason_code: str, message: str) -> dict[str, Any]:
    return {
        "status": status,
        "source_state": UNAVAILABLE,
        "reason_code": reason_code,
        "message": message,
        "baseline_period_start": None,
        "baseline_period_end": None,
        "lifecycle_compared_categories": [],
        "spec_compared_categories": [],
        "lifecycle_only_categories": [],
        "created_count": None,
        "removed_count": None,
        "spec_changed_count": None,
        "items": [],
    }


__all__ = ["analyze_resource_changes"]

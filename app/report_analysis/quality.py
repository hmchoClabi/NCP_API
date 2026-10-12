"""수집 범위와 성공 여부를 데이터셋 단위로 판정한다."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import Finding
from .provenance import CALCULATED, dataset_source_state
from .support import field, flatten_records, mapping, records

DATASETS = (
    ("infrastructure", "인프라 자원", "infrastructure_inventory"),
    ("monitoring", "모니터링 지표", "monitoring"),
    ("insight_events", "Cloud Insight 이벤트", "insight_events"),
    ("activity_events", "변경 이력", "activity_history"),
    ("billing", "비용", "billing"),
    ("service_availability", "서비스 가용성", "service_availability"),
    ("security_events", "보안 이벤트", "security_events"),
)

STATUS_LABELS = {
    "AVAILABLE": "수집 완료",
    "COLLECTED_EMPTY": "수집 완료(0건)",
    "PARTIAL": "부분 수집",
    "FAILED": "수집 실패",
    "UNAVAILABLE": "판정 불가",
    "NOT_REQUESTED": "수집 대상 아님",
}

_STATUS_ALIASES = {
    "AVAILABLE": "AVAILABLE",
    "SUCCESS": "AVAILABLE",
    "SUCCEEDED": "AVAILABLE",
    "COLLECTED": "AVAILABLE",
    "EMPTY": "COLLECTED_EMPTY",
    "COLLECTED_EMPTY": "COLLECTED_EMPTY",
    "PARTIAL": "PARTIAL",
    "PARTIAL_SUCCESS": "PARTIAL",
    "ERROR": "FAILED",
    "FAILED": "FAILED",
    "FAILURE": "FAILED",
    "UNAVAILABLE": "UNAVAILABLE",
    "UNKNOWN": "UNAVAILABLE",
    "SKIPPED": "NOT_REQUESTED",
    "DISABLED": "NOT_REQUESTED",
    "NOT_REQUESTED": "NOT_REQUESTED",
}

_ISSUE_TOKENS = {
    "infrastructure": (
        "servercollector",
        "infrastructurecollector",
        "resource_manager",
        "resourcecollector",
        "network_configuration",
        "server",
        "infrastructure",
    ),
    "monitoring": (
        "insightmetric",
        "infrastructuremetric",
        "monitoring",
        "cloud_insight_metric",
    ),
    "insight_events": ("insightevent", "cloud_insight_event"),
    "activity_events": ("activitytracer", "activity_history"),
    "billing": ("billing",),
    "service_availability": (
        "wms",
        "webservicemonitor",
        "web_service_monitor",
    ),
    "security_events": ("securitymonitoring", "security_event"),
}


def analyze_data_quality(
    report: Any,
) -> tuple[dict[str, Any], list[Finding]]:
    """선택된 데이터셋마다 수집 완료·빈 결과·실패를 구분한다."""
    errors = records(field(report, "collection_errors", []))
    warnings = records(field(report, "collection_warnings", []))
    explicit = _explicit_statuses(report)
    requested_sections = _requested_sections(report)
    options_present = bool(mapping(field(report, "report_options", {})))

    datasets: list[dict[str, Any]] = []
    findings: list[Finding] = []
    for key, label, section in DATASETS:
        requested = _is_requested(
            key,
            section,
            requested_sections,
            options_present,
            report,
            explicit,
        )
        explicit_status = explicit.get(key)
        if explicit_status is not None:
            # 새 보고서는 runner가 데이터셋별 진단을 이미 분리해 기록한다.
            # 전역 오류의 부분 문자열을 다시 매칭하면 monitoring의
            # target_type=server가 infrastructure 오류로 중복 귀속된다.
            error_count = _non_negative_count(explicit_status.get("error_count"))
            warning_count = _non_negative_count(explicit_status.get("warning_count"))
        else:
            # 명시 상태가 없는 구형 스냅샷에만 보수적 휴리스틱을 쓴다.
            error_count = len(_related_issues(errors, key))
            warning_count = len(_related_issues(warnings, key))
        status, count, reason = _dataset_status(
            report=report,
            key=key,
            requested=requested,
            explicit=explicit_status,
            error_count=error_count,
            warning_count=warning_count,
        )
        dataset = {
            "key": key,
            "label": label,
            "status": status,
            "status_label": STATUS_LABELS[status],
            "record_count": count,
            "error_count": error_count,
            "warning_count": warning_count,
            "reason": reason,
            "source_state": dataset_source_state(status),
        }
        datasets.append(dataset)

        if status in {"FAILED", "PARTIAL", "UNAVAILABLE"}:
            findings.append(
                Finding(
                    rule_id=f"DATASET_{status}",
                    severity="WARNING",
                    category="DATA_QUALITY",
                    title=f"{label} 데이터가 완전하지 않습니다.",
                    evidence=[
                        {"label": "수집 상태", "value": STATUS_LABELS[status]},
                        {"label": "오류", "value": error_count, "unit": "건"},
                        {"label": "경고", "value": warning_count, "unit": "건"},
                    ],
                    impact=("해당 데이터에 의존하는 정상 여부와 추세를 확정할 수 없습니다."),
                    recommendation=(
                        "호출 API, 계정 권한, 수집 범위와 수집 시각을 확인한 뒤 다시 수집하세요."
                    ),
                    resource={"id": key, "name": label, "type": "DATASET"},
                )
            )

    requested = [item for item in datasets if item["status"] != "NOT_REQUESTED"]
    if not requested:
        overall = "UNKNOWN"
    elif any(item["status"] == "FAILED" for item in requested):
        overall = "FAILED"
    elif any(item["status"] in {"PARTIAL", "UNAVAILABLE"} for item in requested):
        overall = "PARTIAL"
    else:
        overall = "COMPLETE"

    counts = {
        status.casefold(): sum(item["status"] == status for item in datasets)
        for status in STATUS_LABELS
    }
    return {
        "overall_status": overall,
        "source_state": CALCULATED,
        "datasets": datasets,
        "counts": counts,
    }, findings


def dataset_status(quality: Mapping[str, Any], key: str) -> str:
    for item in quality.get("datasets") or []:
        if isinstance(item, Mapping) and item.get("key") == key:
            return str(item.get("status") or "UNAVAILABLE")
    return "UNAVAILABLE"


def _requested_sections(report: Any) -> set[str]:
    options = mapping(field(report, "report_options", {}))
    raw = options.get("sections")
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return set()
    return {str(item) for item in raw}


def _is_requested(
    key: str,
    section: str,
    requested_sections: set[str],
    options_present: bool,
    report: Any,
    explicit: Mapping[str, dict[str, Any]],
) -> bool:
    if key in explicit:
        return explicit[key].get("status") != "NOT_REQUESTED"
    if key == "billing" and "organization_billing" in requested_sections:
        return True
    if section in requested_sections:
        return True
    if key in {"service_availability", "security_events"}:
        return _has_field(report, _source_field(key))
    return not options_present


def _dataset_status(
    *,
    report: Any,
    key: str,
    requested: bool,
    explicit: dict[str, Any] | None,
    error_count: int,
    warning_count: int,
) -> tuple[str, int | None, str]:
    count = _record_count(report, key)
    if not requested:
        return "NOT_REQUESTED", None, "보고서 설정에서 수집하지 않도록 선택되었습니다."

    if explicit:
        status = explicit["status"]
        explicit_count = explicit.get("record_count")
        if isinstance(explicit_count, int) and not isinstance(explicit_count, bool):
            count = explicit_count
        # 수집기가 성공 상태를 기록했더라도 같은 데이터셋에 진단이
        # 남아 있으면 완전 수집으로 승격하지 않는다.
        if status in {"AVAILABLE", "COLLECTED_EMPTY"} and error_count:
            status = "PARTIAL" if count else "FAILED"
        elif status in {"AVAILABLE", "COLLECTED_EMPTY"} and warning_count:
            status = "PARTIAL"
        reason = str(
            explicit.get("reason")
            if status == explicit["status"]
            else "관련 수집 진단이 있어 부분 수집으로 판정했습니다."
        )
        if not reason:
            reason = STATUS_LABELS[status]
        return status, count, reason

    if error_count:
        status = "PARTIAL" if count else "FAILED"
        return status, count, "관련 수집 오류가 기록되었습니다."
    if warning_count:
        status = "PARTIAL"
        return status, count, "관련 수집 경고가 기록되었습니다."
    if count:
        return "AVAILABLE", count, "사용 가능한 수집 데이터가 있습니다."
    # ReportResult의 빈 기본값만으로 API 호출 성공을 증명할 수 없다. 0건은
    # collector가 dataset_statuses에 COLLECTED_EMPTY를 기록한 경우에만 쓴다.
    return "UNAVAILABLE", None, "수집 성공과 0건을 구분할 상태 근거가 없습니다."


def _explicit_statuses(report: Any) -> dict[str, dict[str, Any]]:
    metadata = mapping(field(report, "collection_metadata", {}))
    raw = field(report, "dataset_statuses", None)
    if raw is None:
        raw = metadata.get("dataset_statuses")
    result: dict[str, dict[str, Any]] = {}

    if isinstance(raw, Mapping):
        items = raw.items()
    elif isinstance(raw, (list, tuple)):
        items = (
            (item.get("key") or item.get("dataset"), item)
            for item in raw
            if isinstance(item, Mapping)
        )
    else:
        return result

    for raw_key, raw_value in items:
        key = str(raw_key or "").strip()
        if not key:
            continue
        value = dict(raw_value) if isinstance(raw_value, Mapping) else {"status": raw_value}
        status = _STATUS_ALIASES.get(str(value.get("status") or "").strip().upper())
        if status:
            result[key] = {**value, "status": status}
    return result


def _related_issues(issues: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    tokens = _ISSUE_TOKENS[key]
    result = []
    for issue in issues:
        haystack = " ".join(
            str(issue.get(name) or "").casefold()
            for name in (
                "collector",
                "target_type",
                "category",
                "service_name",
                "api",
                "source",
            )
        )
        if any(token in haystack for token in tokens):
            result.append(issue)
    return result


def _non_negative_count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(int(value), 0)
    except (TypeError, ValueError, OverflowError):
        return 0


def _record_count(report: Any, key: str) -> int:
    if key == "infrastructure":
        return len(records(field(report, "infrastructure", []))) or len(
            records(field(report, "servers", []))
        )
    if key == "monitoring":
        return monitoring_observation_count(
            field(report, "server_metrics", []),
            field(report, "infrastructure_metrics", []),
        )
    if key == "insight_events":
        return len(records(field(report, "insight_events", [])))
    if key == "activity_events":
        return len(flatten_records(field(report, "activity_events", [])))
    if key == "billing":
        billing = mapping(field(report, "billing", {}))
        return sum(
            isinstance(value, Mapping) and str(value.get("status") or "").upper() == "AVAILABLE"
            for name, value in billing.items()
            if name
            in {
                "invoice_summary",
                "period_estimate",
                "month_to_date_estimate",
                "month_end_projection",
            }
        )
    if key == "security_events":
        security = mapping(field(report, "security_monitoring", {}))
        return len(records(security.get("events")))
    if key == "service_availability":
        availability = mapping(field(report, "service_availability", {}))
        return len(records(availability.get("scenarios")))
    return len(records(field(report, _source_field(key), [])))


def monitoring_observation_count(
    server_metrics: Any,
    infrastructure_metrics: Any,
) -> int:
    count = 0
    for metric in records(server_metrics):
        raw_metrics = metric.get("raw_metrics")
        if isinstance(raw_metrics, Mapping):
            for stats in raw_metrics.values():
                if not isinstance(stats, Mapping):
                    continue
                for entries in stats.values():
                    for entry in records(entries):
                        raw = entry.get("raw")
                        if isinstance(raw, Mapping) and isinstance(raw.get("dps"), list):
                            count += len(raw["dps"])
                        elif isinstance(entry.get("values"), list):
                            count += len(entry["values"])
    for group in records(infrastructure_metrics):
        for series in records(group.get("series")):
            if isinstance(series.get("points"), list):
                count += len(series["points"])
    return count


def _source_field(key: str) -> str:
    return "security_monitoring" if key == "security_events" else key


def _has_field(source: Any, name: str) -> bool:
    if isinstance(source, Mapping):
        return name in source
    return hasattr(source, name)


__all__ = [
    "analyze_data_quality",
    "dataset_status",
    "monitoring_observation_count",
]

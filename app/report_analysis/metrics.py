"""원시 시계열에서 성능 요약과 지속 시간 기반 판정을 만든다."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional

from app.report_options import (
    UTILIZATION_ALERT_MAX_PERCENT,
    UTILIZATION_ALERT_MIN_PERCENT,
    UTILIZATION_CRITICAL_PERCENT,
    UTILIZATION_MAX_SUSTAINED_MINUTES,
    UTILIZATION_MIN_SUSTAINED_MINUTES,
    UTILIZATION_SUSTAINED_MINUTES,
)

from .models import Finding
from .provenance import CALCULATED, UNAVAILABLE
from .support import (
    field,
    infer_interval_seconds,
    interval_seconds,
    number,
    percentile,
    records,
    rounded,
)


DEFAULT_THRESHOLDS: dict[str, dict[str, float]] = {
    "CPU": {
        "warning": UTILIZATION_ALERT_MIN_PERCENT,
        "critical": UTILIZATION_CRITICAL_PERCENT,
        "duration_seconds": UTILIZATION_SUSTAINED_MINUTES * 60.0,
    },
    "MEMORY": {
        "warning": UTILIZATION_ALERT_MIN_PERCENT,
        "critical": UTILIZATION_CRITICAL_PERCENT,
        "duration_seconds": UTILIZATION_SUSTAINED_MINUTES * 60.0,
    },
    "FILESYSTEM": {
        "warning": UTILIZATION_ALERT_MIN_PERCENT,
        "critical": UTILIZATION_CRITICAL_PERCENT,
        "duration_seconds": UTILIZATION_SUSTAINED_MINUTES * 60.0,
    },
}

_SERVER_METRIC_KIND = {
    "used_rto": "CPU",
    "cpu": "CPU",
    "cpu_used_ratio": "CPU",
    "mem_usert": "MEMORY",
    "memory": "MEMORY",
    "memory_used_ratio": "MEMORY",
    "fs_usert": "FILESYSTEM",
    "filesystem": "FILESYSTEM",
    "disk_used_ratio": "FILESYSTEM",
}

_PERCENT_METRIC_TOKENS = {
    "CPU": ("cpu", "used_rto", "unit_utilization", "used_v_cores_percent"),
    "MEMORY": (
        "mem_pct",
        "mem_usage",
        "mem_usert",
        "memory_ratio",
        "memory_usage",
        "used_memory_percent",
    ),
    "FILESYSTEM": (
        "disk_data_pct",
        "fs_usert",
        "disk_used_ratio",
        "volume_used_ratio",
        "disk_mysql_used_ratio",
        "storage_used_ratio",
        "storage_usage_percent",
    ),
}

_NON_USAGE_METRIC_TOKENS = ("available", "free", "idle")


def analyze_metrics(
    report: Any,
    policy: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[Finding]]:
    thresholds = _thresholds(policy)
    series = _server_series(report) + _infrastructure_series(report)
    summaries: list[dict[str, Any]] = []
    findings: list[Finding] = []

    for item in series:
        points = item["points"]
        values = [point[1] for point in points]
        if not values:
            continue
        interval = item.get("interval_seconds") or infer_interval_seconds(points)
        item_summary = {
            "source_state": CALCULATED,
            "category": item["category"],
            "resource_id": item.get("resource_id"),
            "resource_name": item.get("resource_name"),
            "metric": item["metric"],
            "metric_label": item.get("metric_label") or item["metric"],
            "metric_kind": item.get("kind"),
            "unit": item.get("unit"),
            "aggregation": item.get("aggregation"),
            "sample_count": len(values),
            "average": rounded(sum(values) / len(values)),
            "p95": rounded(percentile(values, 0.95)),
            "maximum": rounded(max(values)),
            "interval_seconds": interval,
        }
        kind = item.get("kind")
        if (
            kind in thresholds
            and interval
            # A daily aggregate does not prove continuous threshold duration.
            and interval < interval_seconds("Day1")
            and item.get("alert_eligible", False)
        ):
            rule = thresholds[kind]
            warning_duration = _longest_threshold_duration(
                points,
                threshold=rule["warning"],
                expected_interval_seconds=interval,
            )
            critical_duration = _longest_threshold_duration(
                points,
                threshold=rule["critical"],
                expected_interval_seconds=interval,
            )
            item_summary.update({
                "warning_threshold": rule["warning"],
                "critical_threshold": rule["critical"],
                "warning_duration_seconds": warning_duration,
                "critical_duration_seconds": critical_duration,
            })
            finding = _threshold_finding(
                item,
                item_summary,
                kind,
                required_duration=rule["duration_seconds"],
            )
            if finding:
                item_summary.update({
                    "alert_severity": finding.severity,
                    "alert_threshold": (
                        rule["critical"]
                        if finding.severity == "CRITICAL"
                        else rule["warning"]
                    ),
                    "alert_duration_seconds": (
                        critical_duration
                        if finding.severity == "CRITICAL"
                        else warning_duration
                    ),
                })
                findings.append(finding)
        summaries.append(item_summary)

    summaries.sort(
        key=lambda item: (
            str(item.get("category") or ""),
            str(item.get("resource_name") or ""),
            str(item.get("metric") or ""),
        )
    )
    return {
        "status": "AVAILABLE" if summaries else "UNAVAILABLE",
        "source_state": CALCULATED if summaries else UNAVAILABLE,
        "series_count": len(summaries),
        "summaries": summaries,
    }, findings


def _server_series(report: Any) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for server in records(field(report, "server_metrics", [])):
        raw_metrics = server.get("raw_metrics")
        if not isinstance(raw_metrics, Mapping):
            continue
        metric_interval = interval_seconds(server.get("metric_interval"))
        for metric_name, raw_stats in raw_metrics.items():
            if not isinstance(raw_stats, Mapping):
                continue
            # AVG 시계열이 운영 임계치 판정에 가장 적합하다. 없는 경우에만
            # 다른 통계 시계열을 사용하며 동일 dps를 중복 계산하지 않는다.
            entries = []
            selected_stat_name = ""
            for stat_name in ("avg", "min", "max"):
                entries = records(raw_stats.get(stat_name))
                if entries:
                    selected_stat_name = stat_name
                    break
            for entry in entries:
                points = _entry_points(entry)
                if not points:
                    continue
                dimensions = entry.get("dimensions")
                resource_name = str(server.get("server_name") or "-")
                if isinstance(dimensions, Mapping) and dimensions.get("mnt_nm"):
                    resource_name += f" · {dimensions['mnt_nm']}"
                normalized_name = str(metric_name).strip().casefold()
                metric_kind = _SERVER_METRIC_KIND.get(normalized_name)
                dimension_key = tuple(
                    sorted(
                        (str(name), str(value))
                        for name, value in (
                            dimensions.items()
                            if isinstance(dimensions, Mapping)
                            else []
                        )
                    )
                )
                key = (
                    str(server.get("server_id") or ""),
                    str(metric_name),
                    dimension_key,
                )
                series = grouped.setdefault(key, {
                    "category": "SERVER",
                    "resource_id": str(server.get("server_id") or ""),
                    "resource_name": resource_name,
                    "metric": str(metric_name),
                    "metric_label": _metric_label(
                        metric_kind,
                        str(metric_name),
                    ),
                    "kind": metric_kind,
                    "alert_eligible": (
                        selected_stat_name in {"avg", "min"}
                    ),
                    "unit": "%" if normalized_name in _SERVER_METRIC_KIND else None,
                    "aggregation": selected_stat_name.upper() or None,
                    "interval_seconds": metric_interval,
                    "points_by_time": {},
                })
                series["points_by_time"].update(dict(points))
    result = []
    for series in grouped.values():
        points_by_time = series.pop("points_by_time")
        series["points"] = sorted(points_by_time.items())
        result.append(series)
    return result


def _infrastructure_series(report: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for group in records(field(report, "infrastructure_metrics", [])):
        metric = str(group.get("metric") or "")
        unit = str(group.get("unit") or "")
        aggregation = str(group.get("aggregation") or "").strip().upper()
        metric_kind = _infrastructure_metric_kind(metric, unit)
        expected_interval = interval_seconds(group.get("interval"))
        for series in records(group.get("series")):
            points = _normalize_points(series.get("points"))
            if not points:
                continue
            result.append({
                "category": str(group.get("category") or "INFRASTRUCTURE"),
                "resource_id": str(series.get("resource_id") or ""),
                "resource_name": str(series.get("resource_name") or "-"),
                "metric": metric,
                "metric_label": str(group.get("metric_label") or metric),
                "kind": metric_kind,
                "alert_eligible": aggregation in {"AVG", "MIN"},
                "unit": unit or None,
                "aggregation": aggregation or None,
                "interval_seconds": expected_interval,
                "points": points,
            })
    return result


def _entry_points(entry: Mapping[str, Any]) -> list[tuple[int, float]]:
    raw = entry.get("raw")
    if isinstance(raw, Mapping):
        points = _normalize_points(raw.get("dps"))
        if points:
            return points
    # 과거 스냅샷 중 시각을 버리고 값만 저장한 형식은 p95 계산에는 쓸 수
    # 있지만 지속 시간을 만들면 안 된다. 분석기는 가상 시각을 만들지 않는다.
    return []


def _normalize_points(value: Any) -> list[tuple[int, float]]:
    if not isinstance(value, (list, tuple)):
        return []
    result: dict[int, float] = {}
    for point in value:
        raw_timestamp = raw_value = None
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            raw_timestamp, raw_value = point[0], point[1]
        elif isinstance(point, Mapping):
            raw_timestamp = point.get("timestamp", point.get("time"))
            raw_value = point.get("value")
        # Cloud Insight dps의 첫 값은 API 계약상 epoch milliseconds이다.
        raw_time_number = number(raw_timestamp)
        timestamp = int(raw_time_number) if raw_time_number is not None else None
        parsed_value = number(raw_value)
        if timestamp is not None and parsed_value is not None:
            result[timestamp] = parsed_value
    return sorted(result.items())


def _longest_threshold_duration(
    points: list[tuple[int, float]],
    *,
    threshold: float,
    expected_interval_seconds: int,
) -> int:
    """1.5배보다 큰 관측 공백을 이어 붙이지 않고 최대 지속 시간을 구한다."""
    if not points or expected_interval_seconds <= 0:
        return 0
    allowed_gap_ms = expected_interval_seconds * 1000 * 1.5
    longest = current = 0
    previous_timestamp: Optional[int] = None
    for timestamp, value in points:
        gap_ok = (
            previous_timestamp is not None
            and timestamp > previous_timestamp
            and timestamp - previous_timestamp <= allowed_gap_ms
        )
        if value >= threshold:
            current = current + expected_interval_seconds if gap_ok else expected_interval_seconds
            longest = max(longest, current)
        else:
            current = 0
        previous_timestamp = timestamp
    return int(longest)


def _threshold_finding(
    series: Mapping[str, Any],
    summary: Mapping[str, Any],
    kind: str,
    *,
    required_duration: float,
) -> Optional[Finding]:
    critical_duration = number(summary.get("critical_duration_seconds")) or 0
    warning_duration = number(summary.get("warning_duration_seconds")) or 0
    if critical_duration >= required_duration:
        severity = "CRITICAL"
        threshold = summary.get("critical_threshold")
        observed_duration = critical_duration
    elif warning_duration >= required_duration:
        severity = "WARNING"
        threshold = summary.get("warning_threshold")
        observed_duration = warning_duration
    else:
        return None

    resource_name = str(series.get("resource_name") or "-")
    label = str(series.get("metric_label") or series.get("metric") or kind)
    evidence = [
        {"label": "임계치", "value": threshold, "unit": "%"},
        {
            "label": "최대 연속 지속 시간",
            "value": int(observed_duration),
            "unit": "초",
        },
        {
            "label": "P95",
            "value": summary.get("p95"),
            "unit": series.get("unit"),
        },
        {
            "label": "최댓값",
            "value": summary.get("maximum"),
            "unit": series.get("unit"),
        },
    ]
    if series.get("aggregation"):
        evidence.insert(0, {
            "label": "집계 방식",
            "value": series.get("aggregation"),
        })
    return Finding(
        rule_id=f"METRIC_{kind}_SUSTAINED",
        severity=severity,
        category="PERFORMANCE",
        title=f"{resource_name}의 {label} 임계치 초과가 지속되었습니다.",
        evidence=evidence,
        impact="자원 포화가 지속되면 응답 지연 또는 서비스 불안정으로 이어질 수 있습니다.",
        recommendation="해당 시간대의 워크로드와 이벤트를 확인하고 자원 증설 또는 부하 분산을 검토하세요.",
        resource={
            "id": series.get("resource_id"),
            "name": resource_name,
            "type": series.get("category"),
        },
    )


def _thresholds(policy: Mapping[str, Any] | None) -> dict[str, dict[str, float]]:
    result = {kind: dict(values) for kind, values in DEFAULT_THRESHOLDS.items()}
    if not isinstance(policy, Mapping):
        return result
    raw = policy.get("thresholds")
    if not isinstance(raw, Mapping):
        return result

    # 포털 설정은 평면 키를 사용한다. 내부 규칙 모델로 변환해 수집기나 UI가
    # 분석 엔진의 구조에 종속되지 않게 한다.
    flat_mapping = {
        "CPU": ("cpu_warning_percent", "cpu_critical_percent"),
        "MEMORY": ("memory_warning_percent", "memory_critical_percent"),
        "FILESYSTEM": ("disk_warning_percent", "disk_critical_percent"),
    }
    sustained_minutes = number(raw.get("sustained_minutes"))
    for kind, (warning_name, critical_name) in flat_mapping.items():
        warning = number(raw.get(warning_name))
        critical = number(raw.get(critical_name))
        if warning is not None and warning >= 0:
            result[kind]["warning"] = _bounded_utilization_percent(
                warning
            )
        if critical is not None and critical >= 0:
            result[kind]["critical"] = _bounded_utilization_percent(
                critical
            )
        if sustained_minutes is not None and sustained_minutes >= 0:
            result[kind]["duration_seconds"] = _bounded_duration_seconds(
                sustained_minutes * 60
            )
    for raw_kind, raw_values in raw.items():
        kind = str(raw_kind).upper()
        if kind not in result or not isinstance(raw_values, Mapping):
            continue
        for name in ("warning", "critical", "duration_seconds"):
            parsed = number(raw_values.get(name))
            if parsed is not None and parsed >= 0:
                if name in {"warning", "critical"}:
                    result[kind][name] = _bounded_utilization_percent(
                        parsed
                    )
                else:
                    result[kind][name] = _bounded_duration_seconds(
                        parsed
                    )
    for values in result.values():
        if values["critical"] < values["warning"]:
            values["critical"] = values["warning"]
    return result


def _bounded_utilization_percent(value: float) -> float:
    return min(
        UTILIZATION_ALERT_MAX_PERCENT,
        max(UTILIZATION_ALERT_MIN_PERCENT, value),
    )


def _bounded_duration_seconds(value: float) -> float:
    return min(
        UTILIZATION_MAX_SUSTAINED_MINUTES * 60,
        max(UTILIZATION_MIN_SUSTAINED_MINUTES * 60, value),
    )


def _infrastructure_metric_kind(metric: str, unit: str) -> Optional[str]:
    if "%" not in unit and "percent" not in unit.casefold() and "ratio" not in metric.casefold():
        return None
    normalized = metric.casefold()
    if any(token in normalized for token in _NON_USAGE_METRIC_TOKENS):
        return None
    for kind, tokens in _PERCENT_METRIC_TOKENS.items():
        if any(token in normalized for token in tokens):
            return kind
    return None


def _metric_label(kind: Optional[str], fallback: str) -> str:
    return {
        "CPU": "CPU 사용률",
        "MEMORY": "메모리 사용률",
        "FILESYSTEM": "파일시스템 사용률",
    }.get(kind, fallback)


__all__ = [
    "DEFAULT_THRESHOLDS",
    "analyze_metrics",
]

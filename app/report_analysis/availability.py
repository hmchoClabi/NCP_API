"""WMS 기간 집계로 서비스 가용성 요약을 만든다."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import Finding
from .provenance import OBSERVED, calculated_source_state
from .support import field, mapping, number, records, rounded


def analyze_availability(
    report: Any,
    policy: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[Finding]]:
    source = mapping(field(report, "service_availability", {}))
    scenarios = records(source.get("scenarios"))
    warning_threshold = _policy_number(
        policy, "availability_warning_percent", 99.0
    )
    critical_threshold = _policy_number(
        policy, "availability_critical_percent", 95.0
    )
    critical_threshold = min(critical_threshold, warning_threshold)
    response_threshold = _policy_number(
        policy, "response_time_warning_ms", None
    )
    findings: list[Finding] = []
    items: list[dict[str, Any]] = []

    for scenario in scenarios:
        availability = number(scenario.get("availability_percent"))
        avg_load_time = number(scenario.get("avg_load_time_ms"))
        error_count = _integer_or_none(scenario.get("error_count"))
        total_count = _integer_or_none(scenario.get("total_count"))
        scenario_id = scenario.get("scenario_id")
        scenario_name = scenario.get("name") or scenario_id or "WMS 시나리오"
        item = {
            "source_state": OBSERVED,
            "scenario_id": scenario_id,
            "name": scenario_name,
            "availability_percent": rounded(availability),
            "avg_load_time_ms": rounded(avg_load_time),
            "avg_run_time_ms": rounded(number(scenario.get("avg_run_time_ms"))),
            "success_count": _integer_or_none(scenario.get("success_count")),
            "error_count": error_count,
            "total_count": total_count,
            "has_observations": bool(total_count and total_count > 0),
        }
        items.append(item)

        if availability is not None and total_count and total_count > 0:
            if availability < critical_threshold:
                severity = "CRITICAL"
            elif availability < warning_threshold:
                severity = "WARNING"
            else:
                severity = None
            if severity:
                findings.append(Finding(
                    rule_id="WMS_AVAILABILITY_BELOW_THRESHOLD",
                    severity=severity,
                    category="AVAILABILITY",
                    title=f"{scenario_name} 가용성이 기준보다 낮습니다.",
                    evidence=[
                        {"label": "가용성", "value": rounded(availability), "unit": "%"},
                        {"label": "전체 실행", "value": total_count, "unit": "회"},
                        {"label": "오류", "value": error_count, "unit": "회"},
                    ],
                    impact="외부 관측 위치에서 서비스 요청이 실패했을 가능성이 있습니다.",
                    recommendation="WMS 상세 결과와 같은 시간대의 애플리케이션·LB 지표를 확인하세요.",
                    resource={"id": scenario_id, "name": scenario_name, "type": "WMS_SCENARIO"},
                ))

        if (
            response_threshold is not None
            and avg_load_time is not None
            and total_count
            and total_count > 0
            and avg_load_time > response_threshold
        ):
            findings.append(Finding(
                rule_id="WMS_RESPONSE_TIME_ABOVE_THRESHOLD",
                severity="WARNING",
                category="PERFORMANCE",
                title=f"{scenario_name} 평균 응답 시간이 기준을 초과했습니다.",
                evidence=[
                    {"label": "평균 로드 시간", "value": rounded(avg_load_time), "unit": "ms"},
                    {"label": "설정 기준", "value": response_threshold, "unit": "ms"},
                ],
                impact="사용자가 체감하는 응답 속도가 저하되었을 수 있습니다.",
                recommendation="구간별 응답 결과와 서버·DB·LB 지표를 함께 확인하세요.",
                resource={"id": scenario_id, "name": scenario_name, "type": "WMS_SCENARIO"},
            ))

    items.sort(key=lambda item: str(item.get("name") or "").casefold())
    collection_status = str(source.get("status") or "UNAVAILABLE").upper()
    observed_total = sum(
        item["total_count"] or 0 for item in items
        if item["has_observations"]
    )
    observed_success = sum(
        item["success_count"] or 0 for item in items
        if item["has_observations"]
    )
    return {
        "status": collection_status,
        "source_state": calculated_source_state(collection_status),
        "source": source.get("source"),
        "aggregation": source.get("aggregation"),
        "scenario_count": len(items),
        "observed_scenario_count": sum(item["has_observations"] for item in items),
        "observation_count": observed_total,
        "overall_availability_percent": rounded(
            observed_success / observed_total * 100
            if observed_total else None
        ),
        "thresholds": {
            "warning_percent": warning_threshold,
            "critical_percent": critical_threshold,
            "response_time_warning_ms": response_threshold,
        },
        "items": items,
    }, findings


def _policy_number(
    policy: Mapping[str, Any] | None,
    name: str,
    default: float | None,
) -> float | None:
    if not isinstance(policy, Mapping):
        return default
    thresholds = policy.get("thresholds")
    raw = thresholds.get(name) if isinstance(thresholds, Mapping) else None
    parsed = number(raw)
    return parsed if parsed is not None and parsed >= 0 else default


def _integer_or_none(value: Any) -> int | None:
    parsed = number(value)
    return int(parsed) if parsed is not None else None


__all__ = ["analyze_availability"]

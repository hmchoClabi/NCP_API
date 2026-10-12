"""수집 결과를 한 번의 결정론적 운영 분석으로 조립한다."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .availability import analyze_availability
from .changes import analyze_changes
from .costs import analyze_costs
from .events import analyze_events
from .metrics import analyze_metrics
from .models import sort_findings
from .provenance import CALCULATED, calculated_source_state
from .quality import analyze_data_quality, dataset_status
from .resources import analyze_resource_changes
from .security import analyze_security
from .support import field, mapping, normalize_period_type


ANALYSIS_VERSION = "1.3"

_STATUS_LABELS = {
    # 모든 NCP 상품의 정상 여부가 아니라 실제 수집·검사한 범위의 판정이다.
    # 선택 수집기나 미지원 규칙을 포함한 전체 정상처럼 보이지 않게 한다.
    "NORMAL": "수집·검사 범위 내 정상",
    "CAUTION": "주의",
    "RISK": "위험",
    "UNKNOWN": "판정 불가",
}


def analyze_report(
    report: Any,
    *,
    baseline: Any = None,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """ReportResult 또는 동일 키를 가진 dict를 분석한다.

    분석은 입력만 읽고 외부 상태를 변경하지 않는다. 결과는 JSON 직렬화가
    가능한 기본 타입만 포함하므로 보고서 스냅샷에 그대로 저장할 수 있다.
    """
    effective_policy = dict(policy) if isinstance(policy, Mapping) else {}
    quality, quality_findings = analyze_data_quality(report)
    metrics, metric_findings = analyze_metrics(report, effective_policy)
    events, event_findings = analyze_events(report)
    changes, change_findings = analyze_changes(report)
    availability, availability_findings = analyze_availability(report, effective_policy)
    security, security_findings = analyze_security(report)
    # 거버넌스 준수 여부는 실제 장애나 자원 포화와 동일한 운영 경고로
    # 취급하지 않는다. 기존 저장 스냅샷과의 JSON 계약만 빈 요약으로 유지한다.
    governance = {
        "status": "NOT_REQUESTED",
        "source_state": CALCULATED,
        "rules": [],
        "finding_count": 0,
        "indeterminate_count": 0,
    }
    costs, cost_findings = analyze_costs(
        report,
        baseline=baseline,
        policy=effective_policy,
    )
    resource_changes = analyze_resource_changes(report, baseline=baseline)
    findings = sort_findings(
        [
            *quality_findings,
            *metric_findings,
            *event_findings,
            *change_findings,
            *availability_findings,
            *security_findings,
            *cost_findings,
        ]
    )
    _apply_quality_status(metrics, dataset_status(quality, "monitoring"))
    _apply_quality_status(events, dataset_status(quality, "insight_events"))
    _apply_quality_status(changes, dataset_status(quality, "activity_events"))
    _apply_quality_status(
        availability,
        dataset_status(quality, "service_availability"),
    )
    _apply_quality_status(security, dataset_status(quality, "security_events"))
    _apply_quality_status(costs, dataset_status(quality, "billing"))
    overall_status = _overall_status(findings, quality)
    period = mapping(field(report, "period", {}))

    return {
        "version": ANALYSIS_VERSION,
        "source_state": CALCULATED,
        "period_type": normalize_period_type(period.get("period_type")),
        "overall_status": overall_status,
        "overall_status_label": _STATUS_LABELS[overall_status],
        "assessment_scope_note": (
            "운영 상태는 이번 보고서에서 수집되고 규칙으로 검사된 범위만 "
            "판정합니다. 수집 대상 아님·미지원·수집 실패 항목의 정상 여부는 "
            "확정하지 않습니다."
        ),
        "data_quality": quality,
        "key_findings": _key_findings(findings),
        "findings": findings,
        "metrics": metrics,
        "events": events,
        "changes": changes,
        "availability": availability,
        "security": security,
        "governance": governance,
        "costs": costs,
        "resource_changes": resource_changes,
    }


def _overall_status(
    findings: list[dict[str, Any]],
    quality: Mapping[str, Any],
) -> str:
    operational = [finding for finding in findings if finding.get("category") != "DATA_QUALITY"]
    if any(finding.get("severity") == "CRITICAL" for finding in operational):
        return "RISK"
    if any(finding.get("severity") == "WARNING" for finding in operational):
        return "CAUTION"
    if quality.get("overall_status") == "COMPLETE":
        return "NORMAL"
    return "UNKNOWN"


def _key_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    operational = [finding for finding in findings if finding.get("category") != "DATA_QUALITY"]
    quality = [finding for finding in findings if finding.get("category") == "DATA_QUALITY"]
    return [*operational, *quality][:5]


def _apply_quality_status(result: dict[str, Any], status: str) -> None:
    if status in {
        "AVAILABLE",
        "COLLECTED_EMPTY",
        "PARTIAL",
        "FAILED",
        "UNAVAILABLE",
        "NOT_REQUESTED",
    }:
        result["status"] = status
        result["source_state"] = calculated_source_state(status)


__all__ = ["ANALYSIS_VERSION", "analyze_report"]

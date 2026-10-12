"""Cloud Insight 이벤트를 운영 보고용 통계와 판정으로 변환한다."""

from __future__ import annotations

from typing import Any, Optional

from .models import Finding
from .provenance import CALCULATED, OBSERVED, UNAVAILABLE
from .support import field, records, timestamp_millis

_CRITICAL_LEVELS = {"CRITICAL", "FATAL", "EMERGENCY", "DANGER", "ERROR"}
_WARNING_LEVELS = {"WARNING", "WARN", "CAUTION"}


def analyze_events(report: Any) -> tuple[dict[str, Any], list[Finding]]:
    events = records(field(report, "insight_events", []))
    summaries: list[dict[str, Any]] = []
    findings: list[Finding] = []
    critical_count = warning_count = open_count = duration_count = 0

    for event in events:
        severity = _severity(event)
        if severity == "CRITICAL":
            critical_count += 1
        elif severity == "WARNING":
            warning_count += 1

        start_value = event.get("start_time") or event.get("event_time")
        start_time = timestamp_millis(start_value)
        end_time = timestamp_millis(event.get("end_time"))
        # Cloud Insight는 진행 중인 이벤트의 endTime을 0으로 반환할 수
        # 있다. Unix epoch 종료로 해석하면 미종료 이벤트가 누락된다.
        if end_time is not None and end_time <= 0:
            end_time = None
        duration_seconds: Optional[int] = None
        if start_time is not None and end_time is not None and end_time >= start_time:
            duration_seconds = int((end_time - start_time) / 1000)
            duration_count += 1
        is_open = start_time is not None and end_time is None
        if is_open:
            open_count += 1

        resource_id = event.get("resource_id")
        resource_name = event.get("resource_name") or resource_id or "대상 미확인"
        rule_name = event.get("rule_name") or event.get("metric") or "Cloud Insight 이벤트"
        summaries.append(
            {
                "source_state": OBSERVED,
                "event_id": event.get("event_id"),
                "severity": severity,
                "resource_id": resource_id,
                "resource_name": resource_name,
                "rule_name": rule_name,
                "metric": event.get("metric"),
                "start_time": start_value,
                "end_time": event.get("end_time"),
                "duration_seconds": duration_seconds,
                "is_open": is_open,
            }
        )

        if severity in {"CRITICAL", "WARNING"}:
            findings.append(
                Finding(
                    rule_id="INSIGHT_EVENT_OPEN" if is_open else "INSIGHT_EVENT_OCCURRED",
                    severity=severity,
                    category="EVENT",
                    title=f"{resource_name}에서 {rule_name} 이벤트가 발생했습니다.",
                    evidence=[
                        {"label": "이벤트 등급", "value": severity},
                        {"label": "시작 시각", "value": event.get("start_time_kst") or start_value},
                        {
                            "label": "종료 시각",
                            "value": event.get("end_time_kst") or event.get("end_time") or "미종료",
                        },
                        {"label": "지속 시간", "value": duration_seconds, "unit": "초"},
                    ],
                    impact="모니터링 규칙이 임계 상태를 감지했습니다. 실제 고객 영향은 별도 확인이 필요합니다.",
                    recommendation="같은 시간대의 지표와 변경 이력을 함께 확인하고 원인과 조치 결과를 기록하세요.",
                    resource={
                        "id": resource_id,
                        "name": resource_name,
                        "type": event.get("resource_type") or event.get("prod_name"),
                    },
                    occurrence_key=(
                        event.get("event_id"),
                        event.get("rule_id") or rule_name,
                        event.get("metric"),
                        start_value,
                    ),
                )
            )

    summaries.sort(
        key=lambda item: (
            0 if item["severity"] == "CRITICAL" else 1,
            str(item.get("resource_name") or ""),
            str(item.get("event_id") or ""),
        )
    )
    return {
        "status": "AVAILABLE" if events else "UNAVAILABLE",
        "source_state": CALCULATED if events else UNAVAILABLE,
        "total_count": len(events),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "open_count": open_count,
        "duration_available_count": duration_count,
        "duration_note": (
            "시작·종료 시각 차이이며 MTTA 또는 MTTR이 아닙니다."
            if duration_count
            else "시작·종료 시각이 모두 있는 이벤트가 없어 지속 시간을 계산하지 않았습니다."
        ),
        "items": summaries,
    }, findings


def _severity(event: dict[str, Any]) -> str:
    raw = (
        str(event.get("level") or event.get("severity") or event.get("event_level") or "")
        .strip()
        .upper()
    )
    if raw in _CRITICAL_LEVELS:
        return "CRITICAL"
    if raw in _WARNING_LEVELS:
        return "WARNING"
    return "INFO"


__all__ = ["analyze_events"]

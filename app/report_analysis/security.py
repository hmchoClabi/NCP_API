"""Security Monitoring 기간 이벤트를 노출을 줄인 요약으로 변환한다."""

from __future__ import annotations

from collections import Counter
from typing import Any

from utils.event_sort import event_timestamp_millis

from .models import Finding
from .provenance import OBSERVED, calculated_source_state
from .support import field, mapping, records


def analyze_security(report: Any) -> tuple[dict[str, Any], list[Finding]]:
    source = mapping(field(report, "security_monitoring", {}))
    events = records(source.get("events"))
    by_service: Counter[str] = Counter()
    items: list[dict[str, Any]] = []
    findings: list[Finding] = []

    for event in events:
        service = str(event.get("service") or "SECURITY").upper()
        by_service[service] += 1
        event_name = event.get("event_name") or event.get("attack_type") or "보안 이벤트"
        target = event.get("vpc_name") or event.get("target_ip") or "대상 미확인"
        items.append(
            {
                "source_state": OBSERVED,
                "event_id": event.get("event_id"),
                "service": service,
                "event_name": event_name,
                "attack_type": event.get("attack_type"),
                "detected_at": event.get("detected_at"),
                "detected_at_kst": event.get("detected_at_kst"),
                "action_status": event.get("action_status"),
                "target": target,
                "platform": event.get("platform") or source.get("scope"),
            }
        )
        findings.append(
            Finding(
                rule_id="SECURITY_MONITORING_EVENT_DETECTED",
                severity="WARNING",
                category="SECURITY",
                title=f"{service}에서 보안 이벤트가 탐지되었습니다.",
                evidence=[
                    {"label": "이벤트", "value": event_name},
                    {
                        "label": "탐지 시각",
                        "value": event.get("detected_at_kst") or event.get("detected_at"),
                    },
                    {"label": "처리 상태", "value": event.get("action_status") or "미제공"},
                ],
                impact="보안 탐지 이벤트이며 실제 침해 또는 고객 영향 여부는 상세 분석이 필요합니다.",
                recommendation="Security Monitoring 상세 내역에서 공격 원본, 차단 여부와 후속 조치를 확인하세요.",
                resource={"id": event.get("event_id"), "name": str(target), "type": service},
                occurrence_key=(
                    event.get("event_id"),
                    event.get("detected_at"),
                    event_name,
                ),
            )
        )

    items.sort(
        key=lambda item: (
            -(event_timestamp_millis(item.get("detected_at") or item.get("detected_at_kst")) or 0),
            str(item.get("event_id") or ""),
        )
    )
    service_statuses = source.get("service_statuses")
    if not isinstance(service_statuses, dict):
        service_statuses = {}
    source_collection_status = str(source.get("status") or "UNAVAILABLE").upper()
    return {
        "status": source_collection_status,
        "source_state": calculated_source_state(source_collection_status),
        "source": source.get("source"),
        "scope": source.get("scope"),
        "event_count": len(items),
        "by_service": [
            {"service": service, "count": count} for service, count in sorted(by_service.items())
        ],
        "service_statuses": {
            str(name): str(status) for name, status in sorted(service_statuses.items())
        },
        "items": items,
    }, findings


__all__ = ["analyze_security"]

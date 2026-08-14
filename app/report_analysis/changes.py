"""Cloud Activity Tracer 이벤트를 변경 요약으로 변환한다."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .models import Finding
from .provenance import CALCULATED, OBSERVED, UNAVAILABLE
from .support import field, flatten_records


_FAILURE_RESULTS = {"FAIL", "FAILED", "FAILURE", "ERROR", "DENIED"}
_READ_PREFIXES = (
    "get", "list", "search", "describe", "download", "read", "view",
)
_CHANGE_PREFIXES = (
    "create", "delete", "remove", "terminate", "update", "set", "change",
    "add", "attach", "detach", "start", "stop", "restart", "reboot",
    "assign", "unassign", "associate", "disassociate", "enable", "disable",
    "put", "register", "deregister", "modify", "reset", "cancel", "reissue",
)


def analyze_changes(report: Any) -> tuple[dict[str, Any], list[Finding]]:
    events = flatten_records(field(report, "activity_events", []))
    by_product: Counter[str] = Counter()
    by_action: Counter[str] = Counter()
    items: list[dict[str, Any]] = []
    findings: list[Finding] = []
    success_count = failure_count = 0
    change_count = failed_change_count = read_count = 0

    for event in events:
        product = str(
            event.get("product_display_name")
            or event.get("product_name")
            or "상품 미확인"
        )
        action = str(event.get("action_name") or "작업 미확인")
        operation_kind = _operation_kind(action)
        result = str(event.get("result") or "UNKNOWN").upper()
        by_product[product] += 1
        by_action[action] += 1
        if result in {"SUCCESS", "SUCCEEDED", "OK"}:
            success_count += 1
        elif result in _FAILURE_RESULTS:
            failure_count += 1
        if operation_kind == "CHANGE":
            change_count += 1
            if result in _FAILURE_RESULTS:
                failed_change_count += 1
        elif operation_kind == "READ":
            read_count += 1

        resource_id = event.get("resource_id")
        resource_name = event.get("resource_name") or resource_id or "대상 미확인"
        items.append({
            "source_state": OBSERVED,
            "event_id": event.get("event_id"),
            "event_time": event.get("event_time"),
            "event_time_kst": event.get("event_time_kst"),
            "product": product,
            "action": action,
            "operation_kind": operation_kind,
            "result": result,
            "resource_id": resource_id,
            "resource_name": resource_name,
            "user_type": event.get("user_type"),
            "source_type": event.get("source_type"),
        })
        if result in _FAILURE_RESULTS:
            if operation_kind == "CHANGE":
                rule_id = "ACTIVITY_CHANGE_FAILED"
                category = "CHANGE"
                title = f"{product} {action} 변경 활동이 실패했습니다."
                impact = "변경 작업이 완료되지 않아 대상 상태가 의도와 다를 수 있습니다."
            elif operation_kind == "READ":
                rule_id = "ACTIVITY_READ_FAILED"
                category = "EVENT"
                title = f"{product} {action} 조회 활동이 실패했습니다."
                impact = "조회 활동 실패이며 자원 변경 실패로 분류하지 않습니다."
            else:
                rule_id = "ACTIVITY_OPERATION_FAILED"
                category = "EVENT"
                title = f"{product} {action} 활동이 실패했습니다."
                impact = "액션명만으로 조회·변경 여부를 확정할 수 없습니다."
            findings.append(Finding(
                rule_id=rule_id,
                severity="WARNING",
                category=category,
                title=title,
                evidence=[
                    {"label": "대상", "value": resource_name},
                    {"label": "결과", "value": result},
                    {"label": "시각", "value": event.get("event_time_kst") or event.get("event_time")},
                ],
                impact=impact,
                recommendation="Activity Tracer 원본 이력과 대상 자원의 현재 상태를 확인하세요.",
                resource={"id": resource_id, "name": resource_name, "type": product},
                occurrence_key=(
                    event.get("event_id") or event.get("history_id"),
                    action,
                    event.get("event_time"),
                ),
            ))

    items.sort(
        key=lambda item: (
            str(item.get("event_time") or ""),
            str(item.get("event_id") or ""),
        ),
        reverse=True,
    )
    return {
        "status": "AVAILABLE" if events else "UNAVAILABLE",
        "source_state": CALCULATED if events else UNAVAILABLE,
        "total_count": len(events),
        "success_count": success_count,
        "failure_count": failure_count,
        "change_count": change_count,
        "failed_change_count": failed_change_count,
        "read_count": read_count,
        "by_product": _counter_rows(by_product),
        "by_action": _counter_rows(by_action),
        "items": items,
    }, findings


def _counter_rows(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"name": name, "count": count}
        for name, count in sorted(
            counter.items(),
            key=lambda item: (-item[1], item[0].casefold()),
        )
    ]


def _operation_kind(action: str) -> str:
    normalized = "".join(character for character in action.casefold() if character.isalnum())
    if normalized.startswith(_READ_PREFIXES):
        return "READ"
    if normalized.startswith(_CHANGE_PREFIXES):
        return "CHANGE"
    return "UNKNOWN"


__all__ = ["analyze_changes"]

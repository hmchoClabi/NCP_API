"""Cloud Activity Tracer 이벤트를 변경 요약으로 변환한다."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .models import Finding
from .provenance import CALCULATED, OBSERVED, UNAVAILABLE
from .support import field, flatten_records


_SUCCESS_RESULTS = {"SUCCESS", "SUCCEEDED", "OK", "성공", "완료"}
_FAILURE_RESULTS = {
    "FAIL",
    "FAILED",
    "FAILURE",
    "ERROR",
    "DENIED",
    "REJECTED",
    "실패",
    "오류",
    "거부",
    "거절",
}
_CREATE_ACTIONS = {"create", "add", "attach", "register", "associate", "assign"}
_DELETE_ACTIONS = {
    "delete",
    "remove",
    "detach",
    "terminate",
    "deregister",
    "disassociate",
    "unassign",
}
_READ_PREFIXES = (
    "get",
    "list",
    "search",
    "describe",
    "download",
    "read",
    "view",
)
_CHANGE_PREFIXES = (
    "create",
    "delete",
    "remove",
    "terminate",
    "update",
    "set",
    "change",
    "add",
    "attach",
    "detach",
    "start",
    "stop",
    "restart",
    "reboot",
    "assign",
    "unassign",
    "associate",
    "disassociate",
    "enable",
    "disable",
    "put",
    "register",
    "deregister",
    "modify",
    "reset",
    "cancel",
    "reissue",
)


def analyze_changes(report: Any) -> tuple[dict[str, Any], list[Finding]]:
    events = flatten_records(field(report, "activity_events", []))
    activity_summary = summarize_activity_events(events)
    by_product: Counter[str] = Counter()
    by_action: Counter[str] = Counter()
    items: list[dict[str, Any]] = []
    findings: list[Finding] = []
    change_count = failed_change_count = read_count = 0

    for event in events:
        product = str(
            event.get("product_display_name") or event.get("product_name") or "상품 미확인"
        )
        action = str(event.get("action_name") or "작업 미확인")
        operation_kind = _operation_kind(action)
        result = _normalized_result(event.get("result"))
        result_kind = _result_kind(result)
        by_product[product] += 1
        by_action[action] += 1
        if operation_kind == "CHANGE":
            change_count += 1
            if result_kind == "FAILURE":
                failed_change_count += 1
        elif operation_kind == "READ":
            read_count += 1

        resource_id = event.get("resource_id")
        resource_name = event.get("resource_name") or resource_id or "대상 미확인"
        items.append(
            {
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
            }
        )
        if result_kind == "FAILURE":
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
            findings.append(
                Finding(
                    rule_id=rule_id,
                    severity="WARNING",
                    category=category,
                    title=title,
                    evidence=[
                        {"label": "대상", "value": resource_name},
                        {"label": "결과", "value": result},
                        {
                            "label": "시각",
                            "value": event.get("event_time_kst") or event.get("event_time"),
                        },
                    ],
                    impact=impact,
                    recommendation="Activity Tracer 원본 이력과 대상 자원의 현재 상태를 확인하세요.",
                    resource={"id": resource_id, "name": resource_name, "type": product},
                    occurrence_key=(
                        event.get("event_id") or event.get("history_id"),
                        action,
                        event.get("event_time"),
                    ),
                )
            )

    items.sort(
        key=lambda item: (
            str(item.get("event_time") or ""),
            str(item.get("event_id") or ""),
        ),
        reverse=True,
    )
    return {
        **activity_summary,
        "status": "AVAILABLE" if events else "UNAVAILABLE",
        "source_state": CALCULATED if events else UNAVAILABLE,
        "change_count": change_count,
        "failed_change_count": failed_change_count,
        "read_count": read_count,
        "by_product": _counter_rows(by_product),
        "by_action": _counter_rows(by_action),
        "items": items,
    }, findings


def group_activity_events(value: Any) -> dict[str, list[dict[str, Any]]]:
    """요약 카드와 건수가 같은 판정 기준을 쓰도록 이벤트를 분류한다."""
    events = flatten_records(value)
    groups: dict[str, list[dict[str, Any]]] = {
        "success": [],
        "failure": [],
        "unknown_result": [],
        "created_success": [],
        "deleted_success": [],
        "login_failure": [],
    }
    for event in events:
        result_kind = _result_kind(event.get("result"))
        action = event.get("action_name")
        if result_kind == "SUCCESS":
            groups["success"].append(event)
            lifecycle = _lifecycle_kind(action)
            if lifecycle == "CREATE":
                groups["created_success"].append(event)
            elif lifecycle == "DELETE":
                groups["deleted_success"].append(event)
        elif result_kind == "FAILURE":
            groups["failure"].append(event)
            if _is_login_action(action):
                groups["login_failure"].append(event)
        else:
            groups["unknown_result"].append(event)
    return groups


def summarize_activity_events(value: Any) -> dict[str, int]:
    """담당자가 확인할 Activity 작업을 보수적으로 집계한다."""
    groups = group_activity_events(value)
    return {
        "total_count": sum(len(groups[key]) for key in ("success", "failure", "unknown_result")),
        "success_count": len(groups["success"]),
        "failure_count": len(groups["failure"]),
        "unknown_result_count": len(groups["unknown_result"]),
        "created_success_count": len(groups["created_success"]),
        "deleted_success_count": len(groups["deleted_success"]),
        "login_failure_count": len(groups["login_failure"]),
    }


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


def _normalized_result(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "UNKNOWN"
    return value.strip().upper()


def _result_kind(value: Any) -> str:
    normalized = _normalized_result(value)
    if normalized in _SUCCESS_RESULTS:
        return "SUCCESS"
    if normalized in _FAILURE_RESULTS:
        return "FAILURE"
    return "UNKNOWN"


def _lifecycle_kind(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "OTHER"
    action = value.strip()
    words = action.split()
    first = words[0].casefold().strip(":_-()[]")
    last = words[-1].casefold().strip(":_-()[]")
    if first in _CREATE_ACTIONS or last in {"생성", "추가", "연결"}:
        return "CREATE"
    if (
        first in _DELETE_ACTIONS
        or "".join(character for character in action.casefold() if character.isalnum())
        == "servertermination"
        or any(part in {"삭제", "제거", "반납", "분리"} for part in last.split("/"))
    ):
        return "DELETE"
    return "OTHER"


def _is_login_action(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = "".join(character for character in value.casefold() if character.isalnum())
    return normalized in {"login", "signin", "로그인"}


__all__ = [
    "analyze_changes",
    "group_activity_events",
    "summarize_activity_events",
]

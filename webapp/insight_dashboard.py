"""Summarize persisted Insight occurrences without collecting or changing data."""

import json
from datetime import datetime, timedelta

from utils.event_sort import event_timestamp_millis


def summarize_insight_alarms(reports: list[dict], today: datetime) -> dict:
    def event_time(value):
        try:
            millis = event_timestamp_millis(value)
            return datetime.fromtimestamp(millis / 1000, tz=today.tzinfo) if millis and millis > 0 else None
        except (ValueError, OverflowError, OSError):
            return None

    current = [report for report in reports
               if today <= (event_time(report.get("completed_at")) or today - timedelta(days=1))
               < today + timedelta(days=1)]
    current.sort(key=lambda report: event_time(report["completed_at"]), reverse=True)
    seen = set()
    groups = {}
    incomplete = 0
    unidentified = 0
    severity_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    for report in current:
        statuses = report.get("dataset_statuses")
        status = next((item.get("status") for item in statuses
                       if isinstance(item, dict) and item.get("key") == "insight_events"), None
                      ) if isinstance(statuses, list) else None
        if status not in {"COLLECTED", "COLLECTED_EMPTY"}:
            incomplete += 1
        events = report.get("insight_events")
        for index, event in enumerate(events if isinstance(events, list) else []):
            if not isinstance(event, dict):
                continue
            account = tuple(str(report.get(key) or "") for key in
                            ("tenant_id", "cloud_account_id", "environment"))
            occurred = event_time(event.get("start_time"))
            identity = (
                str(event.get("prod_key") or event.get("prod_name") or ""),
                str(event.get("resource_id") or event.get("resource_name") or ""),
                str(event.get("rule_id") or event.get("rule_name") or ""),
                *(str(event[key]) if event.get(key) is not None else "" for key in
                  ("metric", "operator", "criteria", "unit", "calc", "interval")),
                json.dumps(event.get("dimension") or {}, sort_keys=True, ensure_ascii=False),
            )
            source_id = str(event.get("event_id") or "")
            occurrence = account + (("id", source_id) if source_id else
                                    ("time", identity, occurred) if occurred else
                                    ("unknown", str(report.get("id")), index))
            if occurrence in seen:
                continue
            seen.add(occurrence)
            uncertain = not source_id and occurred is None
            unidentified += int(uncertain)
            group = groups.setdefault(account + identity, {
                "tenant_id": report.get("tenant_id"),
                "customer_name": report.get("customer_name"),
                "account_name": report.get("account_name") or report.get("account_code") or "계정 미확인",
                "environment": report.get("environment"),
                "resource_name": event.get("resource_name") or event.get("resource_id") or "인스턴스 미확인",
                "resource_id": event.get("resource_id"),
                "alarm_name": event.get("rule_name") or event.get("metric") or "알람명 미확인",
                "metric": event.get("metric"),
                "condition": " ".join(str(event[field]) if event.get(field) is not None else "" for field in
                                      ("operator_symbol", "criteria", "unit")).strip(),
                "dimension": identity[-1],
                "severity": str(event.get("level") or "UNKNOWN").upper(),
                "count": 0, "open_count": 0, "unknown_count": 0,
                "first_at": None, "last_at": None,
                "report_id": report.get("id"),
            })
            group["count"] += 1
            group["open_count"] += int(event_time(event.get("end_time")) is None)
            group["unknown_count"] += int(uncertain)
            level = str(event.get("level") or "UNKNOWN").upper()
            if severity_order.get(level, 99) < severity_order.get(group["severity"], 99):
                group["severity"] = level
            if occurred:
                group["first_at"] = min(group["first_at"] or occurred, occurred)
                group["last_at"] = max(group["last_at"] or occurred, occurred)
    items = sorted(groups.values(), key=lambda item: (
        severity_order.get(item["severity"], 99), -item["count"],
        str(item["customer_name"]), str(item["resource_name"]),
    ))
    return {
        "day": today, "report_count": len(current),
        "customer_count": len({str(report.get("tenant_id")) for report in current}),
        "affected_customer_count": len({str(item["tenant_id"]) for item in items}),
        "event_count": len(seen), "group_count": len(items),
        "incomplete_report_count": incomplete, "unidentified_count": unidentified,
        "items": items,
    }

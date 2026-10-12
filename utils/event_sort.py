import math
from datetime import datetime
from typing import Any, Dict, Iterable, List, Sequence
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def event_timestamp_millis(value: Any) -> int | None:
    """Return an event time as epoch milliseconds when it can be parsed."""
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, datetime):
        event_time = value
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=KST)
        return int(event_time.timestamp() * 1000)

    if isinstance(value, (int, float)):
        timestamp = float(value)
    else:
        text = str(value).strip()
        if not text:
            return None

        try:
            timestamp = float(text)
        except ValueError:
            event_time = _parse_datetime(text)
            if event_time is None:
                return None
            return int(event_time.timestamp() * 1000)

    if not math.isfinite(timestamp):
        return None

    # NCP event timestamps normally use epoch milliseconds. Supporting epoch
    # seconds keeps sorting compatible with older fixtures and integrations.
    if abs(timestamp) < 100_000_000_000:
        timestamp *= 1000
    return int(timestamp)


def sort_event_records(
    records: Iterable[Dict[str, Any]],
    time_keys: Sequence[str],
) -> List[Dict[str, Any]]:
    """Sort events oldest-first, keeping unparseable times last and stable."""

    def sort_key(record: Dict[str, Any]) -> tuple[int, int]:
        for key in time_keys:
            timestamp = event_timestamp_millis(record.get(key))
            if timestamp is not None:
                return 0, timestamp
        return 1, 0

    return sorted(records, key=sort_key)


def _parse_datetime(value: str) -> datetime | None:
    normalized = value.strip()
    if normalized.endswith(" KST"):
        normalized = normalized[:-4] + "+09:00"
    elif normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        event_time = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=KST)
    return event_time

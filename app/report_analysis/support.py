"""분석 모듈에서 공통으로 사용하는 안전한 값 변환 함수."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Any, Optional

from utils.event_sort import event_timestamp_millis


INTERVAL_SECONDS = {
    "Min1": 60,
    "Min5": 5 * 60,
    "Min30": 30 * 60,
    "Hour1": 60 * 60,
    "Hour2": 2 * 60 * 60,
    "Day1": 24 * 60 * 60,
}


def field(source: Any, name: str, default: Any = None) -> Any:
    """매핑과 ReportResult 같은 객체에서 같은 방식으로 값을 읽는다."""
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def flatten_records(value: Any) -> list[dict[str, Any]]:
    """그룹 키의 형태와 무관하게 이벤트 레코드를 한 번씩 펼친다."""
    if isinstance(value, (list, tuple)):
        return records(value)
    if not isinstance(value, Mapping):
        return []

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item_value in value.values():
        for item in records(item_value):
            identity = str(
                item.get("event_id")
                or item.get("history_id")
                or stable_fingerprint("event", item)
            )
            if identity in seen:
                continue
            seen.add(identity)
            result.append(item)
    return result


def number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


timestamp_millis = event_timestamp_millis


def interval_seconds(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    if text in INTERVAL_SECONDS:
        return INTERVAL_SECONDS[text]
    lowered = text.casefold()
    if lowered.endswith("s") and lowered[:-1].isdigit():
        return int(lowered[:-1])
    return None


def infer_interval_seconds(points: list[tuple[int, float]]) -> Optional[int]:
    gaps = [
        (current[0] - previous[0]) / 1000
        for previous, current in zip(points, points[1:])
        if current[0] > previous[0]
    ]
    if not gaps:
        return None
    median = statistics.median(gaps)
    return max(1, int(round(median))) if math.isfinite(median) else None


def percentile(values: Iterable[float], percentile_value: float) -> Optional[float]:
    """정렬된 표본 사이를 선형 보간해 분위수를 구한다."""
    samples = sorted(value for value in values if math.isfinite(value))
    if not samples:
        return None
    if len(samples) == 1:
        return samples[0]
    position = (len(samples) - 1) * percentile_value
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return samples[lower]
    ratio = position - lower
    return samples[lower] + (samples[upper] - samples[lower]) * ratio


def rounded(value: Optional[float], digits: int = 2) -> Optional[float]:
    return round(value, digits) if value is not None else None


def stable_fingerprint(*parts: Any) -> str:
    """동일한 규칙과 대상에는 보고서가 달라도 같은 식별자를 부여한다."""
    canonical = json.dumps(
        [_json_safe(part) for part in parts],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return f"finding-{digest}"


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in sorted(value.items(), key=lambda row: str(row[0]))
        }
    if isinstance(value, (set, frozenset)):
        return [
            _json_safe(item)
            for item in sorted(value, key=lambda item: str(item))
        ]
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def normalize_period_type(value: Any) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized in {
        "day",
        "daily",
        "today",
        "yesterday",
        "일",
        "일간",
        "오늘",
        "어제",
    }:
        return "DAILY"
    if normalized in {"month", "monthly", "prev_month", "월", "월간"}:
        return "MONTHLY"
    if normalized in {"range", "period", "datetime_range", "기간"}:
        return "RANGE"
    return "UNKNOWN"

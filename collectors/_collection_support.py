"""Shared, stateless collection helpers."""

import json
from collections.abc import Mapping, Sequence
from typing import Any


def item_identity(
    item: Mapping[str, Any],
    identity_fields: Sequence[str],
) -> str:
    for field in identity_fields:
        value = item.get(field)
        if value is not None and str(value).strip():
            return f"{field}:{value}"
    return "row:" + json.dumps(
        item,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def query_time_windows(
    start_time: int,
    end_time: int,
    interval: str,
) -> list[tuple[int, int]]:
    day = 24 * 60 * 60 * 1000
    window_size = {
        "Min1": day,
        "Min5": 7 * day,
        "Min30": 31 * day,
        "Hour2": 31 * day,
        "Day1": 366 * day,
    }.get(interval, 7 * day)
    result = []
    cursor = start_time
    while cursor <= end_time:
        window_end = min(cursor + window_size - 1, end_time)
        result.append((cursor, window_end))
        cursor = window_end + 1
    return result

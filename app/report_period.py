"""보고 기간과 인프라 스냅샷 시간 경계를 일관되게 계산한다.

보고서 내부의 기간은 모두 ``[시작, 종료)`` 반개구간으로 다룬다. 일 단위
입력처럼 종료 시각이 포함형인 기존 데이터만 이 모듈에서 1초를 보정한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional


def normalize_period_bounds(
    start: datetime,
    end: datetime,
    *,
    end_exclusive: bool,
) -> tuple[datetime, datetime]:
    """기간을 표준 ``[start, end)`` 경계로 정규화한다."""
    normalized_end = end if end_exclusive else end + timedelta(seconds=1)
    if start >= normalized_end:
        raise ValueError("Report period is invalid.")
    return start, normalized_end


def build_snapshot_eligibility_window(
    period_start: datetime,
    period_end: datetime,
    reference_at: datetime,
) -> Optional[Dict[str, datetime]]:
    """기준 시각까지 실제 관측 가능했던 스냅샷 구간을 반환한다.

    종료 경계 바로 앞의 1마이크로초를 기준 시각의 상한으로 사용해야
    다음 보고 기간에서 수집된 스냅샷이 현재 기간에 섞이지 않는다.
    """
    if reference_at < period_start:
        return None

    reference = min(
        reference_at,
        period_end - timedelta(microseconds=1),
    )
    eligible_end = min(
        period_end,
        reference + timedelta(microseconds=1),
    )
    if period_start >= eligible_end:
        return None
    return {
        "reference_at": reference,
        "eligible_start": period_start,
        "eligible_end": eligible_end,
    }


def snapshot_window_metadata(
    window: Optional[Dict[str, datetime]],
    observed_at: Any = None,
) -> Dict[str, Any]:
    """스냅샷 선택 근거를 직렬화 가능한 메타데이터로 변환한다."""
    if not window:
        return {
            "reference_at": None,
            "eligible_start": None,
            "eligible_end": None,
            "snapshot_age_seconds": None,
        }

    metadata: Dict[str, Any] = {
        key: window[key].isoformat()
        for key in ("reference_at", "eligible_start", "eligible_end")
    }
    metadata["snapshot_age_seconds"] = None
    if isinstance(observed_at, datetime):
        metadata["snapshot_age_seconds"] = max(
            0,
            int((window["reference_at"] - observed_at).total_seconds()),
        )
    return metadata

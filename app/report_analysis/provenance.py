"""운영 분석 결과의 출처 상태를 일관된 값으로 변환한다."""

from __future__ import annotations

from typing import Final


OBSERVED: Final = "OBSERVED"
CALCULATED: Final = "CALCULATED"
INFERRED: Final = "INFERRED"
UNAVAILABLE: Final = "UNAVAILABLE"
COLLECTION_FAILED: Final = "COLLECTION_FAILED"

SOURCE_STATE_LABELS: Final[dict[str, str]] = {
    OBSERVED: "관측",
    CALCULATED: "계산",
    INFERRED: "추론",
    UNAVAILABLE: "미수집",
    COLLECTION_FAILED: "수집 실패",
}

_AVAILABLE_DATASET_STATUSES = {
    "AVAILABLE",
    "COLLECTED",
    "COLLECTED_EMPTY",
    "PARTIAL",
}


def dataset_source_state(status: object) -> str:
    """수집 상태를 원천 데이터의 출처 상태로 변환한다.

    PARTIAL은 확보된 관측 데이터가 있다는 의미로 OBSERVED를 유지하고,
    부분 누락 여부는 기존 ``status`` 필드에서 별도로 표현한다.
    """
    normalized = str(status or "").strip().upper()
    if normalized in _AVAILABLE_DATASET_STATUSES:
        return OBSERVED
    if normalized in {"FAILED", "ERROR", "FAILURE"}:
        return COLLECTION_FAILED
    return UNAVAILABLE


def calculated_source_state(status: object) -> str:
    """수집 상태를 해당 데이터로 계산한 결과의 출처 상태로 변환한다."""
    source_state = dataset_source_state(status)
    return CALCULATED if source_state == OBSERVED else source_state


def historical_source_state(confidence: object) -> str:
    """명시된 과거 존재 추론만 INFERRED로 표시한다."""
    normalized = str(confidence or "").strip().upper()
    if normalized == "INFERRED_FROM_CREATE_TIME":
        return INFERRED
    if normalized:
        return UNAVAILABLE
    return OBSERVED


__all__ = [
    "CALCULATED",
    "COLLECTION_FAILED",
    "INFERRED",
    "OBSERVED",
    "SOURCE_STATE_LABELS",
    "UNAVAILABLE",
    "calculated_source_state",
    "dataset_source_state",
    "historical_source_state",
]

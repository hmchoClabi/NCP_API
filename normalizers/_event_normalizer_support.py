"""이벤트 normalizer의 공통 검증·그룹화·오류 계약을 제공한다.

공급자별 필드 매핑, timestamp 해석 후보, 그룹 키와 정렬 필드는 subclass가
명시한다. 공통 계층은 입력 항목을 격리해 처리하고 기존 오류 payload를 만드는
역할만 담당한다.
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional

from utils.event_sort import sort_event_records


class _EventNormalizerBase:
    """두 이벤트 공급자가 공유하는 한 단계 normalizer 골격."""

    SORT_FIELDS: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.last_errors: List[Dict[str, Any]] = []

    def normalize(
        self,
        raw_events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        self.last_errors = []
        result = []
        if not isinstance(raw_events, list):
            self._record_error(
                index=None,
                message="이벤트 목록이 list 형식이 아닙니다.",
            )
            return result

        for index, event in enumerate(raw_events):
            if not isinstance(event, dict):
                self._record_error(
                    index=index,
                    message="이벤트 항목이 object 형식이 아닙니다.",
                )
                continue
            try:
                result.append(self._normalize_event(event))
            except Exception as exc:
                self._record_error(
                    index=index,
                    message="이벤트 항목 정규화에 실패했습니다.",
                    exc=exc,
                )
        return sort_event_records(result, self.SORT_FIELDS)

    def group_events(
        self,
        events: List[Dict[str, Any]],
        group_by: str = "resource",
    ) -> Dict[str, List[Dict[str, Any]]]:
        result: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for event in events:
            if not isinstance(event, dict):
                continue
            result[self._get_group_key(event, group_by)].append(event)
        return dict(result)

    def _normalize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def _get_group_key(
        self,
        event: Dict[str, Any],
        group_by: str,
    ) -> str:
        raise NotImplementedError

    def _record_error(
        self,
        index: Optional[int],
        message: str,
        exc: Optional[Exception] = None,
    ) -> None:
        error: Dict[str, Any] = {
            "normalizer": self.__class__.__name__,
            "stage": "normalize_event",
            "message": message,
        }
        if index is not None:
            error["item_index"] = index
        if exc is not None:
            error["exception_type"] = type(exc).__name__
        self.last_errors.append(error)


__all__ = ["_EventNormalizerBase"]

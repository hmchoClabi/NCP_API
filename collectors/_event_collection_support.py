"""이벤트 수집기의 공통 상태와 정규화 결과 처리를 제공한다.

페이지 번호와 종료 조건은 공급자마다 다르므로 이 모듈에서는 다루지 않는다.
각 collector는 고유한 페이지 계약을 직접 구현하고 이 공통 골격만 재사용한다.
"""

from typing import Any, Dict, List, Optional

from utils.common_rest import safe_exception_message


class _EventCollectorBase:
    """공개 이벤트 collector가 공유하는 상태 및 오류 payload 골격."""

    NORMALIZER_ERROR_API = ""

    def __init__(self, api_factory: Any, normalizer: Any):
        self.api_factory = api_factory
        self.normalizer = normalizer
        self.last_errors: List[Dict[str, Any]] = []
        self.last_events: List[Dict[str, Any]] = []
        self.last_grouped_events: Dict[str, List[Dict[str, Any]]] = {}

    def _reset_event_state(self) -> None:
        self.last_errors = []
        self.last_events = []
        self.last_grouped_events = {}

    def _normalize_and_group_events(
        self,
        raw_events: List[Dict[str, Any]],
        group_by: str,
    ) -> Dict[str, List[Dict[str, Any]]]:
        normalized_events = self.normalizer.normalize(raw_events)
        self._extend_normalizer_errors()
        grouped_events = self.normalizer.group_events(
            events=normalized_events,
            group_by=group_by,
        )
        self.last_events = normalized_events
        self.last_grouped_events = grouped_events
        return grouped_events

    def _extend_normalizer_errors(self) -> None:
        for error in getattr(self.normalizer, "last_errors", []):
            normalized_error = dict(error)
            normalized_error.setdefault(
                "collector",
                self.__class__.__name__,
            )
            normalized_error.setdefault("target_type", "event")
            normalized_error.setdefault("api", self.NORMALIZER_ERROR_API)
            self.last_errors.append(normalized_error)

    def _record_error(
        self,
        stage: str,
        api: str,
        exc: Optional[Exception] = None,
        page_no: Optional[int] = None,
        message: Optional[str] = None,
    ) -> None:
        error: Dict[str, Any] = {
            "collector": self.__class__.__name__,
            "stage": stage,
            "target_type": "event",
            "api": api,
            "message": (
                message
                or (
                    safe_exception_message(exc)
                    if exc
                    else "알 수 없는 오류"
                )
            ),
        }
        if page_no is not None:
            error["page_no"] = page_no
        if exc is not None:
            error["exception_type"] = type(exc).__name__
        self.last_errors.append(error)


__all__ = ["_EventCollectorBase"]

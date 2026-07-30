import json
import logging
from typing import Any, Dict, List, Optional

from normalizers.insighteventnormalizer import InsightEventNormalizer
from utils.common_rest import safe_exception_message
from utils.response_validation import validate_collection_response

logger = logging.getLogger(__name__)


class InsightEventCollector:
    EVENT_PAGE_SIZE = 100
    MAX_PAGES = 10_000

    def __init__(self, api_factory: Any):
        self.api_factory = api_factory
        self.normalizer = InsightEventNormalizer()
        self.last_errors: List[Dict[str, Any]] = []
        self.last_events: List[Dict[str, Any]] = []
        self.last_grouped_events: Dict[str, List[Dict[str, Any]]] = {}

    def collect(
        self,
        start_time: int,
        end_time: int,
        cw_key: Optional[str] = None,
        group_by: str = "resource",
    ) -> Dict[str, List[Dict[str, Any]]]:
        logger.info("Cloud Insight 이벤트 수집을 시작합니다.")
        self.last_errors = []
        self.last_events = []
        self.last_grouped_events = {}

        try:
            raw_events = self.collect_raw(
                start_time=start_time,
                end_time=end_time,
                cw_key=cw_key,
            )

            normalized_events = self.normalizer.normalize(raw_events)
            self._extend_normalizer_errors()

            grouped_events = self.normalizer.group_events(
                events=normalized_events,
                group_by=group_by,
            )
            self.last_events = normalized_events
            self.last_grouped_events = grouped_events

            logger.info(
                "Cloud Insight 이벤트 수집 완료: %s건",
                len(normalized_events),
            )

            return grouped_events

        except Exception as exc:
            logger.error(
                "Cloud Insight 이벤트 수집 중 오류가 발생했습니다: %s",
                safe_exception_message(exc),
            )
            self._record_error(
                stage="collect",
                api="get_search_event",
                exc=exc,
            )
            return {}

    def collect_raw(
        self,
        start_time: int,
        end_time: int,
        cw_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        insight_api = self.api_factory.get("cloud_insight")

        return self._fetch_all_events(
            insight_api=insight_api,
            start_time=start_time,
            end_time=end_time,
            cw_key=cw_key,
        )

    def _fetch_all_events(
        self,
        insight_api: Any,
        start_time: int,
        end_time: int,
        cw_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        all_events: List[Dict[str, Any]] = []
        seen_event_ids = set()
        previous_fingerprint = None
        fetched_count = 0
        page_no = 1

        while page_no <= self.MAX_PAGES:
            params = {
                "start_time": start_time,
                "end_time": end_time,
                "page_no": page_no,
                "page_size": self.EVENT_PAGE_SIZE,
            }

            try:
                # get_search_event에는 cw_key 인수가 없으므로 전체 이벤트를
                # 조회한 뒤 아래에서 prodKey를 기준으로 로컬 필터링한다.
                response = insight_api.get_search_event(**params)
            except Exception as exc:
                self._record_error(
                    stage="pagination",
                    api="get_search_event",
                    exc=exc,
                    page_no=page_no,
                )
                break

            try:
                validate_collection_response(
                    response,
                    expected_keys=("events", "eventList"),
                    allow_list=True,
                    api_name="get_search_event",
                )
                events = self._extract_events(response)
            except Exception as exc:
                self._record_error(
                    stage="response",
                    api="get_search_event",
                    exc=exc,
                    page_no=page_no,
                )
                break
            fetched_count += len(events)
            fingerprint = tuple(
                self._event_identity(event)
                for event in events
            )

            if events and fingerprint == previous_fingerprint:
                self._record_error(
                    stage="pagination_guard",
                    api="get_search_event",
                    page_no=page_no,
                    message="동일한 이벤트 페이지가 반복되어 수집을 중단했습니다.",
                )
                break

            previous_fingerprint = fingerprint
            added_count = 0

            for event in events:
                identity = self._event_identity(event)

                if identity in seen_event_ids:
                    continue

                seen_event_ids.add(identity)

                if cw_key and not self._matches_cw_key(event, cw_key):
                    continue

                all_events.append(event)
                added_count += 1

            if events and not cw_key and added_count == 0:
                self._record_error(
                    stage="pagination_guard",
                    api="get_search_event",
                    page_no=page_no,
                    message="이벤트 페이지가 진행되지 않아 수집을 중단했습니다.",
                )
                break

            total_records = self._extract_total_records(response)

            if not self._has_next_page(
                total_records=total_records,
                fetched_count=fetched_count,
                last_page_count=len(events),
            ):
                break

            page_no += 1
        else:
            self._record_error(
                stage="pagination_guard",
                api="get_search_event",
                page_no=self.MAX_PAGES,
                message=(
                    f"최대 페이지 수({self.MAX_PAGES})에 도달해 "
                    "수집을 중단했습니다."
                ),
            )

        return all_events

    def _extract_events(self, response: Any) -> List[Dict[str, Any]]:
        if isinstance(response, list):
            return [item for item in response if isinstance(item, dict)]

        if not isinstance(response, dict):
            return []

        events = self._first_present(
            response,
            ("events", "eventList", "data", "result"),
            default=[],
        )

        if isinstance(events, dict):
            events = self._first_present(
                events,
                ("events", "eventList", "items", "content"),
                default=[],
            )

        if not isinstance(events, list):
            return []

        return [event for event in events if isinstance(event, dict)]

    def _extract_total_records(self, response: Any) -> Optional[int]:
        if not isinstance(response, dict):
            return None

        containers = [response]

        for key in ("data", "result"):
            nested = response.get(key)

            if isinstance(nested, dict):
                containers.append(nested)

        candidates = []

        for container in containers:
            candidates.extend(
                [
                    container.get("totalRecords"),
                    container.get("totalCount"),
                    container.get("total"),
                ]
            )

        for value in candidates:
            if value is None:
                continue

            try:
                return int(value)
            except (TypeError, ValueError):
                continue

        return None

    def _has_next_page(
        self,
        total_records: Optional[int],
        fetched_count: int,
        last_page_count: int,
    ) -> bool:
        if last_page_count == 0:
            return False

        if total_records is None:
            return last_page_count >= self.EVENT_PAGE_SIZE

        return fetched_count < total_records

    def _matches_cw_key(
        self,
        event: Dict[str, Any],
        cw_key: str,
    ) -> bool:
        event_key = (
            event.get("prodKey")
            or event.get("cw_key")
            or event.get("cwKey")
        )
        return event_key is not None and str(event_key) == str(cw_key)

    def _event_identity(self, event: Dict[str, Any]) -> str:
        event_id = (
            event.get("eventId")
            or event.get("event_id")
            or event.get("id")
        )

        if event_id is not None and str(event_id).strip():
            return f"event:{event_id}"

        return "row:" + json.dumps(
            event,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

    def _first_present(
        self,
        mapping: Dict[str, Any],
        keys: tuple[str, ...],
        default: Any,
    ) -> Any:
        for key in keys:
            value = mapping.get(key)

            if value is not None:
                return value

        return default

    def _extend_normalizer_errors(self) -> None:
        for error in getattr(self.normalizer, "last_errors", []):
            normalized_error = dict(error)
            normalized_error.setdefault(
                "collector",
                self.__class__.__name__,
            )
            normalized_error.setdefault("target_type", "event")
            normalized_error.setdefault("api", "get_search_event")
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

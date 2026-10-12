import json
import logging
from typing import Any, Dict, List, Optional

from ._event_collection_support import _EventCollectorBase
from normalizers.activitytracereventnormalizer import ActivityTracerEventNormalizer
from utils.common_rest import safe_exception_message
from utils.response_validation import validate_collection_response

logger = logging.getLogger(__name__)


class ActivityTracerEventCollector(_EventCollectorBase):
    PAGE_SIZE = 100
    MAX_PAGES = 10_000
    NORMALIZER_ERROR_API = "get_activity_list"

    def __init__(self, api_factory: Any):
        super().__init__(api_factory, ActivityTracerEventNormalizer())

    def collect(
        self,
        start_time: int,
        end_time: int,
        nrn: Optional[str] = None,
        group_by: str = "resource",
    ) -> Dict[str, List[Dict[str, Any]]]:
        logger.info("Cloud Activity Tracer 이벤트 수집을 시작합니다.")
        self._reset_event_state()

        try:
            raw_events = self.collect_raw(
                start_time=start_time,
                end_time=end_time,
                nrn=nrn,
            )

            grouped_events = self._normalize_and_group_events(
                raw_events,
                group_by,
            )

            logger.info(
                "Cloud Activity Tracer 이벤트 수집 완료: %s건",
                len(self.last_events),
            )

            return grouped_events

        except Exception as exc:
            logger.error(
                "Cloud Activity Tracer 이벤트 수집 중 오류가 발생했습니다: %s",
                safe_exception_message(exc),
            )
            self._record_error(
                stage="collect",
                api="get_activity_list",
                exc=exc,
            )
            return {}

    def collect_raw(
        self,
        start_time: int,
        end_time: int,
        nrn: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        activity_api = self.api_factory.get("cloud_activity_tracer")

        return self._fetch_all_events(
            activity_api=activity_api,
            start_time=start_time,
            end_time=end_time,
            nrn=nrn,
        )

    def _fetch_all_events(
        self,
        activity_api: Any,
        start_time: int,
        end_time: int,
        nrn: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        all_events: List[Dict[str, Any]] = []
        seen_event_ids = set()
        previous_fingerprint = None
        page = 0

        # Activity Tracer는 0번 페이지부터 시작하고 hasMore로 종료한다.
        # nrn은 공급자 API에 전달되므로 Insight의 로컬 필터와 섞지 않는다.
        while page < self.MAX_PAGES:
            try:
                response = activity_api.get_activity_list(
                    fromEventTime=start_time,
                    toEventTime=end_time,
                    page=page,
                    size=self.PAGE_SIZE,
                    nrn=nrn,
                )
            except Exception as exc:
                self._record_error(
                    stage="pagination",
                    api="get_activity_list",
                    exc=exc,
                    page_no=page,
                )
                break

            try:
                validate_collection_response(
                    response,
                    expected_keys=("items",),
                    allow_list=True,
                    api_name="get_activity_list",
                )
                events = self._extract_events(response)
            except Exception as exc:
                self._record_error(
                    stage="response",
                    api="get_activity_list",
                    exc=exc,
                    page_no=page,
                )
                break
            fingerprint = tuple(self._event_identity(event) for event in events)

            if events and fingerprint == previous_fingerprint:
                self._record_error(
                    stage="pagination_guard",
                    api="get_activity_list",
                    page_no=page,
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
                all_events.append(event)
                added_count += 1

            if events and added_count == 0:
                self._record_error(
                    stage="pagination_guard",
                    api="get_activity_list",
                    page_no=page,
                    message="이벤트 페이지가 진행되지 않아 수집을 중단했습니다.",
                )
                break

            has_next_page = self._has_next_page(response)

            if has_next_page and not events:
                self._record_error(
                    stage="pagination_guard",
                    api="get_activity_list",
                    page_no=page,
                    message=(
                        "추가 페이지 표시가 있지만 현재 페이지가 비어 있어 수집을 중단했습니다."
                    ),
                )
                break

            if not has_next_page:
                break

            page += 1
        else:
            self._record_error(
                stage="pagination_guard",
                api="get_activity_list",
                page_no=self.MAX_PAGES - 1,
                message=(f"최대 페이지 수({self.MAX_PAGES})에 도달해 수집을 중단했습니다."),
            )

        return all_events

    def _extract_events(
        self,
        response: Any,
    ) -> List[Dict[str, Any]]:
        if isinstance(response, list):
            return [item for item in response if isinstance(item, dict)]

        if not isinstance(response, dict):
            return []

        items = response.get("items")

        if items is None:
            nested = response.get("data") or response.get("result")
            if isinstance(nested, dict):
                items = nested.get("items", [])
            elif isinstance(nested, list):
                items = nested
            else:
                items = []

        if not isinstance(items, list):
            return []

        return [item for item in items if isinstance(item, dict)]

    def _has_next_page(
        self,
        response: Any,
    ) -> bool:
        if not isinstance(response, dict):
            return False

        has_more = response.get("hasMore")

        if has_more is None:
            nested = response.get("data") or response.get("result")

            if isinstance(nested, dict):
                has_more = nested.get("hasMore", False)
            else:
                has_more = False

        if isinstance(has_more, str):
            return has_more.strip().lower() in {"true", "1", "yes", "y"}

        return bool(has_more)

    def _event_identity(self, event: Dict[str, Any]) -> str:
        event_id = event.get("historyId") or event.get("eventId") or event.get("id")

        if event_id is not None and str(event_id).strip():
            return f"event:{event_id}"

        return "row:" + json.dumps(
            event,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

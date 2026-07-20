import logging
from typing import Any, Dict, List, Optional

from normalizers.insighteventnormalizer import InsightEventNormalizer

logger = logging.getLogger(__name__)


class InsightEventCollector:
    EVENT_PAGE_SIZE = 100

    def __init__(self, api_factory: Any):
        self.api_factory = api_factory
        self.normalizer = InsightEventNormalizer()

    def collect(
        self,
        start_time: int,
        end_time: int,
        cw_key: Optional[str] = None,
        group_by: str = "resource",
    ) -> Dict[str, List[Dict[str, Any]]]:
        logger.info("Cloud Insight 이벤트 수집을 시작합니다.")

        try:
            raw_events = self.collect_raw(
                start_time=start_time,
                end_time=end_time,
                cw_key=cw_key,
            )

            normalized_events = self.normalizer.normalize(raw_events)

            grouped_events = self.normalizer.group_events(
                events=normalized_events,
                group_by=group_by,
            )

            logger.info(
                "Cloud Insight 이벤트 수집 완료: %s건",
                len(normalized_events),
            )

            return grouped_events

        except Exception:
            logger.exception("Cloud Insight 이벤트 수집 중 오류가 발생했습니다.")
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
        page_no = 1

        while True:
            params = {
                "start_time": start_time,
                "end_time": end_time,
                "page_no": page_no,
                "page_size": self.EVENT_PAGE_SIZE,
            }

            if cw_key:
                params["cw_key"] = cw_key

            response = insight_api.get_search_event(**params)

            events = self._extract_events(response)
            all_events.extend(events)

            total_records = self._extract_total_records(response)

            if not self._has_next_page(
                total_records=total_records,
                fetched_count=len(all_events),
                last_page_count=len(events),
            ):
                break

            page_no += 1

        return all_events

    def _extract_events(self, response: Any) -> List[Dict[str, Any]]:
        if isinstance(response, list):
            return [item for item in response if isinstance(item, dict)]

        if not isinstance(response, dict):
            return []

        events = (
            response.get("events")
            or response.get("eventList")
            or response.get("data")
            or response.get("result")
            or []
        )

        if isinstance(events, dict):
            events = (
                events.get("events")
                or events.get("eventList")
                or events.get("items")
                or events.get("content")
                or []
            )

        if not isinstance(events, list):
            return []

        return [event for event in events if isinstance(event, dict)]

    def _extract_total_records(self, response: Any) -> Optional[int]:
        if not isinstance(response, dict):
            return None

        candidates = [
            response.get("totalRecords"),
            response.get("totalCount"),
            response.get("total"),
        ]

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
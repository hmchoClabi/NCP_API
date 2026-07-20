import logging
from typing import Any, Dict, List, Optional

from normalizers.activitytracereventnormalizer import ActivityTracerEventNormalizer

logger = logging.getLogger(__name__)


class ActivityTracerEventCollector:
    PAGE_SIZE = 100

    def __init__(self, api_factory: Any):
        self.api_factory = api_factory
        self.normalizer = ActivityTracerEventNormalizer()

    def collect(
        self,
        start_time: int,
        end_time: int,
        nrn: Optional[str] = None,
        group_by: str = "resource",
    ) -> Dict[str, List[Dict[str, Any]]]:
        logger.info("Cloud Activity Tracer 이벤트 수집을 시작합니다.")

        try:
            raw_events = self.collect_raw(
                start_time=start_time,
                end_time=end_time,
                nrn=nrn,
            )

            normalized_events = self.normalizer.normalize(raw_events)

            grouped_events = self.normalizer.group_events(
                events=normalized_events,
                group_by=group_by,
            )

            logger.info(
                "Cloud Activity Tracer 이벤트 수집 완료: %s건",
                len(normalized_events),
            )

            return grouped_events

        except Exception:
            logger.exception("Cloud Activity Tracer 이벤트 수집 중 오류가 발생했습니다.")
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
        page = 0

        while True:
            response = activity_api.get_activity_list(
                fromEventTime=start_time,
                toEventTime=end_time,
                page=page,
                size=self.PAGE_SIZE,
                nrn=nrn,
            )

            events = self._extract_events(response)
            all_events.extend(events)

            if not self._has_next_page(response):
                break

            page += 1

        return all_events

    def _extract_events(
        self,
        response: Any,
    ) -> List[Dict[str, Any]]:
        if not isinstance(response, dict):
            return []

        items = response.get("items", [])

        if not isinstance(items, list):
            return []

        return [
            item for item in items
            if isinstance(item, dict)
        ]

    def _has_next_page(
        self,
        response: Any,
    ) -> bool:
        if not isinstance(response, dict):
            return False

        return bool(response.get("hasMore", False))
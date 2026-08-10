from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from ._event_normalizer_support import _EventNormalizerBase


class ActivityTracerEventNormalizer(_EventNormalizerBase):
    """Activity Tracer 필드·시간·그룹 키를 공통 이벤트 계약으로 변환한다."""

    KST = ZoneInfo("Asia/Seoul")
    SORT_FIELDS = ("event_time",)

    def _get_group_key(
        self,
        event: Dict[str, Any],
        group_by: str,
    ) -> str:
        if group_by == "resource":
            return (
                event.get("resource_id")
                or event.get("resource_name")
                or event.get("nrn")
                or "unknown"
            )

        if group_by == "product":
            return (
                event.get("product_display_name")
                or event.get("product_name")
                or "unknown"
            )

        if group_by == "action":
            return event.get("action_name") or "unknown"

        if group_by == "result":
            return event.get("result") or "unknown"

        if group_by == "source_ip":
            return event.get("source_ip") or "unknown"

        if group_by == "source_type":
            return event.get("source_type") or "unknown"

        if group_by == "user_type":
            return event.get("user_type") or "unknown"

        return "all"

    def _normalize_event(
        self,
        event: Dict[str, Any],
    ) -> Dict[str, Any]:
        product_data = event.get("productData") or {}
        event_time = event.get("eventTime")

        if not isinstance(product_data, dict):
            product_data = {}

        return {
            "event_id": event.get("historyId"),
            "nrn": event.get("nrn"),
            "event_time": event_time,
            "event_time_kst": self._format_event_time_kst(event_time),

            "platform_type": event.get("platformType"),

            "product_name": event.get("productName"),
            "product_display_name": event.get("productDisplayName"),

            "region_code": event.get("regionCode"),
            "region_display_name": event.get("regionDisplayName"),

            "resource_type": event.get("resourceType"),
            "resource_id": event.get("resourceId"),
            "resource_name": event.get("resourceName"),

            "action_name": event.get("actionDisplayName"),
            "result": event.get("actionResultType"),

            "user_type": event.get("actionUserType"),
            "sub_account_no": event.get("actionSubAccountNo"),

            "source_type": event.get("sourceType"),
            "source_ip": event.get("sourceIp"),

            "product_data": product_data,

            # productData 안에 자주 들어오는 보조 필드
            "member_no": product_data.get("memberNo"),
            "instance_no": product_data.get("instanceNo"),
            "user_name": product_data.get("userName"),
            "client_ip": product_data.get("clientIp"),

            # 원본 보존
            "raw": event,
        }

    def _format_event_time_kst(self, value: Any) -> Optional[str]:
        if value is None or isinstance(value, bool):
            return None

        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            return None

        # Activity Tracer eventTime is Unix epoch milliseconds. Accepting
        # seconds as well keeps the normalizer tolerant of older fixtures.
        if abs(timestamp) >= 100_000_000_000:
            timestamp /= 1000

        try:
            event_dt = datetime.fromtimestamp(timestamp, tz=self.KST)
        except (OSError, OverflowError, ValueError):
            return None

        milliseconds = event_dt.microsecond // 1000
        return (
            event_dt.strftime("%Y-%m-%d %H:%M:%S")
            + f".{milliseconds:03d} KST"
        )

from collections import defaultdict
from typing import Any, Dict, List, Optional


class ActivityTracerEventNormalizer:
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

        return result

    def group_events(
        self,
        events: List[Dict[str, Any]],
        group_by: str = "resource",
    ) -> Dict[str, List[Dict[str, Any]]]:
        result: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for event in events:
            if not isinstance(event, dict):
                continue

            group_key = self._get_group_key(
                event=event,
                group_by=group_by,
            )
            result[group_key].append(event)

        return dict(result)

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

        if not isinstance(product_data, dict):
            product_data = {}

        return {
            "event_id": event.get("historyId"),
            "nrn": event.get("nrn"),
            "event_time": event.get("eventTime"),

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

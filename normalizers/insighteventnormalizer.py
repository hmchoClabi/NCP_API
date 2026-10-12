from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from utils.event_sort import event_timestamp_millis

from ._event_normalizer_support import _EventNormalizerBase


class InsightEventNormalizer(_EventNormalizerBase):
    """Cloud Insight 필드·시간·그룹 키를 공통 이벤트 계약으로 변환한다."""

    KST = ZoneInfo("Asia/Seoul")
    SORT_FIELDS = ("start_time", "end_time")

    def _get_group_key(
        self,
        event: Dict[str, Any],
        group_by: str,
    ) -> str:
        if group_by == "resource":
            return (
                event.get("resource_id")
                or event.get("resource_name")
                or event.get("prod_key")
                or "unknown"
            )

        if group_by == "product":
            return event.get("prod_name") or event.get("prod_key") or "unknown"

        if group_by == "level":
            return event.get("level") or "unknown"

        if group_by == "metric":
            return event.get("metric") or "unknown"

        return "all"

    def _normalize_event(
        self,
        event: Dict[str, Any],
    ) -> Dict[str, Any]:
        dimension = self._normalize_dimension(event.get("dimension"))

        resource_id = self._extract_resource_id(
            event=event,
            dimension=dimension,
        )

        return {
            "event_id": event.get("eventId"),
            "resource_id": resource_id,
            "resource_name": event.get("resourceName"),
            "resource_type": event.get("prodName"),
            "level": event.get("eventLevel"),
            "metric": event.get("metric"),
            "criteria": event.get("criteria"),
            "operator": event.get("operator"),
            "operator_symbol": event.get("operatorSymbol"),
            "detect_value": event.get("detectValue"),
            "unit": event.get("unit"),
            "rule_id": event.get("ruleId"),
            "rule_name": event.get("ruleName"),
            "description": event.get("describe"),
            "calc": event.get("calc"),
            "interval": event.get("interval"),
            "metric_group_item_id": event.get("metricGroupItemId"),
            "calc_sliding_group_key": event.get("calcSlidingGroupKey"),
            "notification_groups": event.get("notificationGroups"),
            "notification_status": event.get("notificationStatus"),
            "in_maintenance": event.get("inMaintenance"),
            "resource_deleted": event.get("resourceDeleted"),
            "start_time": event.get("startTime"),
            "end_time": event.get("endTime"),
            "start_time_kst": self._format_event_time(event.get("startTime")),
            "end_time_kst": self._format_event_time(event.get("endTime")),
            "prod_key": event.get("prodKey"),
            "prod_name": event.get("prodName"),
            "region_code": event.get("regionCode"),
            "zone_code": event.get("zoneCode"),
            "dimension": dimension,
            # 원본 보존
            "raw": event,
        }

    def _format_event_time(self, value: Any) -> Optional[str]:
        timestamp = event_timestamp_millis(value)
        if timestamp is None or timestamp <= 0:
            return None
        event_time = datetime.fromtimestamp(
            timestamp / 1000,
            tz=self.KST,
        )
        return event_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " KST"

    def _extract_resource_id(
        self,
        event: Dict[str, Any],
        dimension: Dict[str, Any],
    ) -> Optional[str]:
        candidates = [
            dimension.get("instanceNo"),
            dimension.get("serverInstanceNo"),
            dimension.get("loadBalancerNo"),
            dimension.get("targetGroupNo"),
            dimension.get("autoScalingGroupNo"),
            dimension.get("nasVolumeInstanceNo"),
            dimension.get("dbInstanceNo"),
            dimension.get("cloudDbInstanceNo"),
            dimension.get("clusterNo"),
            dimension.get("bucketName"),
            dimension.get("resourceId"),
            dimension.get("resourceNo"),
            event.get("resourceId"),
            event.get("resourceNo"),
            event.get("resourceName"),
        ]

        for value in candidates:
            if value:
                return str(value)

        return None

    def _normalize_dimension(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value

        if not isinstance(value, list):
            return {}

        result: Dict[str, Any] = {}

        for item in value:
            if not isinstance(item, dict):
                continue

            name = item.get("dim") or item.get("name") or item.get("dimension")
            item_value = item.get("val") if item.get("val") is not None else item.get("value")

            if name and item_value is not None:
                result[str(name)] = item_value

        return result

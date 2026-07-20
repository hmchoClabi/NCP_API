from collections import defaultdict
from typing import Any, Dict, List, Optional


class InsightEventNormalizer:
    def normalize(
        self,
        raw_events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return [
            self._normalize_event(event)
            for event in raw_events
        ]

    def group_events(
        self,
        events: List[Dict[str, Any]],
        group_by: str = "resource",
    ) -> Dict[str, List[Dict[str, Any]]]:
        result: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for event in events:
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
                or event.get("prod_key")
                or "unknown"
            )

        if group_by == "product":
            return (
                event.get("prod_name")
                or event.get("prod_key")
                or "unknown"
            )

        if group_by == "level":
            return event.get("level") or "unknown"

        if group_by == "metric":
            return event.get("metric") or "unknown"

        return "all"

    def _normalize_event(
        self,
        event: Dict[str, Any],
    ) -> Dict[str, Any]:
        dimension = event.get("dimension") or {}

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
            "notification_groups": event.get("notificationGroups"),
            "notification_status": event.get("notificationStatus"),
            "in_maintenance": event.get("inMaintenance"),
            "resource_deleted": event.get("resourceDeleted"),
            "start_time": event.get("startTime"),
            "end_time": event.get("endTime"),
            "prod_key": event.get("prodKey"),
            "prod_name": event.get("prodName"),
            "region_code": event.get("regionCode"),
            "zone_code": event.get("zoneCode"),
            "dimension": dimension,

            # 원본 보존
            "raw": event,
        }

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
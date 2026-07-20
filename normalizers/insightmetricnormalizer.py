import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class InsightMetricNormalizer:
    OS_MOUNT_POINTS = {
        "/",
        "/root",
        "/boot",
        "/boot/efi",
    }

    def __init__(
        self,
        aggregations: Dict[str, str],
        simple_metrics: List[Dict[str, Any]],
        filesystem_metric: Dict[str, Any],
    ):
        self.aggregations = aggregations
        self.simple_metrics = simple_metrics
        self.filesystem_metric = filesystem_metric

    def merge_metric_response(
        self,
        raw_metrics: Dict[str, Dict[str, Dict[str, List[Dict[str, Any]]]]],
        response: Any,
        stat_name: str,
    ) -> None:
        if not isinstance(response, list):
            logger.warning("Cloud Insight 응답이 list가 아닙니다: %s", response)
            return

        for item in response:
            if not isinstance(item, dict):
                continue

            dimensions = item.get("dimensions") or {}
            instance_no = dimensions.get("instanceNo")
            metric_name = item.get("metric")
            dps = item.get("dps") or []

            if not instance_no or not metric_name:
                continue

            values = self._extract_dps_values(dps)

            raw_metrics[instance_no][metric_name][stat_name].append(
                {
                    "values": values,
                    "dimensions": dimensions,
                    "raw": item,
                }
            )

    def _extract_dps_values(
        self,
        dps: List[Any],
    ) -> List[float]:
        values = []

        for point in dps:
            if not isinstance(point, (list, tuple)):
                continue

            if len(point) < 2:
                continue

            value = point[1]

            if value is None:
                continue

            try:
                values.append(float(value))
            except (TypeError, ValueError):
                continue

        return values

    def build_report_metrics(
        self,
        raw_metrics: Dict[str, Dict[str, Dict[str, List[Dict[str, Any]]]]],
        servers: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = []

        for server in servers:
            instance_no = server.get("server_id")
            metric_data = raw_metrics.get(instance_no, {})

            report = self._create_base_report(server)

            for metric_config in self.simple_metrics:
                self._apply_simple_metric(
                    report=report,
                    metric_data=metric_data,
                    metric_name=metric_config["metric"],
                    output_prefix=metric_config["output_prefix"],
                )

            self._apply_filesystem_metric(
                report=report,
                metric_data=metric_data,
                metric_name=self.filesystem_metric["metric"],
            )

            report["raw_metrics"] = metric_data
            result.append(report)

        return result

    def build_empty_reports(
        self,
        servers: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return [
            self._create_base_report(server)
            for server in servers
        ]

    def _create_base_report(
        self,
        server: Dict[str, Any],
    ) -> Dict[str, Any]:
        report = {
            "server_id": server.get("server_id"),
            "server_name": server.get("server_name"),
        }

        for metric_config in self.simple_metrics:
            self._init_stat_fields(report, metric_config["output_prefix"])

        self._init_stat_fields(report, "os_fs")
        self._init_stat_fields(report, "data_fs")

        report["os_fs_details"] = []
        report["data_fs_details"] = []

        return report

    def _init_stat_fields(
        self,
        report: Dict[str, Any],
        prefix: str,
    ) -> None:
        report[f"{prefix}_min"] = None
        report[f"{prefix}_avg"] = None
        report[f"{prefix}_max"] = None

    def _apply_simple_metric(
        self,
        report: Dict[str, Any],
        metric_data: Dict[str, Dict[str, List[Dict[str, Any]]]],
        metric_name: str,
        output_prefix: str,
    ) -> None:
        stat_entries = metric_data.get(metric_name, {})

        for stat_name in self.aggregations:
            entries = stat_entries.get(stat_name, [])
            values = self._collect_metric_values(entries)

            report[f"{output_prefix}_{stat_name}"] = self._reduce_values(
                values=values,
                stat_name=stat_name,
            )

    def _apply_filesystem_metric(
        self,
        report: Dict[str, Any],
        metric_data: Dict[str, Dict[str, List[Dict[str, Any]]]],
        metric_name: str,
    ) -> None:
        stat_entries = metric_data.get(metric_name, {})
        fs_summary = self._summarize_filesystem_entries(stat_entries)

        for stat_name in self.aggregations:
            report[f"os_fs_{stat_name}"] = self._reduce_values(
                values=fs_summary["os_values_by_stat"].get(stat_name, []),
                stat_name=stat_name,
            )

            report[f"data_fs_{stat_name}"] = self._reduce_values(
                values=fs_summary["data_values_by_stat"].get(stat_name, []),
                stat_name=stat_name,
            )

        report["os_fs_details"] = fs_summary["os_details"]
        report["data_fs_details"] = fs_summary["data_details"]

    def _summarize_filesystem_entries(
        self,
        stat_entries: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        os_values_by_stat = defaultdict(list)
        data_values_by_stat = defaultdict(list)

        os_mount_values = defaultdict(lambda: defaultdict(list))
        data_mount_values = defaultdict(lambda: defaultdict(list))

        for stat_name, entries in stat_entries.items():
            for entry in entries:
                mount_name = self._get_mount_name(entry)
                values = entry.get("values") or []

                if not mount_name or not values:
                    continue

                if self._is_os_mount(mount_name):
                    os_values_by_stat[stat_name].extend(values)
                    os_mount_values[mount_name][stat_name].extend(values)
                else:
                    data_values_by_stat[stat_name].extend(values)
                    data_mount_values[mount_name][stat_name].extend(values)

        return {
            "os_values_by_stat": os_values_by_stat,
            "data_values_by_stat": data_values_by_stat,
            "os_details": self._build_mount_details(os_mount_values),
            "data_details": self._build_mount_details(data_mount_values),
        }

    def _build_mount_details(
        self,
        mount_values: Dict[str, Dict[str, List[float]]],
    ) -> List[Dict[str, Any]]:
        details = []

        for mount_name, values_by_stat in mount_values.items():
            detail = {
                "mount": mount_name,
            }

            for stat_name in self.aggregations:
                detail[stat_name] = self._reduce_values(
                    values=values_by_stat.get(stat_name, []),
                    stat_name=stat_name,
                )

            details.append(detail)

        return sorted(
            details,
            key=lambda item: item.get("mount") or "",
        )

    def _get_mount_name(
        self,
        entry: Dict[str, Any],
    ) -> Optional[str]:
        dimensions = entry.get("dimensions") or {}
        mount_name = dimensions.get("mnt_nm")

        if mount_name is None:
            return None

        return str(mount_name)

    def _is_os_mount(
        self,
        mount_name: str,
    ) -> bool:
        return mount_name in self.OS_MOUNT_POINTS

    def _collect_metric_values(
        self,
        metric_entries: List[Dict[str, Any]],
    ) -> List[float]:
        values = []

        for entry in metric_entries:
            values.extend(entry.get("values") or [])

        return values

    def _reduce_values(
        self,
        values: List[float],
        stat_name: str,
    ) -> Optional[float]:
        if not values:
            return None

        if stat_name == "min":
            return round(min(values), 2)

        if stat_name == "avg":
            return round(sum(values) / len(values), 2)

        if stat_name == "max":
            return round(max(values), 2)

        return None
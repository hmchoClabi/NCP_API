import logging
import pprint
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set

from normalizers.insightmetricnormalizer import InsightMetricNormalizer

logger = logging.getLogger(__name__)


class InsightMetricCollector:
    MAX_QUERY_SIZE = 20
    SERVER_PROD_NAME = "Server(VPC)"

    AGGREGATIONS = {
        "min": "MIN",
        "avg": "AVG",
        "max": "MAX",
    }

    SIMPLE_METRICS = [
        {
            "metric": "used_rto",
            "output_prefix": "cpu",
            "interval": "Min1",
            "dimensions": {"type": "cpu"},
        },
        {
            "metric": "mem_usert",
            "output_prefix": "mem",
            "interval": "Min5",
            "dimensions": {"type": "memory"},
        },
    ]

    FILESYSTEM_METRIC = {
        "metric": "fs_usert",
        "interval": "Min5",
        "dimensions": {"type": "fs"},
    }

    def __init__(self, api_factory: Any, debug: bool = False):
        self.api_factory = api_factory
        self.debug = debug
        self.normalizer = InsightMetricNormalizer(
            aggregations=self.AGGREGATIONS,
            simple_metrics=self.SIMPLE_METRICS,
            filesystem_metric=self.FILESYSTEM_METRIC,
        )

        self._cw_key_map: Optional[Dict[str, str]] = None
        self._filesystem_mount_candidates: Optional[Set[str]] = None

    def collect(
        self,
        servers: List[Dict[str, Any]],
        start_time: int,
        end_time: int,
    ) -> List[Dict[str, Any]]:
        logger.info("인사이트 metric 데이터 수집을 시작합니다.")

        try:
            if not servers:
                logger.warning("서버 목록이 없어 인사이트 metric 수집을 건너뜁니다.")
                return []

            metric_queries = self._build_metric_queries(servers)

            if not metric_queries:
                logger.warning("조회할 Cloud Insight metric 정보가 없습니다.")
                return self.normalizer.build_empty_reports(servers)

            self._debug_insight_request(
                servers=servers,
                start_time=start_time,
                end_time=end_time,
                metric_queries=metric_queries,
            )

            raw_metrics = self._execute_metric_queries(
                metric_queries=metric_queries,
                start_time=start_time,
                end_time=end_time,
            )

            result = self.normalizer.build_report_metrics(
                raw_metrics=raw_metrics,
                servers=servers,
            )

            logger.info("인사이트 metric 데이터 수집이 완료되었습니다.")
            return result

        except Exception:
            logger.exception("인사이트 metric 데이터 수집 중 오류가 발생했습니다.")
            return []

    def _build_metric_queries(
        self,
        servers: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        server_cw_key = self._get_cw_key(self.SERVER_PROD_NAME)

        if not server_cw_key:
            logger.error("%s cw_key를 찾을 수 없습니다.", self.SERVER_PROD_NAME)
            return []

        metric_queries = []

        for server in servers:
            instance_no = server.get("server_id")

            if not instance_no:
                logger.warning("server_id가 없는 서버는 제외됩니다: %s", server)
                continue

            metric_queries.extend(
                self._build_simple_metric_queries(
                    prod_key=server_cw_key,
                    instance_no=instance_no,
                )
            )

            metric_queries.extend(
                self._build_filesystem_metric_queries(
                    prod_key=server_cw_key,
                    instance_no=instance_no,
                )
            )

        return metric_queries

    def _build_simple_metric_queries(
        self,
        prod_key: str,
        instance_no: str,
    ) -> List[Dict[str, Any]]:
        result = []

        for metric_config in self.SIMPLE_METRICS:
            for stat_name, aggregation in self.AGGREGATIONS.items():
                dimensions = {"instanceNo": instance_no}
                dimensions.update(metric_config.get("dimensions", {}))

                result.append(
                    {
                        "stat_name": stat_name,
                        "payload": self._make_metric_payload(
                            prod_key=prod_key,
                            metric_config=metric_config,
                            dimensions=dimensions,
                            aggregation=aggregation,
                        ),
                    }
                )

        return result

    def _build_filesystem_metric_queries(
        self,
        prod_key: str,
        instance_no: str,
    ) -> List[Dict[str, Any]]:
        mount_points = self._get_filesystem_mount_candidates(prod_key)

        if not mount_points:
            logger.warning("filesystem mnt_nm 후보가 없어 fs_usert 조회를 건너뜁니다.")
            return []

        result = []

        for mount_point in sorted(mount_points):
            for stat_name, aggregation in self.AGGREGATIONS.items():
                dimensions = {"instanceNo": instance_no}
                dimensions.update(self.FILESYSTEM_METRIC.get("dimensions", {}))
                dimensions["mnt_nm"] = mount_point

                result.append(
                    {
                        "stat_name": stat_name,
                        "payload": self._make_metric_payload(
                            prod_key=prod_key,
                            metric_config=self.FILESYSTEM_METRIC,
                            dimensions=dimensions,
                            aggregation=aggregation,
                        ),
                    }
                )

        return result

    def _make_metric_payload(
        self,
        prod_key: str,
        metric_config: Dict[str, Any],
        dimensions: Dict[str, Any],
        aggregation: str,
    ) -> Dict[str, Any]:
        return {
            "prodKey": prod_key,
            "metric": metric_config["metric"],
            "interval": metric_config.get("interval", "Min5"),
            "aggregation": aggregation,
            "queryAggregation": aggregation,
            "dimensions": dimensions,
        }

    def _execute_metric_queries(
        self,
        metric_queries: List[Dict[str, Any]],
        start_time: int,
        end_time: int,
    ) -> Dict[str, Dict[str, Dict[str, List[Dict[str, Any]]]]]:
        insight_api = self.api_factory.get("cloud_insight")
        raw_metrics = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        queries_by_stat = defaultdict(list)

        for query in metric_queries:
            queries_by_stat[query["stat_name"]].append(query["payload"])

        for stat_name, payloads in queries_by_stat.items():
            for chunk in self._chunk_list(payloads, self.MAX_QUERY_SIZE):
                response = insight_api.get_query_data_multiple(
                    time_start=start_time,
                    time_end=end_time,
                    metric_info_list=chunk,
                )

                self.normalizer.merge_metric_response(
                    raw_metrics=raw_metrics,
                    response=response,
                    stat_name=stat_name,
                )

        return raw_metrics

    def _get_filesystem_mount_candidates(
        self,
        prod_key: str,
    ) -> Set[str]:
        if self._filesystem_mount_candidates is not None:
            return self._filesystem_mount_candidates

        insight_api = self.api_factory.get("cloud_insight")

        response = self._search_metric_list(
            insight_api=insight_api,
            prod_key=prod_key,
        )

        metric_items = self._extract_metric_items(response)
        mount_points = set()

        for item in metric_items:
            metric_name = (
                item.get("metric")
                or item.get("metricName")
                or item.get("name")
            )

            if metric_name != self.FILESYSTEM_METRIC["metric"]:
                continue

            for dimension in item.get("dimensions") or []:
                if not isinstance(dimension, dict):
                    continue

                dim_name = (
                    dimension.get("dim")
                    or dimension.get("name")
                    or dimension.get("dimension")
                )

                dim_value = (
                    dimension.get("val")
                    or dimension.get("value")
                    or dimension.get("dimensionValue")
                )

                if dim_name == "mnt_nm" and dim_value:
                    mount_points.add(str(dim_value))

        self._filesystem_mount_candidates = mount_points

        logger.info(
            "filesystem mnt_nm 후보 %s개를 캐싱했습니다: %s",
            len(mount_points),
            sorted(mount_points),
        )

        return self._filesystem_mount_candidates

    def _search_metric_list(
        self,
        insight_api: Any,
        prod_key: str,
    ) -> Any:
        if hasattr(insight_api, "get_search_metric_list"):
            return insight_api.get_search_metric_list(prod_key=prod_key)

        if hasattr(insight_api, "search_metric_list"):
            return insight_api.search_metric_list(prod_key=prod_key)

        raise AttributeError(
            "CloudInsightAPI에 get_search_metric_list(prod_key) 메서드가 필요합니다."
        )

    def _extract_metric_items(
        self,
        response: Any,
    ) -> List[Dict[str, Any]]:
        if isinstance(response, list):
            return [item for item in response if isinstance(item, dict)]

        if not isinstance(response, dict):
            return []

        candidates = (
            response.get("metrics")
            or response.get("metricList")
            or response.get("data")
            or response.get("result")
            or []
        )

        if isinstance(candidates, dict):
            candidates = (
                candidates.get("metrics")
                or candidates.get("metricList")
                or candidates.get("items")
                or []
            )

        if not isinstance(candidates, list):
            return []

        return [item for item in candidates if isinstance(item, dict)]

    def _get_cw_key(
        self,
        prod_name: str,
    ) -> Optional[str]:
        cw_key_map = self._get_cw_key_map()
        return cw_key_map.get(prod_name)

    def _get_cw_key_map(self) -> Dict[str, str]:
        if self._cw_key_map is not None:
            return self._cw_key_map

        insight_api = self.api_factory.get("cloud_insight")
        response = insight_api.get_system_schema_key_list()

        if isinstance(response, list):
            schema_items = response
        elif isinstance(response, dict):
            schema_items = (
                response.get("result")
                or response.get("data")
                or response.get("schemaList")
                or response.get("systemSchemaList")
                or []
            )
        else:
            schema_items = []

        self._cw_key_map = {
            item.get("prodName"): item.get("cw_key")
            for item in schema_items
            if isinstance(item, dict)
            and item.get("prodName")
            and item.get("cw_key")
        }

        logger.info(
            "Cloud Insight cw_key %s개를 캐싱했습니다.",
            len(self._cw_key_map),
        )

        return self._cw_key_map

    def _chunk_list(
        self,
        items: List[Any],
        size: int,
    ) -> Iterable[List[Any]]:
        for i in range(0, len(items), size):
            yield items[i:i + size]

    def _debug_insight_request(
        self,
        servers: List[Dict[str, Any]],
        start_time: int,
        end_time: int,
        metric_queries: List[Dict[str, Any]],
    ) -> None:
        if not self.debug:
            return

        logger.debug("=" * 100)
        logger.debug("CLOUD INSIGHT DEBUG")
        logger.debug("=" * 100)

        logger.debug("[TIME]")
        logger.debug("start_time: %s", start_time)
        logger.debug("end_time  : %s", end_time)
        logger.debug("start_dt  : %s", datetime.fromtimestamp(start_time / 1000))
        logger.debug("end_dt    : %s", datetime.fromtimestamp(end_time / 1000))

        logger.debug("[TARGET SERVERS]")

        for server in servers:
            logger.debug(
                "%s | id=%s | status=%s | create_date=%s",
                server.get("server_name"),
                server.get("server_id"),
                server.get("status"),
                server.get("create_date"),
            )

        logger.debug("[METRIC QUERIES]")
        logger.debug("count: %s", len(metric_queries))
        logger.debug(
            "\n%s",
            pprint.pformat(
                metric_queries,
                indent=2,
                width=140,
                sort_dicts=False,
            ),
        )

        logger.debug("=" * 100)
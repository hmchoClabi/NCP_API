import logging
from collections import defaultdict
from datetime import datetime
from itertools import batched
from typing import Any, Dict, List, Optional, Set
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta

from normalizers.insightmetricnormalizer import InsightMetricNormalizer
from utils.common_rest import safe_exception_message
from utils.response_validation import validate_collection_response

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
    KST = ZoneInfo("Asia/Seoul")

    def __init__(self, api_factory: Any):
        self.api_factory = api_factory
        self.normalizer = InsightMetricNormalizer(
            aggregations=self.AGGREGATIONS,
            simple_metrics=self.SIMPLE_METRICS,
            filesystem_metric=self.FILESYSTEM_METRIC,
        )

        self._cw_key_map: Optional[Dict[str, str]] = None
        self._filesystem_mount_candidates: Optional[Set[str]] = None
        self._filesystem_mount_candidates_by_instance: Dict[str, Set[str]] = {}
        self._supports_mount_dimension_filter: Optional[bool] = None
        self.last_errors: List[Dict[str, Any]] = []

    def collect(
        self,
        servers: List[Dict[str, Any]],
        start_time: int,
        end_time: int,
    ) -> List[Dict[str, Any]]:
        logger.info("인사이트 metric 데이터 수집을 시작합니다.")
        self.last_errors = []
        eligible_servers = self._filter_servers_for_period(
            servers=servers,
            start_time=start_time,
            end_time=end_time,
        )

        try:
            if not eligible_servers:
                logger.warning("서버 목록이 없어 인사이트 metric 수집을 건너뜁니다.")
                return []

            interval = self._select_metric_interval(
                start_time=start_time,
                end_time=end_time,
            )
            metric_queries = self._build_metric_queries(
                eligible_servers,
                interval=interval,
            )

            if not metric_queries:
                logger.warning("조회할 Cloud Insight metric 정보가 없습니다.")
                return self.normalizer.build_empty_reports(eligible_servers)

            raw_metrics = self._execute_metric_queries(
                metric_queries=metric_queries,
                start_time=start_time,
                end_time=end_time,
            )

            result = self.normalizer.build_report_metrics(
                raw_metrics=raw_metrics,
                servers=eligible_servers,
            )
            for report in result:
                report["metric_interval"] = interval

            logger.info("인사이트 metric 데이터 수집이 완료되었습니다.")
            return result

        except Exception as exc:
            logger.error(
                "인사이트 metric 데이터 수집 중 오류가 발생했습니다: %s",
                safe_exception_message(exc),
            )
            self._record_error(
                stage="collect",
                api="cloud_insight",
                exc=exc,
            )
            return self.normalizer.build_empty_reports(eligible_servers)

    def _build_metric_queries(
        self,
        servers: List[Dict[str, Any]],
        interval: str,
    ) -> List[Dict[str, Any]]:
        server_cw_key = self._get_cw_key(self.SERVER_PROD_NAME)

        if not server_cw_key:
            logger.error("%s cw_key를 찾을 수 없습니다.", self.SERVER_PROD_NAME)
            self._record_error(
                stage="schema_lookup",
                api="get_system_schema_key_list",
                product_key=None,
                message=f"{self.SERVER_PROD_NAME} cw_key를 찾을 수 없습니다.",
            )
            return []

        metric_queries = []

        for server in servers:
            instance_no = self._normalize_id(server.get("server_id"))

            if not instance_no:
                logger.warning("server_id가 없는 서버는 제외됩니다: %s", server)
                continue

            metric_queries.extend(
                self._build_simple_metric_queries(
                    prod_key=server_cw_key,
                    instance_no=instance_no,
                    interval=interval,
                )
            )

            metric_queries.extend(
                self._build_filesystem_metric_queries(
                    prod_key=server_cw_key,
                    instance_no=instance_no,
                    interval=interval,
                )
            )

        return metric_queries

    def _build_simple_metric_queries(
        self,
        prod_key: str,
        instance_no: str,
        interval: str,
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
                            interval=interval,
                        ),
                    }
                )

        return result

    def _build_filesystem_metric_queries(
        self,
        prod_key: str,
        instance_no: str,
        interval: str,
    ) -> List[Dict[str, Any]]:
        try:
            mount_points = self._get_filesystem_mount_candidates(
                prod_key,
                instance_no=instance_no,
            )
        except Exception as exc:
            self._record_error(
                stage="filesystem_discovery",
                api="get_search_metric_list",
                exc=exc,
                target_id=instance_no,
                product_key=prod_key,
                metric=self.FILESYSTEM_METRIC["metric"],
            )
            return []

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
                            interval=interval,
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
        interval: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "prodKey": prod_key,
            "metric": metric_config["metric"],
            "interval": (
                interval
                or metric_config.get("interval", "Min5")
            ),
            "aggregation": aggregation,
            "queryAggregation": aggregation,
            "dimensions": dimensions,
        }

    def _select_metric_interval(
        self,
        start_time: int,
        end_time: int,
        now_time: Optional[int] = None,
    ) -> str:
        del end_time
        now_dt = (
            datetime.fromtimestamp(now_time / 1000, tz=self.KST)
            if now_time is not None
            else datetime.now(self.KST)
        )
        start_dt = datetime.fromtimestamp(
            start_time / 1000,
            tz=self.KST,
        )

        if start_dt >= now_dt - relativedelta(days=8):
            return "Min1"
        if start_dt >= now_dt - relativedelta(months=1):
            return "Min5"
        if start_dt >= now_dt - relativedelta(months=3):
            return "Min30"
        if start_dt >= now_dt - relativedelta(months=6):
            return "Hour2"
        return "Day1"

    def _query_time_windows(
        self,
        start_time: int,
        end_time: int,
        interval: str,
    ) -> List[tuple[int, int]]:
        day = 24 * 60 * 60 * 1000
        window_size = {
            "Min1": day,
            "Min5": 7 * day,
            "Min30": 31 * day,
            "Hour2": 31 * day,
            "Day1": 366 * day,
        }.get(interval, 7 * day)

        result = []
        cursor = start_time
        while cursor <= end_time:
            window_end = min(cursor + window_size - 1, end_time)
            result.append((cursor, window_end))
            cursor = window_end + 1
        return result

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
            for chunk in batched(payloads, self.MAX_QUERY_SIZE):
                interval = str(chunk[0].get("interval") or "Min5")
                time_windows = self._query_time_windows(
                    start_time=start_time,
                    end_time=end_time,
                    interval=interval,
                )

                for window_start, window_end in time_windows:
                    try:
                        response = insight_api.get_query_data_multiple(
                            time_start=window_start,
                            time_end=window_end,
                            metric_info_list=chunk,
                        )
                    except Exception as exc:
                        target_ids = sorted(
                            {
                                str(
                                    payload.get("dimensions", {}).get(
                                        "instanceNo"
                                    )
                                )
                                for payload in chunk
                                if payload.get("dimensions", {}).get(
                                    "instanceNo"
                                )
                                is not None
                            }
                        )
                        metric_names = sorted(
                            {
                                str(payload.get("metric"))
                                for payload in chunk
                                if payload.get("metric") is not None
                            }
                        )
                        self._record_error(
                            stage="query",
                            api="get_query_data_multiple",
                            exc=exc,
                            target_id=",".join(target_ids) or None,
                            product_key=(
                                str(chunk[0].get("prodKey"))
                                if (
                                    chunk
                                    and chunk[0].get("prodKey") is not None
                                )
                                else None
                            ),
                            metric=",".join(metric_names) or None,
                            stat_name=stat_name,
                        )
                        continue

                    try:
                        validate_collection_response(
                            response,
                            expected_keys=("metrics", "items"),
                            allow_list=True,
                            api_name="get_query_data_multiple",
                        )
                    except Exception as exc:
                        self._record_error(
                            stage="response",
                            api="get_query_data_multiple",
                            product_key=(
                                str(chunk[0].get("prodKey"))
                                if (
                                    chunk
                                    and chunk[0].get("prodKey") is not None
                                )
                                else None
                            ),
                            stat_name=stat_name,
                            exc=exc,
                        )
                        continue

                    self.normalizer.merge_metric_response(
                        raw_metrics=raw_metrics,
                        response=response,
                        stat_name=stat_name,
                    )

        return raw_metrics

    def _get_filesystem_mount_candidates(
        self,
        prod_key: str,
        instance_no: Optional[str] = None,
    ) -> Set[str]:
        normalized_instance_no = self._normalize_id(instance_no)

        if (
            normalized_instance_no
            and normalized_instance_no
            in self._filesystem_mount_candidates_by_instance
        ):
            return self._filesystem_mount_candidates_by_instance[
                normalized_instance_no
            ]

        if (
            not normalized_instance_no
            and self._filesystem_mount_candidates is not None
        ):
            return self._filesystem_mount_candidates

        insight_api = self.api_factory.get("cloud_insight")

        response = None

        if normalized_instance_no and self._supports_mount_dimension_filter is not False:
            try:
                response = self._search_metric_list(
                    insight_api=insight_api,
                    prod_key=prod_key,
                    instance_no=normalized_instance_no,
                )
                self._supports_mount_dimension_filter = True
            except TypeError:
                # 오래된 래퍼나 테스트 대역이 dimension 필터를 받지 않는
                # 경우에는 기존 전역 조회 계약으로 안전하게 되돌아간다.
                self._supports_mount_dimension_filter = False

        if response is None:
            if self._filesystem_mount_candidates is not None:
                return self._filesystem_mount_candidates

            response = self._search_metric_list(
                insight_api=insight_api,
                prod_key=prod_key,
                instance_no=None,
            )

        metric_items = self._extract_metric_items(response)
        mount_points = self._extract_mount_points(
            metric_items=metric_items,
            instance_no=(
                normalized_instance_no
                if self._supports_mount_dimension_filter
                else None
            ),
        )

        if normalized_instance_no and self._supports_mount_dimension_filter:
            self._filesystem_mount_candidates_by_instance[
                normalized_instance_no
            ] = mount_points
        else:
            self._filesystem_mount_candidates = mount_points

        logger.info(
            "filesystem mnt_nm 후보 %s개를 캐싱했습니다"
            " (instanceNo=%s): %s",
            len(mount_points),
            normalized_instance_no or "all",
            sorted(mount_points),
        )

        return mount_points

    def _extract_mount_points(
        self,
        metric_items: List[Dict[str, Any]],
        instance_no: Optional[str],
    ) -> Set[str]:
        mount_points: Set[str] = set()

        for item in metric_items:
            metric_name = (
                item.get("metric")
                or item.get("metricName")
                or item.get("name")
            )

            if metric_name != self.FILESYSTEM_METRIC["metric"]:
                continue

            dimensions = item.get("dimensions") or []

            if isinstance(dimensions, dict):
                dimensions = [
                    {"dim": name, "val": value}
                    for name, value in dimensions.items()
                ]

            item_instance_ids = set()
            item_mount_points = set()

            for dimension in dimensions:
                if not isinstance(dimension, dict):
                    continue

                dim_name = (
                    dimension.get("dim")
                    or dimension.get("name")
                    or dimension.get("dimension")
                )

                dim_value = dimension.get("val")

                if dim_value is None:
                    dim_value = dimension.get("value")

                if dim_value is None:
                    dim_value = dimension.get("dimensionValue")

                if dim_name == "mnt_nm" and dim_value:
                    item_mount_points.add(str(dim_value))

                if dim_name in {"instanceNo", "serverInstanceNo"}:
                    normalized_value = self._normalize_id(dim_value)

                    if normalized_value:
                        item_instance_ids.add(normalized_value)

            if (
                instance_no
                and item_instance_ids
                and instance_no not in item_instance_ids
            ):
                continue

            mount_points.update(item_mount_points)

        return mount_points

    def _search_metric_list(
        self,
        insight_api: Any,
        prod_key: str,
        instance_no: Optional[str] = None,
    ) -> Any:
        kwargs: Dict[str, Any] = {"prod_key": prod_key}

        if instance_no:
            kwargs["dimensions_selected_list"] = [
                {
                    "name": "instanceNo",
                    "values": [instance_no],
                }
            ]

        if hasattr(insight_api, "get_search_metric_list"):
            return insight_api.get_search_metric_list(**kwargs)

        if hasattr(insight_api, "search_metric_list"):
            return insight_api.search_metric_list(**kwargs)

        raise AttributeError(
            "CloudInsightAPI에 get_search_metric_list(prod_key) 메서드가 필요합니다."
        )

    def _extract_metric_items(
        self,
        response: Any,
    ) -> List[Dict[str, Any]]:
        validate_collection_response(
            response,
            expected_keys=("metrics", "metricList", "items"),
            allow_list=True,
            api_name="get_search_metric_list",
        )
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
        validate_collection_response(
            response,
            expected_keys=(
                "items",
                "schemaList",
                "systemSchemaList",
            ),
            allow_list=True,
            api_name="get_system_schema_key_list",
        )

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

        if isinstance(schema_items, dict):
            schema_items = (
                schema_items.get("items")
                or schema_items.get("schemaList")
                or schema_items.get("systemSchemaList")
                or []
            )

        if not isinstance(schema_items, list):
            schema_items = []

        self._cw_key_map = {}

        for item in schema_items:
            if not isinstance(item, dict):
                continue

            prod_name = item.get("prodName") or item.get("productName")
            cw_key = (
                item.get("cw_key")
                or item.get("cwKey")
                or item.get("prodKey")
            )

            if prod_name and cw_key:
                self._cw_key_map[str(prod_name)] = str(cw_key)

        logger.info(
            "Cloud Insight cw_key %s개를 캐싱했습니다.",
            len(self._cw_key_map),
        )

        return self._cw_key_map

    def _filter_servers_for_period(
        self,
        servers: List[Dict[str, Any]],
        start_time: int,
        end_time: int,
    ) -> List[Dict[str, Any]]:
        if not isinstance(servers, list):
            self._record_error(
                stage="period_filter",
                api="local",
                message="서버 목록이 list 형식이 아닙니다.",
            )
            return []

        result = []

        for index, server in enumerate(servers):
            if not isinstance(server, dict):
                self._record_error(
                    stage="period_filter",
                    api="local",
                    message=f"서버 항목 {index}가 object 형식이 아닙니다.",
                )
                continue

            create_value = server.get("create_date")

            if create_value is None:
                raw_server = server.get("raw_server")

                if isinstance(raw_server, dict):
                    create_value = raw_server.get("createDate")

            create_time = self._to_timestamp_ms(create_value)

            if create_value is not None and create_time is None:
                self._record_error(
                    stage="period_filter",
                    api="local",
                    target_id=self._normalize_id(server.get("server_id")),
                    message=(
                        "서버 생성일을 해석하지 못해 기간 필터 없이 "
                        f"포함했습니다: {create_value}"
                    ),
                    severity="warning",
                )

            if create_time is not None and create_time > end_time:
                self._record_error(
                    stage="period_filter",
                    api="local",
                    target_id=self._normalize_id(server.get("server_id")),
                    message=(
                        "조회 종료일 이후 생성된 현재 서버를 "
                        "과거 메트릭 조회에서 제외했습니다."
                    ),
                    severity="warning",
                )
                continue

            if create_time is not None and create_time > start_time:
                self._record_error(
                    stage="period_filter",
                    api="local",
                    target_id=self._normalize_id(server.get("server_id")),
                    message=(
                        "서버가 조회 시작일 이후 생성되어 해당 서버의 "
                        "메트릭은 생성 시점 이후의 부분 기간만 포함합니다."
                    ),
                    severity="warning",
                )

            result.append(server)

        return result

    def _to_timestamp_ms(self, value: Any) -> Optional[int]:
        if value is None:
            return None

        if isinstance(value, (int, float)):
            numeric = float(value)
            return int(numeric if abs(numeric) >= 10**11 else numeric * 1000)

        parsed: Optional[datetime] = None

        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            normalized = value.strip()

            if not normalized:
                return None

            try:
                numeric = float(normalized)
                return int(
                    numeric if abs(numeric) >= 10**11 else numeric * 1000
                )
            except ValueError:
                pass

            try:
                parsed = datetime.fromisoformat(
                    normalized.replace("Z", "+00:00")
                )
            except ValueError:
                for date_format in (
                    "%b %d, %Y, %I:%M:%S %p",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y/%m/%d %H:%M:%S",
                ):
                    try:
                        parsed = datetime.strptime(normalized, date_format)
                        break
                    except ValueError:
                        continue

        if parsed is None:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=self.KST)

        return int(parsed.timestamp() * 1000)

    def _normalize_id(self, value: Any) -> Optional[str]:
        if value is None:
            return None

        normalized = str(value).strip()
        return normalized or None

    def _record_error(
        self,
        stage: str,
        api: str,
        exc: Optional[Exception] = None,
        target_id: Optional[str] = None,
        product_key: Optional[str] = None,
        metric: Optional[str] = None,
        stat_name: Optional[str] = None,
        message: Optional[str] = None,
        severity: str = "error",
    ) -> None:
        error: Dict[str, Any] = {
            "collector": self.__class__.__name__,
            "stage": stage,
            "target_type": "server",
            "api": api,
            "severity": severity,
            "message": (
                message
                or (
                    safe_exception_message(exc)
                    if exc
                    else "알 수 없는 오류"
                )
            ),
        }

        if target_id:
            error["target_id"] = target_id

        if product_key:
            error["product_key"] = product_key

        if metric:
            error["metric"] = metric

        if stat_name:
            error["stat_name"] = stat_name

        if exc is not None:
            error["exception_type"] = type(exc).__name__

        self.last_errors.append(error)

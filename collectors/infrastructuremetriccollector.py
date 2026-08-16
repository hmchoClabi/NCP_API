import logging
import math
import re
from collections import defaultdict
from datetime import datetime
from itertools import batched
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests
from dateutil.relativedelta import relativedelta

from . import _infrastructure_metric_catalog as metric_catalog
from ._collection_support import query_time_windows
from utils.common_rest import safe_exception_message
from utils.response_validation import validate_collection_response


logger = logging.getLogger(__name__)


class InfrastructureMetricCollector:
    """대표 인프라의 Cloud Insight 시계열을 안전하게 수집한다.

    Cloud Insight의 상품 키, metric, dimension 및 지원 집계 방식은 계정과
    상품 세대에 따라 달라질 수 있다. 따라서 고정 dimension을 조합하지 않고
    System Schema와 SearchMetricList가 반환한 실제 조합만 조회한다.
    """

    MAX_QUERY_SIZE = metric_catalog.MAX_QUERY_SIZE
    MAX_SERIES = metric_catalog.MAX_SERIES
    MAX_DISCOVERY_TARGETS = metric_catalog.MAX_DISCOVERY_TARGETS
    KST = metric_catalog.KST
    MONITORED_CATEGORIES = metric_catalog.MONITORED_CATEGORIES
    OUTPUT_CATEGORIES = metric_catalog.OUTPUT_CATEGORIES
    CATEGORY_ALIASES = metric_catalog.CATEGORY_ALIASES
    INTERVAL_MINUTES = metric_catalog.INTERVAL_MINUTES
    AGGREGATION_ORDER = metric_catalog.AGGREGATION_ORDER
    LB_METRICS = metric_catalog.LB_METRICS
    TARGET_GROUP_METRICS = metric_catalog.TARGET_GROUP_METRICS
    CDB_CATALOG = metric_catalog.CDB_CATALOG
    CDB_LABELS = metric_catalog.CDB_LABELS
    NKS_METRICS = metric_catalog.NKS_METRICS
    RESOURCE_METRICS = metric_catalog.RESOURCE_METRICS
    PRIMARY_ID_DIMENSIONS = metric_catalog.PRIMARY_ID_DIMENSIONS
    CATEGORY_ID_DIMENSIONS = metric_catalog.CATEGORY_ID_DIMENSIONS
    CATEGORY_DETAIL_ID_FIELDS = metric_catalog.CATEGORY_DETAIL_ID_FIELDS
    ID_DIMENSION_HINTS = metric_catalog.ID_DIMENSION_HINTS
    NAME_DIMENSION_HINTS = metric_catalog.NAME_DIMENSION_HINTS

    def __init__(self, api_factory: Any):
        self.api_factory = api_factory
        self.last_errors: List[Dict[str, Any]] = []
        self.last_warnings: List[Dict[str, Any]] = []
        self._issue_keys: set[Tuple[Any, ...]] = set()

    def collect(
        self,
        infrastructure: List[Dict[str, Any]],
        start_time: int,
        end_time: int,
        selected_categories: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        self.last_errors = []
        self.last_warnings = []
        self._issue_keys = set()

        resources = self._monitoring_resources(
            infrastructure,
            selected_categories=selected_categories,
        )
        if not any(resources.values()):
            # 일반 인프라만 있거나 인프라가 없는 계정은 정상적인 빈 결과다.
            return []

        if not self._valid_time_range(start_time, end_time):
            self._record_issue(
                severity="error",
                stage="validation",
                api="local",
                message="모니터링 조회 기간이 올바르지 않습니다.",
            )
            return []

        try:
            insight_api = self.api_factory.get("cloud_insight")
        except Exception as exc:
            self._record_issue(
                severity="error",
                stage="client",
                api="cloud_insight",
                exc=exc,
            )
            return []

        schemas = self._load_system_schemas(insight_api)
        if schemas is None:
            return []

        preferred_interval = self._select_metric_interval(
            start_time=start_time,
            end_time=end_time,
        )
        records: List[Dict[str, Any]] = []
        matched_categories = set()
        mapped_categories = set()
        mapping_attempted_products: Dict[str, List[str]] = defaultdict(list)

        for schema in schemas:
            product_name = schema["product_name"]
            category = self._product_category(product_name)
            if category not in resources or not resources[category]:
                continue

            product_resources = self._resources_for_product(
                category=category,
                product_name=product_name,
                resources=resources[category],
            )
            if not product_resources:
                continue

            matched_categories.add(category)
            metric_items = self._search_metrics(
                insight_api=insight_api,
                product_name=product_name,
                product_key=schema["product_key"],
                category=category,
                resources=product_resources,
            )
            if metric_items is None:
                continue

            mapping_attempted_products[category].append(product_name)
            product_records = self._build_product_records(
                category=category,
                product_name=product_name,
                product_key=schema["product_key"],
                metric_items=metric_items,
                resources=product_resources,
                preferred_interval=preferred_interval,
            )
            if product_records:
                mapped_categories.add(category)
            records.extend(product_records)

        for category in self.MONITORED_CATEGORIES:
            if not resources[category]:
                continue
            if category not in matched_categories:
                self._record_issue(
                    severity="warning",
                    stage="schema_lookup",
                    api="get_system_schema_key_list",
                    category=category,
                    message=(
                        "해당 인프라의 Cloud Insight 시스템 상품을 "
                        "찾지 못했습니다."
                    ),
                )
            elif (
                category not in mapped_categories
                and mapping_attempted_products[category]
            ):
                # 한 서비스에 현행/레거시 System Schema가 함께 반환될 수 있다.
                # 동일 카테고리의 다른 상품에서 정상 매핑된 경우 개별 0건
                # 상품은 장애가 아니므로 경고하지 않는다.
                attempted_products = list(
                    dict.fromkeys(mapping_attempted_products[category])
                )
                self._record_issue(
                    severity="warning",
                    stage="metric_mapping",
                    api="get_search_metric_list",
                    category=self.OUTPUT_CATEGORIES[category],
                    message=(
                        "지원 지표 또는 인벤토리와 일치하는 Cloud Insight "
                        "dimension을 찾지 못했습니다. 서비스 View 권한, "
                        "직접 API 인벤토리 및 모니터링 dimension을 "
                        "확인하십시오."
                    ),
                    extra={"attempted_products": attempted_products[:10]},
                )

        records = self._deduplicate_records(records)
        records.sort(key=self._record_sort_key)

        if len(records) > self.MAX_SERIES:
            omitted_count = len(records) - self.MAX_SERIES
            records = self._fair_series_limit(
                records,
                limit=self.MAX_SERIES,
            )
            self._record_issue(
                severity="warning",
                stage="series_limit",
                api="local",
                message=(
                    f"모니터링 시계열이 제한({self.MAX_SERIES}개)을 초과해 "
                    f"{omitted_count}개를 제외했습니다."
                ),
                extra={
                    "limit": self.MAX_SERIES,
                    "omitted_count": omitted_count,
                },
            )

        if not records:
            return []

        self._execute_queries(
            insight_api=insight_api,
            records=records,
            start_time=start_time,
            end_time=end_time,
        )
        self._warn_empty_products(records)
        return self._group_records(records)

    def _monitoring_resources(
        self,
        infrastructure: Any,
        selected_categories: Optional[Sequence[str]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        result = {
            category: []
            for category in self.MONITORED_CATEGORIES
        }
        if not isinstance(infrastructure, list):
            return result

        selected = self._selected_monitoring_categories(selected_categories)

        for item in infrastructure:
            if not isinstance(item, dict):
                continue
            category = self._normalize_category(item.get("category"))
            if category in result and category in selected:
                result[category].append(item)
        return result

    def _selected_monitoring_categories(
        self,
        selected_categories: Optional[Sequence[str]],
    ) -> set[str]:
        if selected_categories is None:
            return set(self.MONITORED_CATEGORIES)
        if isinstance(selected_categories, str):
            candidates: Iterable[Any] = (selected_categories,)
        else:
            candidates = selected_categories
        selected = {
            category
            for value in candidates
            if (category := self._normalize_category(value)) is not None
        }
        if "LOAD_BALANCER" in selected:
            selected.add("TARGET_GROUP")
        return selected

    def _normalize_category(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        normalized = re.sub(r"[^A-Z0-9]+", "_", str(value).upper()).strip("_")
        return self.CATEGORY_ALIASES.get(normalized)

    def _valid_time_range(self, start_time: Any, end_time: Any) -> bool:
        return (
            isinstance(start_time, int)
            and not isinstance(start_time, bool)
            and isinstance(end_time, int)
            and not isinstance(end_time, bool)
            and start_time >= 0
            and end_time >= start_time
        )

    def _load_system_schemas(
        self,
        insight_api: Any,
    ) -> Optional[List[Dict[str, str]]]:
        try:
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
            items = self._extract_collection(
                response,
                keys=("items", "schemaList", "systemSchemaList"),
            )
        except Exception as exc:
            severity, metadata = self._classify_exception(exc)
            self._record_issue(
                severity=severity,
                stage="schema_lookup",
                api="get_system_schema_key_list",
                exc=exc,
                extra=metadata,
            )
            return None

        result = []
        seen = set()
        for item in items:
            product_name = item.get("prodName") or item.get("productName")
            product_key = (
                item.get("cw_key")
                or item.get("cwKey")
                or item.get("prodKey")
            )
            if not product_name or not product_key:
                continue
            pair = (str(product_name), str(product_key))
            if pair in seen:
                continue
            seen.add(pair)
            result.append(
                {
                    "product_name": pair[0],
                    "product_key": pair[1],
                }
            )
        return result

    def _product_category(self, product_name: str) -> Optional[str]:
        normalized = self._normalize_product_name(product_name)
        if "targetgroup" in normalized:
            return "TARGET_GROUP"
        if "loadbalancer" in normalized:
            return "LOAD_BALANCER"
        if "clouddb" in normalized or normalized.startswith("cdb"):
            return "CDB"
        if "kubernetes" in normalized or normalized.startswith("nks"):
            return "NKS"
        if normalized in {"nas", "nasvpc"}:
            return "NAS"
        if "objectstorage" in normalized:
            return "OBJECT_STORAGE"
        if "autoscaling" in normalized:
            return "AUTO_SCALING"
        if "searchengineservice" in normalized or normalized.startswith(
            "searchengine"
        ):
            return "SEARCH_ENGINE"
        if "clouddatastreamingservice" in normalized:
            return "DATA_STREAMING"
        if "cloudhadoop" in normalized:
            return "CLOUD_HADOOP"
        if normalized.startswith("datastream"):
            return "DATA_STREAM"
        return None

    def _normalize_product_name(self, value: Any) -> str:
        normalized = str(value or "").strip().casefold()
        if normalized.startswith("system/"):
            normalized = normalized[len("system/"):]
        normalized = normalized.replace(" monitor", "")
        return re.sub(r"[^a-z0-9]+", "", normalized)

    def _search_metrics(
        self,
        insight_api: Any,
        product_name: str,
        product_key: str,
        category: str,
        resources: List[Dict[str, Any]],
    ) -> Optional[List[Dict[str, Any]]]:
        search_targets = self._metric_search_targets(
            category=category,
            resources=resources,
        )
        if len(search_targets) > self.MAX_DISCOVERY_TARGETS:
            omitted_count = len(search_targets) - self.MAX_DISCOVERY_TARGETS
            search_targets = search_targets[:self.MAX_DISCOVERY_TARGETS]
            self._record_issue(
                severity="warning",
                stage="discovery_target_limit",
                api="get_search_metric_list",
                category=self.OUTPUT_CATEGORIES[category],
                product_name=product_name,
                message=(
                    "모니터링 발견 대상이 제한을 초과해 "
                    f"{omitted_count}개 대상을 제외했습니다."
                ),
                extra={
                    "limit": self.MAX_DISCOVERY_TARGETS,
                    "omitted_count": omitted_count,
                },
            )

        try:
            if hasattr(insight_api, "get_search_metric_list"):
                search_method = insight_api.get_search_metric_list
            elif hasattr(insight_api, "search_metric_list"):
                search_method = insight_api.search_metric_list
            else:
                raise AttributeError(
                    "CloudInsightAPI에 metric 검색 메서드가 없습니다."
                )
        except Exception as exc:
            severity, metadata = self._classify_exception(exc)
            self._record_issue(
                severity=severity,
                stage="metric_discovery",
                api="get_search_metric_list",
                product_name=product_name,
                exc=exc,
                extra=metadata,
            )
            return None

        metric_items: List[Dict[str, Any]] = []
        successful_targets = 0
        for id_dimension, target_id in search_targets:
            try:
                search_filter: Dict[str, Any] = {
                    "dimensions_selected_list": [
                        {"name": id_dimension, "values": [target_id]}
                    ]
                }
                if category == "NKS":
                    search_filter["dim_values"] = [
                        {"name": "type", "value": "NodeAvailability"}
                    ]
                response = search_method(
                    prod_key=product_key,
                    **search_filter,
                )
                validate_collection_response(
                    response,
                    expected_keys=("metrics", "metricList", "items"),
                    allow_list=True,
                    api_name="get_search_metric_list",
                )
                metric_items.extend(
                    self._attach_search_target(
                        items=self._extract_collection(
                            response,
                            keys=("metrics", "metricList", "items"),
                        ),
                        fallback_id_dimension=id_dimension,
                        target_id=target_id,
                    )
                )
                successful_targets += 1
            except Exception as exc:
                severity, metadata = self._classify_exception(exc)
                self._record_issue(
                    severity=severity,
                    stage="metric_discovery",
                    api="get_search_metric_list",
                    category=self.OUTPUT_CATEGORIES[category],
                    product_name=product_name,
                    exc=exc,
                    extra={**metadata, "target_id": target_id[:128]},
                )

        if search_targets and not successful_targets:
            return None
        return self._deduplicate_metric_items(metric_items)

    def _resources_for_product(
        self,
        category: str,
        product_name: str,
        resources: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if category == "NAS":
            normalized_product = self._normalize_product_name(product_name)
            if normalized_product == "nasvpc":
                required_platform = "VPC"
            elif normalized_product == "nas":
                required_platform = "CLASSIC"
            else:
                return []
            return [
                resource
                for resource in resources
                if re.sub(
                    r"[^A-Z0-9]+",
                    "",
                    str(resource.get("platform") or "").upper(),
                )
                == required_platform
            ]

        if category != "CDB":
            return resources

        variant = self._cdb_variant(product_name)
        aliases = {
            "mysql": {"MYSQL"},
            "postgresql": {"POSTGRESQL", "POSTGRES"},
            "mssql": {"MSSQL", "SQLSERVER"},
            "mongodb": {"MONGODB", "MONGO"},
            "cache": {"CACHE", "REDIS"},
            "serverless": {"SERVERLESS"},
        }.get(variant, set())
        matched = []
        unknown = []
        for resource in resources:
            platform = re.sub(
                r"[^A-Z0-9]+",
                "",
                str(resource.get("platform") or "").upper(),
            )
            if not platform:
                unknown.append(resource)
            elif platform in aliases:
                matched.append(resource)
        return matched or unknown

    def _metric_search_targets(
        self,
        category: str,
        resources: List[Dict[str, Any]],
    ) -> List[Tuple[str, str]]:
        dimension_name = self.PRIMARY_ID_DIMENSIONS[category]
        identifiers = set()
        for resource in resources:
            identifiers.update(
                self._resource_identifiers(
                    resource,
                    category=category,
                )
            )
        return [
            (dimension_name, identifier)
            for identifier in sorted(identifiers)
        ]

    def _attach_search_target(
        self,
        items: List[Dict[str, Any]],
        fallback_id_dimension: str,
        target_id: str,
    ) -> List[Dict[str, Any]]:
        result = []
        for item in items:
            declared_id_dimension = str(
                item.get("idDimension")
                or item.get("id_dimension")
                or ""
            ).strip()
            if declared_id_dimension and (
                self._normalize_dimension_name(declared_id_dimension)
                != self._normalize_dimension_name(fallback_id_dimension)
            ):
                continue
            id_dimension = fallback_id_dimension
            dimensions = self._normalize_dimensions(item.get("dimensions"))
            existing_id = next(
                (
                    value
                    for name, value in dimensions.items()
                    if self._normalize_dimension_name(name)
                    == self._normalize_dimension_name(id_dimension)
                ),
                None,
            )
            if existing_id is not None and str(existing_id) != target_id:
                continue
            dimensions[id_dimension] = target_id
            annotated = dict(item)
            annotated["dimensions"] = dimensions
            annotated["_selected_id"] = target_id
            annotated["_id_dimension"] = id_dimension
            result.append(annotated)
        return result

    def _deduplicate_metric_items(
        self,
        items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = []
        seen = set()
        for item in items:
            metric_name = self._metric_name(item)
            dimensions = self._normalize_dimensions(item.get("dimensions"))
            key = (
                metric_name,
                self._dimension_tuple(dimensions),
                item.get("_selected_id"),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    def _extract_collection(
        self,
        response: Any,
        keys: Sequence[str],
    ) -> List[Dict[str, Any]]:
        if isinstance(response, list):
            return [item for item in response if isinstance(item, dict)]
        if not isinstance(response, dict):
            return []

        for key in keys:
            candidate = response.get(key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]

        for wrapper_key in ("data", "result", "response"):
            candidate = response.get(wrapper_key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
            if isinstance(candidate, dict):
                nested = self._extract_collection(candidate, keys)
                if nested:
                    return nested
        return []

    def _build_product_records(
        self,
        category: str,
        product_name: str,
        product_key: str,
        metric_items: List[Dict[str, Any]],
        resources: List[Dict[str, Any]],
        preferred_interval: str,
    ) -> List[Dict[str, Any]]:
        selected_names = self._select_metric_names(
            category=category,
            product_name=product_name,
            metric_items=metric_items,
        )
        result = []

        for item in metric_items:
            metric_name = self._metric_name(item)
            if not metric_name or metric_name not in selected_names:
                continue

            dimensions = self._normalize_dimensions(item.get("dimensions"))
            descriptor = self._metric_descriptor(
                category=category,
                product_name=product_name,
                metric_name=metric_name,
                dimensions=dimensions,
            )
            if descriptor is None:
                continue

            resource = self._match_resource(
                category=category,
                resources=resources,
                dimensions=dimensions,
                metric_item=item,
            )
            if resource is None and self._resources_have_identifiers(
                resources,
                category=category,
            ):
                continue

            option = self._select_supported_option(
                options=item.get("options"),
                preferred_interval=preferred_interval,
                aggregation_order=descriptor["aggregations"],
            )
            if option is None:
                continue
            interval, aggregation = option

            runtime_unit = item.get("unit")
            force_unit = bool(descriptor.get("force_unit"))
            unit = (
                descriptor.get("unit")
                if force_unit
                else runtime_unit or descriptor.get("unit")
            )
            value_scale = float(descriptor.get("value_scale") or 1.0)
            if self._is_percent_unit(runtime_unit):
                value_scale = 1.0

            resource_id, resource_name = self._series_identity(
                resource=resource,
                dimensions=dimensions,
                metric_item=item,
            )
            if category == "CDB":
                resource_name = self._cdb_series_name(
                    resource=resource,
                    dimensions=dimensions,
                    service_name=resource_name,
                )
            result.append(
                {
                    "category": category,
                    "product_name": product_name,
                    "product_key": product_key,
                    "metric": metric_name,
                    "metric_label": descriptor["label"],
                    "unit": unit,
                    "value_scale": value_scale,
                    "interval": interval,
                    "aggregation": aggregation,
                    "resource_id": resource_id,
                    "resource_name": resource_name,
                    "dimensions": dimensions,
                    "points": {},
                }
            )
        return result

    def _select_metric_names(
        self,
        category: str,
        product_name: str,
        metric_items: List[Dict[str, Any]],
    ) -> set[str]:
        names = {
            name
            for item in metric_items
            if (name := self._metric_name(item))
        }
        if category == "LOAD_BALANCER":
            selected = set()
            normalized_names = defaultdict(list)
            for name in names:
                normalized_names[self._normalize_metric_name(name)].append(name)
            for config in self.LB_METRICS.values():
                for alias in config["aliases"]:
                    matches = normalized_names.get(alias, [])
                    if matches:
                        selected.add(sorted(matches)[0])
                        break
            return selected

        if category == "TARGET_GROUP":
            return {
                name
                for name in names
                if self._normalize_metric_name(name)
                in self.TARGET_GROUP_METRICS
            }

        if category == "CDB":
            variant = self._cdb_variant(product_name)
            catalog = self.CDB_CATALOG.get(variant, ())
            selected = set()
            for metric_config in catalog:
                chosen = self._first_matching_metric(
                    names,
                    metric_config["aliases"],
                )
                if chosen is not None:
                    selected.add(chosen)
            if variant != "unknown":
                return selected

            # 아직 카탈로그에 등록되지 않은 Cloud DB 상품만 제한된 의미
            # 규칙으로 대체한다. 알려진 상품에서는 임의 이름을 선택하지 않는다.
            for semantic in ("cpu", "memory", "storage", "connection"):
                chosen = self._generic_cdb_metric(names, semantic)
                if chosen is not None:
                    selected.add(chosen)
            return selected

        if category == "NKS":
            return {
                name
                for name in names
                if self._normalize_metric_name(name) in self.NKS_METRICS
            }
        metric_catalog = self.RESOURCE_METRICS.get(category)
        if metric_catalog is not None:
            return {
                name
                for name in names
                if self._normalize_metric_name(name) in metric_catalog
            }
        return set()

    def _first_matching_metric(
        self,
        names: set[str],
        aliases: Sequence[str],
    ) -> Optional[str]:
        by_normalized = defaultdict(list)
        for name in names:
            by_normalized[self._normalize_metric_name(name)].append(name)
        for alias in aliases:
            matches = by_normalized.get(alias, [])
            if matches:
                return sorted(matches)[0]
        return None

    def _generic_cdb_metric(
        self,
        names: set[str],
        semantic: str,
    ) -> Optional[str]:
        scored = []
        for name in names:
            token = self._normalize_metric_name(name)
            score: Optional[int] = None
            if semantic == "cpu" and (
                token == "cpu" or token.startswith("cpu_")
            ):
                score = 10 if "total" in token else 20
            elif semantic == "memory" and (
                token.startswith("mem_")
                or token.startswith("memory_")
            ) and any(
                word in token
                for word in ("used", "usage", "pct", "percent", "available")
            ):
                score = 10
            elif semantic == "storage" and (
                token.startswith("disk_")
                or token.startswith("storage_")
            ) and any(
                word in token
                for word in ("used", "usage", "pct", "percent", "free")
            ):
                score = 10
            elif semantic == "connection" and any(
                word in token for word in ("connection", "session", "conn")
            ) and any(
                word in token
                for word in ("count", "current", "total", "active", "client")
            ):
                score = 10
            if score is not None:
                scored.append((score, token, name))
        return min(scored)[2] if scored else None

    def _metric_descriptor(
        self,
        category: str,
        product_name: str,
        metric_name: str,
        dimensions: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        token = self._normalize_metric_name(metric_name)

        if category == "LOAD_BALANCER":
            for config in self.LB_METRICS.values():
                if token in config["aliases"]:
                    return dict(config)
            return None

        if category == "TARGET_GROUP":
            metric_config = self.TARGET_GROUP_METRICS.get(token)
            return dict(metric_config) if metric_config is not None else None

        if category == "CDB":
            metric_config = self._cdb_metric_config(product_name, token)
            if metric_config is not None:
                return {
                    "label": metric_config["label"],
                    "unit": metric_config.get("unit"),
                    "force_unit": bool(metric_config.get("force_unit")),
                    "aggregations": metric_config.get(
                        "aggregations",
                        ("AVG", "MAX", "MIN"),
                    ),
                }

            semantic = self._cdb_semantic(product_name, token)
            if semantic is None:
                return None
            label = self.CDB_LABELS[semantic]
            if token == "memory_available":
                label = "가용 메모리"
            elif semantic == "storage" and "free" in token:
                label = "스토리지 여유 공간"
            elif semantic == "cpu" and any(
                word in token for word in ("pct", "ratio", "percent")
            ):
                label = "CPU 사용률"
            elif semantic == "memory" and any(
                word in token for word in ("pct", "ratio", "percent")
            ):
                label = "메모리 사용률"
            elif semantic == "storage" and any(
                word in token for word in ("pct", "ratio", "percent")
            ):
                label = "스토리지 사용률"
            return {
                "label": label,
                "unit": "count" if semantic == "connection" else None,
                "force_unit": semantic == "connection",
                "aggregations": ("AVG", "MAX", "MIN"),
            }

        if category == "NKS":
            metric_config = self.NKS_METRICS.get(token)
            if metric_config is None:
                return None
            normalized_dimensions = {
                self._normalize_dimension_name(name): str(value).casefold()
                for name, value in dimensions.items()
            }
            if normalized_dimensions.get("type") != "nodeavailability":
                return None
            if not any(
                key in normalized_dimensions
                for key in ("clusteruuid", "clusterid")
            ):
                return None
            return {
                "label": metric_config[0],
                "unit": metric_config[1],
                "force_unit": True,
                "value_scale": (
                    100.0 if token == "node_available_ratio" else 1.0
                ),
                "aggregations": ("AVG", "MAX", "SUM", "MIN"),
            }
        metric_catalog = self.RESOURCE_METRICS.get(category)
        if metric_catalog is not None:
            metric_config = metric_catalog.get(token)
            if metric_config is None:
                return None
            return dict(metric_config)
        return None

    def _cdb_variant(self, product_name: str) -> str:
        normalized = self._normalize_product_name(product_name)
        if "serverless" in normalized:
            return "serverless"
        if "postgresql" in normalized or "postgres" in normalized:
            return "postgresql"
        if "mongodb" in normalized or "mongo" in normalized:
            return "mongodb"
        if "mssql" in normalized or "sqlserver" in normalized:
            return "mssql"
        if any(
            product in normalized
            for product in ("cache", "redis", "valkey")
        ):
            return "cache"
        if "mysql" in normalized or "mariadb" in normalized:
            return "mysql"
        return "unknown"

    def _cdb_semantic(
        self,
        product_name: str,
        metric_token: str,
    ) -> Optional[str]:
        if self._cdb_variant(product_name) != "unknown":
            return None

        for semantic in ("cpu", "memory", "storage", "connection"):
            if self._generic_cdb_metric({metric_token}, semantic):
                return semantic
        return None

    def _cdb_metric_config(
        self,
        product_name: str,
        metric_token: str,
    ) -> Optional[Dict[str, Any]]:
        catalog = self.CDB_CATALOG.get(self._cdb_variant(product_name), ())
        for metric_config in catalog:
            if metric_token in metric_config["aliases"]:
                return metric_config
        return None

    def _metric_name(self, item: Dict[str, Any]) -> Optional[str]:
        value = item.get("metric") or item.get("metricName") or item.get("name")
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    def _normalize_metric_name(self, value: Any) -> str:
        text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(value or ""))
        return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")

    def _normalize_dimensions(self, dimensions: Any) -> Dict[str, str]:
        result: Dict[str, str] = {}
        if isinstance(dimensions, dict):
            values = dimensions.items()
        elif isinstance(dimensions, list):
            normalized_values = []
            for dimension in dimensions:
                if not isinstance(dimension, dict):
                    continue
                name = (
                    dimension.get("dim")
                    or dimension.get("name")
                    or dimension.get("dimension")
                )
                value = dimension.get("val")
                if value is None:
                    value = dimension.get("value")
                if value is None:
                    value = dimension.get("dimensionValue")
                normalized_values.append((name, value))
            values = normalized_values
        else:
            return result

        for name, value in values:
            if name is None or value is None:
                continue
            normalized_name = str(name).strip()
            normalized_value = str(value).strip()
            if normalized_name and normalized_value:
                result[normalized_name] = normalized_value
        return dict(sorted(result.items(), key=lambda pair: pair[0].casefold()))

    def _normalize_dimension_name(self, value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())

    def _resources_have_identifiers(
        self,
        resources: List[Dict[str, Any]],
        category: str,
    ) -> bool:
        return any(
            self._resource_identifiers(resource, category=category)
            for resource in resources
        )

    def _match_resource(
        self,
        category: str,
        resources: List[Dict[str, Any]],
        dimensions: Dict[str, str],
        metric_item: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        allowed_dimensions = self.CATEGORY_ID_DIMENSIONS[category]
        identifier_values = {
            str(value).strip().casefold()
            for name, value in dimensions.items()
            if self._normalize_dimension_name(name) in allowed_dimensions
            and str(value).strip()
        }
        selected_id = metric_item.get("_selected_id")
        if selected_id is not None and str(selected_id).strip():
            identifier_values.add(str(selected_id).strip().casefold())

        for key in ("resourceId", "instanceId", "instanceNo"):
            if self._normalize_dimension_name(key) not in allowed_dimensions:
                continue
            value = metric_item.get(key)
            if value is not None and str(value).strip():
                identifier_values.add(str(value).strip().casefold())

        if not identifier_values:
            return None

        for resource in resources:
            identifiers = {
                value.casefold()
                for value in self._resource_identifiers(
                    resource,
                    category=category,
                )
            }
            if identifiers & identifier_values:
                return resource
        return None

    def _resource_identifiers(
        self,
        resource: Dict[str, Any],
        category: str,
    ) -> set[str]:
        result = set()
        # Cloud DB metrics are keyed by the DB node instance numbers rather
        # than the service-level resource ID. Other monitored products use
        # their primary inventory resource ID unless an explicit equivalent
        # provider field is present.
        if category != "CDB":
            resource_id = resource.get("resource_id")
            if resource_id is not None and str(resource_id).strip():
                result.add(str(resource_id).strip())

        details = resource.get("details")
        if isinstance(details, dict):
            allowed_fields = self.CATEGORY_DETAIL_ID_FIELDS[category]
            for name, value in details.items():
                normalized_name = self._normalize_dimension_name(name)
                if normalized_name not in allowed_fields:
                    continue
                if isinstance(value, (str, int)) and str(value).strip():
                    result.add(str(value).strip())
                elif isinstance(value, (list, tuple, set)):
                    result.update(
                        str(item).strip()
                        for item in value
                        if isinstance(item, (str, int)) and str(item).strip()
                    )
        return result

    def _series_identity(
        self,
        resource: Optional[Dict[str, Any]],
        dimensions: Dict[str, str],
        metric_item: Dict[str, Any],
    ) -> Tuple[str, str]:
        if resource is not None:
            resource_id = resource.get("resource_id")
            resource_name = resource.get("resource_name")
            if resource_id is not None and str(resource_id).strip():
                normalized_id = str(resource_id).strip()
            else:
                normalized_id = self._dimension_identity(dimensions)
            normalized_name = str(resource_name or normalized_id).strip()
            return normalized_id, normalized_name

        resource_id = self._dimension_identity(dimensions)
        resource_name = metric_item.get("resourceName")
        if resource_name is None:
            resource_name = self._dimension_name(dimensions)
        return resource_id, str(resource_name or resource_id)

    def _cdb_series_name(
        self,
        resource: Optional[Dict[str, Any]],
        dimensions: Dict[str, str],
        service_name: str,
    ) -> str:
        """Cloud DB 서비스 아래의 실제 DB 노드와 역할을 범례에 구분한다."""

        normalized_dimensions = {
            self._normalize_dimension_name(name): str(value).strip()
            for name, value in dimensions.items()
            if str(value).strip()
        }

        def dimension_value(*names: str) -> Optional[str]:
            return next(
                (
                    normalized_dimensions[name]
                    for name in names
                    if normalized_dimensions.get(name)
                ),
                None,
            )

        node_id = dimension_value(
            "instanceno",
            "serverinstanceno",
            "dbinstanceno",
            "clouddbinstanceno",
        )
        node_name = dimension_value(
            "dbservername",
            "servername",
            "instancename",
            "resourcename",
        )
        role = dimension_value(
            "dbserverrole",
            "serverrole",
            "dbrole",
            "role",
        )

        details = resource.get("details") if resource is not None else None
        if isinstance(details, dict) and node_id:
            instance_nos = self._string_list(
                details.get("server_instance_nos")
            )
            try:
                node_index = instance_nos.index(node_id)
            except ValueError:
                node_index = None

            if node_index is not None:
                server_names = self._string_list(details.get("server_names"))
                server_roles = self._string_list(details.get("server_roles"))
                # 정규화 목록의 순서가 보존될 때만 위치 기반으로 보완한다.
                if not node_name and len(server_names) == len(instance_nos):
                    node_name = server_names[node_index]
                if not role and len(server_roles) == len(instance_nos):
                    role = server_roles[node_index]

        node_label = node_name
        if node_id:
            node_label = (
                f"{node_name} ({node_id})"
                if node_name and node_name.casefold() != node_id.casefold()
                else f"노드 {node_id}"
            )

        qualifiers = [value for value in (node_label, role) if value]
        if not qualifiers:
            return service_name
        return " · ".join((service_name, *qualifiers))

    @staticmethod
    def _string_list(value: Any) -> List[str]:
        if not isinstance(value, (list, tuple)):
            return []
        return [
            str(item).strip()
            for item in value
            if item is not None and str(item).strip()
        ]

    def _dimension_identity(self, dimensions: Dict[str, str]) -> str:
        for name, value in dimensions.items():
            if self._normalize_dimension_name(name) in self.ID_DIMENSION_HINTS:
                return str(value)
        return "|".join(f"{name}={value}" for name, value in dimensions.items())

    def _dimension_name(self, dimensions: Dict[str, str]) -> Optional[str]:
        for name, value in dimensions.items():
            if self._normalize_dimension_name(name) in self.NAME_DIMENSION_HINTS:
                return str(value)
        return None

    def _select_supported_option(
        self,
        options: Any,
        preferred_interval: str,
        aggregation_order: Sequence[str],
    ) -> Optional[Tuple[str, str]]:
        parsed = self._parse_options(options)
        if not parsed:
            return preferred_interval, aggregation_order[0]

        preferred_minutes = self.INTERVAL_MINUTES[preferred_interval]
        intervals = sorted(
            parsed,
            key=lambda name: self.INTERVAL_MINUTES.get(name, 10**9),
        )
        eligible = [
            name
            for name in intervals
            if self.INTERVAL_MINUTES.get(name, -1) >= preferred_minutes
        ]
        interval = eligible[0] if eligible else intervals[-1]
        allowed = parsed[interval]
        for aggregation in aggregation_order:
            if aggregation in allowed:
                return interval, aggregation
        for aggregation in self.AGGREGATION_ORDER:
            if aggregation in allowed:
                return interval, aggregation
        return None

    def _parse_options(self, options: Any) -> Dict[str, set[str]]:
        result: Dict[str, set[str]] = {}
        if isinstance(options, dict):
            option_items = options.items()
        elif isinstance(options, list):
            option_items = []
            for item in options:
                if not isinstance(item, dict):
                    continue
                interval = item.get("interval") or item.get("period")
                aggregations = (
                    item.get("aggregations")
                    or item.get("aggregation")
                    or item.get("calculations")
                    or item.get("values")
                )
                option_items.append((interval, aggregations))
        else:
            return result

        canonical_intervals = {
            name.casefold(): name
            for name in self.INTERVAL_MINUTES
        }
        for raw_interval, raw_aggregations in option_items:
            interval = canonical_intervals.get(str(raw_interval).casefold())
            if interval is None:
                continue
            if isinstance(raw_aggregations, dict):
                raw_aggregations = (
                    raw_aggregations.get("aggregations")
                    or raw_aggregations.get("values")
                    or raw_aggregations.get("calculations")
                )
            if isinstance(raw_aggregations, str):
                aggregations = re.split(r"[\s,|]+", raw_aggregations)
            elif isinstance(raw_aggregations, (list, tuple, set)):
                aggregations = raw_aggregations
            else:
                aggregations = []
            normalized = {
                str(value).upper()
                for value in aggregations
                if str(value).upper() in self.AGGREGATION_ORDER
            }
            if normalized:
                result[interval] = normalized
        return result

    def _deduplicate_records(
        self,
        records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = []
        seen = set()
        for record in records:
            key = self._record_identity(record)
            if key in seen:
                continue
            seen.add(key)
            result.append(record)
        return result

    def _record_identity(self, record: Dict[str, Any]) -> Tuple[Any, ...]:
        return (
            record["product_key"],
            record["metric"],
            record["interval"],
            record["aggregation"],
            self._dimension_tuple(record["dimensions"]),
        )

    def _record_sort_key(self, record: Dict[str, Any]) -> Tuple[Any, ...]:
        category_order = {
            category: index
            for index, category in enumerate(self.MONITORED_CATEGORIES)
        }
        return (
            category_order.get(record["category"], 999),
            record["product_name"].casefold(),
            record["metric"].casefold(),
            record["resource_name"].casefold(),
            self._dimension_tuple(record["dimensions"]),
        )

    def _execute_queries(
        self,
        insight_api: Any,
        records: List[Dict[str, Any]],
        start_time: int,
        end_time: int,
    ) -> None:
        grouped: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
        for record in records:
            grouped[
                (
                    record["product_key"],
                    record["interval"],
                    record["aggregation"],
                )
            ].append(record)

        for (_, interval, _), group_records in grouped.items():
            for chunk in batched(group_records, self.MAX_QUERY_SIZE):
                for window_start, window_end in query_time_windows(
                    start_time=start_time,
                    end_time=end_time,
                    interval=interval,
                ):
                    self._execute_query_chunk(
                        insight_api=insight_api,
                        records=chunk,
                        window_start=window_start,
                        window_end=window_end,
                    )

    def _execute_query_chunk(
        self,
        insight_api: Any,
        records: List[Dict[str, Any]],
        window_start: int,
        window_end: int,
    ) -> None:
        payloads = [self._query_payload(record) for record in records]
        try:
            response = insight_api.get_query_data_multiple(
                time_start=window_start,
                time_end=window_end,
                metric_info_list=payloads,
            )
            validate_collection_response(
                response,
                expected_keys=("metrics", "items", "dps"),
                allow_list=True,
                api_name="get_query_data_multiple",
            )
            response_items = self._extract_collection(
                response,
                keys=("metrics", "items"),
            )
        except Exception as exc:
            severity, metadata = self._classify_exception(exc)
            if (
                len(records) > 1
                and metadata.get("status_code") in {400, 404}
            ):
                midpoint = len(records) // 2
                self._execute_query_chunk(
                    insight_api,
                    records[:midpoint],
                    window_start,
                    window_end,
                )
                self._execute_query_chunk(
                    insight_api,
                    records[midpoint:],
                    window_start,
                    window_end,
                )
                return
            self._record_issue(
                severity=severity,
                stage="query",
                api="get_query_data_multiple",
                product_name=records[0]["product_name"],
                metric=",".join(
                    sorted({record["metric"] for record in records})
                )[:300],
                exc=exc,
                extra=metadata,
            )
            return
        self._merge_response(records, response_items)

    def _warn_empty_products(
        self,
        records: List[Dict[str, Any]],
    ) -> None:
        grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        for record in records:
            grouped[(record["category"], record["product_name"])].append(record)

        for (category, product_name), product_records in grouped.items():
            if any(record["points"] for record in product_records):
                continue
            self._record_issue(
                severity="warning",
                stage="no_metric_data",
                api="get_query_data_multiple",
                category=self.OUTPUT_CATEGORIES[category],
                product_name=product_name,
                message=(
                    "조회된 모니터링 데이터가 없습니다. Cloud Insight "
                    "모니터링 활성화 여부, 데이터 보관 기간 및 resource "
                    "dimension 매핑을 확인하십시오."
                ),
            )

    def _query_payload(self, record: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "prodKey": record["product_key"],
            "metric": record["metric"],
            "interval": record["interval"],
            "aggregation": record["aggregation"],
            "queryAggregation": record["aggregation"],
            # SearchMetricList에서 받은 전체 tuple을 그대로 사용한다.
            "dimensions": dict(record["dimensions"]),
        }

    def _merge_response(
        self,
        records: List[Dict[str, Any]],
        response_items: List[Dict[str, Any]],
    ) -> None:
        by_key: Dict[
            Tuple[str, Tuple[Tuple[str, str], ...]],
            List[Dict[str, Any]],
        ] = defaultdict(list)
        for record in records:
            by_key[
                (
                    self._normalize_metric_name(record["metric"]),
                    self._dimension_tuple(record["dimensions"]),
                )
            ].append(record)

        for item in response_items:
            metric_name = self._metric_name(item)
            dimensions = self._normalize_dimensions(item.get("dimensions"))
            if not metric_name or not dimensions:
                continue
            candidates = by_key.get(
                (
                    self._normalize_metric_name(metric_name),
                    self._dimension_tuple(dimensions),
                ),
                [],
            )
            if not candidates:
                continue
            points = self._normalize_points(
                item.get("dps")
                if item.get("dps") is not None
                else item.get("data") or item.get("points")
            )
            for record in candidates:
                value_scale = float(record.get("value_scale") or 1.0)
                record["points"].update(
                    {
                        timestamp: value * value_scale
                        for timestamp, value in points.items()
                    }
                )

    def _normalize_points(self, raw_points: Any) -> Dict[int, float]:
        result: Dict[int, float] = {}
        if not isinstance(raw_points, list):
            return result
        for point in raw_points:
            timestamp = None
            value = None
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                timestamp, value = point[0], point[1]
            elif isinstance(point, dict):
                timestamp = point.get("timestamp")
                if timestamp is None:
                    timestamp = point.get("time")
                value = point.get("value")
            try:
                normalized_timestamp = int(timestamp)
                normalized_value = float(value)
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(normalized_value):
                continue
            result[normalized_timestamp] = normalized_value
        return result

    def _group_records(
        self,
        records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        groups: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        for record in records:
            output_category = self.OUTPUT_CATEGORIES[record["category"]]
            metric_scope = (
                "TARGET_GROUP"
                if record["category"] == "TARGET_GROUP"
                else "RESOURCE"
            )
            key = (
                output_category,
                metric_scope,
                record["product_name"],
                record["metric"],
                record["metric_label"],
                record.get("unit"),
                record["interval"],
                record["aggregation"],
            )
            group = groups.setdefault(
                key,
                {
                    "category": output_category,
                    **(
                        {
                            "metric_scope": "TARGET_GROUP",
                            "resource_type": "TargetGroup",
                        }
                        if metric_scope == "TARGET_GROUP"
                        else {}
                    ),
                    "product_name": record["product_name"],
                    "metric": record["metric"],
                    "metric_label": record["metric_label"],
                    "unit": record.get("unit"),
                    "interval": record["interval"],
                    "aggregation": record["aggregation"],
                    "series": [],
                },
            )
            group["series"].append(
                {
                    "resource_id": record["resource_id"],
                    "resource_name": record["resource_name"],
                    "dimensions": dict(record["dimensions"]),
                    "points": [
                        [timestamp, value]
                        for timestamp, value in sorted(record["points"].items())
                    ],
                }
            )

        result = list(groups.values())
        category_order = {
            self.OUTPUT_CATEGORIES[category]: index
            for index, category in enumerate(self.MONITORED_CATEGORIES)
        }
        result.sort(
            key=lambda group: (
                category_order.get(group["category"], 999),
                group["product_name"].casefold(),
                group["metric"].casefold(),
            )
        )
        for group in result:
            group["series"].sort(
                key=lambda series: (
                    series["resource_name"].casefold(),
                    series["resource_id"].casefold(),
                    self._dimension_tuple(series["dimensions"]),
                )
            )
        return result

    def _fair_series_limit(
        self,
        records: List[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Limit series without allowing one metric to consume the quota."""
        if limit <= 0:
            return []
        if len(records) <= limit:
            return records

        grouped: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = defaultdict(list)
        for record in records:
            grouped[
                (
                    record["category"],
                    record["product_name"],
                    record["metric"],
                    record["metric_label"],
                    record.get("unit"),
                    record["interval"],
                    record["aggregation"],
                )
            ].append(record)

        selected: List[Dict[str, Any]] = []
        groups_by_category: Dict[str, List[List[Dict[str, Any]]]] = (
            defaultdict(list)
        )
        for items in grouped.values():
            groups_by_category[items[0]["category"]].append(items)

        group_records: List[List[Dict[str, Any]]] = []
        max_metric_groups = max(
            len(items) for items in groups_by_category.values()
        )
        for group_index in range(max_metric_groups):
            for category in self.MONITORED_CATEGORIES:
                category_groups = groups_by_category.get(category, [])
                if group_index < len(category_groups):
                    group_records.append(category_groups[group_index])

        max_group_size = max(len(items) for items in group_records)
        for series_index in range(max_group_size):
            for items in group_records:
                if series_index >= len(items):
                    continue
                selected.append(items[series_index])
                if len(selected) == limit:
                    selected.sort(key=self._record_sort_key)
                    return selected
        return selected

    def _dimension_tuple(
        self,
        dimensions: Dict[str, Any],
    ) -> Tuple[Tuple[str, str], ...]:
        return tuple(
            sorted(
                (
                    str(name),
                    str(value),
                )
                for name, value in dimensions.items()
            )
        )

    def _select_metric_interval(
        self,
        start_time: int,
        end_time: int,
        now_time: Optional[int] = None,
    ) -> str:
        now_dt = (
            datetime.fromtimestamp(now_time / 1000, tz=self.KST)
            if now_time is not None
            else datetime.now(self.KST)
        )
        start_dt = datetime.fromtimestamp(start_time / 1000, tz=self.KST)
        duration = max(end_time - start_time, 0)
        hour = 60 * 60 * 1000
        day = 24 * hour
        if duration <= 6 * hour:
            duration_interval = "Min1"
        elif duration <= 3 * day:
            duration_interval = "Min5"
        elif duration <= 14 * day:
            duration_interval = "Min30"
        elif duration <= 90 * day:
            duration_interval = "Hour2"
        else:
            duration_interval = "Day1"

        if start_dt >= now_dt - relativedelta(days=8):
            retention_interval = "Min1"
        elif start_dt >= now_dt - relativedelta(months=1):
            retention_interval = "Min5"
        elif start_dt >= now_dt - relativedelta(months=3):
            retention_interval = "Min30"
        elif start_dt >= now_dt - relativedelta(months=6):
            retention_interval = "Hour2"
        else:
            retention_interval = "Day1"

        return max(
            (duration_interval, retention_interval),
            key=lambda name: self.INTERVAL_MINUTES[name],
        )

    @staticmethod
    def _is_percent_unit(value: Any) -> bool:
        return str(value or "").strip().casefold() in {
            "%",
            "percent",
            "percentage",
        }

    def _classify_exception(
        self,
        exc: Exception,
    ) -> Tuple[str, Dict[str, Any]]:
        metadata: Dict[str, Any] = {}
        status_code: Optional[int] = None
        response = getattr(exc, "response", None)

        if isinstance(exc, requests.HTTPError) and response is not None:
            try:
                status_code = int(response.status_code)
            except (TypeError, ValueError, AttributeError):
                status_code = None
            if status_code is not None:
                metadata["status_code"] = status_code
                metadata["retryable"] = status_code >= 500 or status_code == 429

            provider_code = self._provider_error_code(response)
            if provider_code:
                metadata["error_code"] = provider_code

        severity = (
            "warning"
            if status_code in {401, 403, 404}
            else "error"
        )
        return severity, metadata

    def _provider_error_code(self, response: Any) -> Optional[str]:
        try:
            payload = response.json()
        except (TypeError, ValueError, AttributeError):
            return None

        value = self._find_provider_code(payload)
        if value is None:
            return None
        safe_code = "".join(
            character
            for character in str(value)[:64]
            if character.isalnum() or character in {"-", "_", "."}
        )
        return safe_code or None

    def _find_provider_code(
        self,
        value: Any,
        depth: int = 0,
    ) -> Any:
        if depth > 5 or not isinstance(value, dict):
            return None
        for key in ("errorCode", "returnCode", "code"):
            candidate = value.get(key)
            if candidate not in (None, ""):
                return candidate
        for child in value.values():
            if isinstance(child, dict):
                candidate = self._find_provider_code(child, depth + 1)
                if candidate not in (None, ""):
                    return candidate
        return None

    def _record_issue(
        self,
        severity: str,
        stage: str,
        api: str,
        exc: Optional[Exception] = None,
        category: Optional[str] = None,
        product_name: Optional[str] = None,
        metric: Optional[str] = None,
        message: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        safe_message = (
            message
            or (
                safe_exception_message(exc)
                if exc is not None
                else "알 수 없는 오류"
            )
        )[:500]
        issue_key = (
            severity,
            stage,
            api,
            category,
            product_name,
            metric,
            type(exc).__name__ if exc is not None else None,
            safe_message,
        )
        if issue_key in self._issue_keys:
            return
        self._issue_keys.add(issue_key)

        issue: Dict[str, Any] = {
            "collector": self.__class__.__name__,
            "stage": stage,
            "target_type": "infrastructure_metric",
            "api": api,
            "severity": severity,
            "message": safe_message,
        }
        if category:
            issue["category"] = category
        if product_name:
            issue["product_name"] = product_name
        if metric:
            issue["metric"] = metric
        if exc is not None:
            issue["exception_type"] = type(exc).__name__
        if extra:
            issue.update(extra)

        if severity == "warning":
            self.last_warnings.append(issue)
        else:
            self.last_errors.append(issue)


__all__ = ["InfrastructureMetricCollector"]

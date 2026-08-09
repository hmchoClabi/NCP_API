import unittest

import requests

from collectors.infrastructuremetriccollector import (
    InfrastructureMetricCollector,
)


class FakeFactory:
    def __init__(self, cloud_insight=None):
        self.cloud_insight = cloud_insight
        self.calls = []

    def get(self, name):
        self.calls.append(name)
        if name != "cloud_insight" or self.cloud_insight is None:
            raise KeyError(name)
        return self.cloud_insight


class DiscoveryAPI:
    def __init__(self):
        self.search_calls = []
        self.query_calls = []
        self.schemas = [
            {"prodName": "Load Balancer Monitor(VPC)", "cwKey": "lb"},
            {"prodName": "Cloud DB for PostgreSQL(VPC)", "cwKey": "pg"},
            {"prodName": "Ncloud Kubernetes Service", "cwKey": "nks"},
        ]
        self.metrics = {
            "lb": self._lb_metrics(),
            "pg": self._pg_metrics(),
            "nks": self._nks_metrics(),
        }

    def get_system_schema_key_list(self):
        return self.schemas

    def get_search_metric_list(
        self,
        prod_key,
        dim_values=None,
        dimensions_selected_list=None,
    ):
        self.search_calls.append(
            {
                "prod_key": prod_key,
                "dim_values": dim_values,
                "dimensions_selected_list": dimensions_selected_list,
            }
        )
        selected = (dimensions_selected_list or [{}])[0]
        id_dimension = selected.get("name")
        selected_values = {
            str(value) for value in selected.get("values", [])
        }
        result = []
        for source in self.metrics[prod_key]:
            item = dict(source)
            raw_dimensions = source.get("dimensions") or {}
            if isinstance(raw_dimensions, list):
                dimensions = {
                    entry.get("dim"): entry.get("val")
                    for entry in raw_dimensions
                    if isinstance(entry, dict)
                }
            else:
                dimensions = dict(raw_dimensions)
            if id_dimension:
                selected_value = dimensions.pop(id_dimension, None)
                if str(selected_value) not in selected_values:
                    continue
                item["idDimension"] = id_dimension
            if dim_values:
                if any(
                    str(dimensions.get(entry["name"])) != str(entry["value"])
                    for entry in dim_values
                ):
                    continue
            item["dimensions"] = [
                {"dim": name, "val": value}
                for name, value in dimensions.items()
            ]
            result.append(item)
        return {"metrics": result}

    def get_query_data_multiple(
        self,
        time_start,
        time_end,
        metric_info_list,
    ):
        self.query_calls.append(
            {
                "start": time_start,
                "end": time_end,
                "payloads": metric_info_list,
            }
        )
        metrics = []
        for payload in metric_info_list:
            values = (
                (0.8, 0.9)
                if payload["metric"] == "node_available_ratio"
                else (len(payload["dimensions"]), 2.5)
            )
            metrics.append(
                {
                    "metric": payload["metric"],
                    "dimensions": payload["dimensions"],
                    "dps": [[time_start, values[0]], [time_end, values[1]]],
                }
            )
        return {"metrics": metrics}

    @staticmethod
    def _options(*aggregations):
        return {
            "Min5": list(aggregations),
            "Min30": list(aggregations),
            "Day1": list(aggregations),
        }

    def _lb_metrics(self):
        result = []
        for metric in (
            "connections_per_second",
            "concurrent_session",
            "traffic_in_byte",
            "traffic_out_byte",
        ):
            result.append(
                {
                    "metric": metric,
                    "unit": (
                        "bytes/sec" if "traffic" in metric else "count"
                    ),
                    "options": self._options("AVG", "SUM", "MAX"),
                    "dimensions": [
                        {"dim": "instanceId", "val": "lb-1"},
                        {"dim": "loadBalancerName", "val": "main-lb"},
                        {"dim": "loadBalancerPort", "val": "443"},
                        {"dim": "layerType", "val": "APPLICATION"},
                    ],
                }
            )
        result.append(
            {
                "metric": "connections_per_second",
                "options": self._options("AVG"),
                "dimensions": {"instanceId": "unmanaged-lb"},
            }
        )
        return result

    def _pg_metrics(self):
        result = []
        for metric, unit in (
            ("cpu_total", "%"),
            ("mem_used", "byte"),
            ("disk_usage", "byte"),
            ("total_session_count", "count"),
            ("active_session_count", "count"),
            ("slowquery", "count"),
        ):
            result.append(
                {
                    "metric": metric,
                    "unit": unit,
                    "options": self._options("AVG"),
                    "dimensions": {"instanceNo": "db-node-1"},
                }
            )
        return result

    def _nks_metrics(self):
        result = []
        for metric in (
            "node_ready_count",
            "node_not_ready_count",
            "node_available_ratio",
        ):
            result.append(
                {
                    "metric": metric,
                    "unit": "num" if metric.endswith("ratio") else "count",
                    "options": self._options("AVG", "MAX", "SUM", "MIN"),
                    "dimensions": {
                        "clusterUUID": "cluster-1",
                        "type": "NodeAvailability",
                    },
                }
            )
        result.append(
            {
                "metric": "real_cpu",
                "options": self._options("AVG"),
                "dimensions": {
                    "clusterUUID": "cluster-1",
                    "type": "CpuMem",
                    "pod": "pod-1",
                },
            }
        )
        return result


class ExpandedDiscoveryAPI(DiscoveryAPI):
    def __init__(self):
        super().__init__()
        self.schemas = [
            {"prodName": "System/NAS(VPC)", "cwKey": "nas"},
            {"prodName": "System/Object Storage", "cwKey": "object"},
            {
                "prodName": "System/Auto Scaling Group(Classic)",
                "cwKey": "autoscaling",
            },
            {
                "prodName": "System/Search Engine Service(VPC)",
                "cwKey": "search",
            },
            {
                "prodName": "System/Cloud Data Streaming Service(VPC)",
                "cwKey": "streaming",
            },
            {
                "prodName": "System/Cloud Hadoop(VPC)",
                "cwKey": "hadoop",
            },
            {
                "prodName": "System/Data Stream(VPC)",
                "cwKey": "data-stream",
            },
        ]
        self.metrics = {
            "nas": self._metric_items(
                ("volume_size", "volume_used_size", "volume_used_ratio"),
                {"instanceNo": "nas-1"},
            ),
            "object": self._metric_items(
                ("bucket_size", "object_count"),
                {"resourceId": "bucket-1", "regionCode": "KR"},
            ),
            "autoscaling": self._metric_items(
                ("avg_cpu_used_rto", "mem_usert", "avg_fs_usert"),
                {"autoScalingGroupNo": "asg-1"},
            ),
            "search": self._metric_items(
                (
                    "cluster_node_count",
                    "cluster_documents_total",
                    "cluster_disk_used",
                    "cpu_total",
                    "mem_usage",
                    "disk_used",
                ),
                {
                    "Svc_group_instance_no": "search-1",
                    "instanceNo": "search-node-1",
                },
            ),
            "streaming": self._metric_items(
                (
                    "cluster_total_partition",
                    "cluster_total_topic",
                    "cluster_total_message",
                    "cluster_messagesInSecMean",
                    "cluster_bytesInSec",
                    "cluster_bytesOutSec",
                    "cpu_total",
                    "mem_usage",
                    "disk_used_ratio",
                ),
                {"instanceNo": "streaming-1"},
            ),
            "hadoop": self._metric_items(
                (
                    "avg_cpu_used_rto",
                    "active_nodes",
                    "queue_used_memory_percent",
                    "queue_used_v_cores_percent",
                ),
                {
                    "instanceNo": "hadoop-1",
                    "clusterName": "do-not-use-for-joining",
                },
            ),
            "data-stream": self._metric_items(
                (
                    "bytes_in_total",
                    "messages_in_total",
                    "bytes_out_total",
                    "log_size",
                    "consumer_group_lag",
                ),
                {"topicId": "topic-1", "topicName": "orders"},
            ),
        }
        self.metrics["data-stream"][-1]["options"] = self._options("MAX")

    def _metric_items(self, names, dimensions):
        units = {
            "volume_size": "bytes",
            "volume_used_size": "bytes",
            "volume_used_ratio": "%",
            "bucket_size": "bytes",
            "object_count": "num",
            "cluster_disk_used": "GB",
            "disk_used": "GB",
            "cpu_total": "%",
            "mem_usage": "%",
            "disk_used_ratio": "%",
            "avg_cpu_used_rto": "%",
            "mem_usert": "%",
            "avg_fs_usert": "%",
            "queue_used_memory_percent": "%",
            "queue_used_v_cores_percent": "%",
            "log_size": "bytes",
        }
        return [
            {
                "metric": name,
                "unit": units.get(name, "num"),
                "options": self._options("AVG", "MAX", "SUM", "MIN"),
                "dimensions": dict(dimensions),
            }
            for name in names
        ]


class ClassicAndLegacyAPI(DiscoveryAPI):
    def __init__(self):
        super().__init__()
        self.schemas = [
            {"prodName": "System/Load Balancer", "cw_key": "classic"},
            {
                "prodName": "System/Kubernetes Service(VPC)",
                "cw_key": "legacy",
            },
        ]
        classic_dimensions = {
            "instanceId": "lb-classic",
            "publicIp": "192.0.2.10",
            "loadBalancerPort": "443",
            "serverIp": "10.0.0.10",
            "serverPort": "8443",
            "regionNumber": "1",
        }
        self.metrics = {
            "classic": [
                {
                    "metric": metric,
                    "options": self._options("AVG", "SUM"),
                    "dimensions": classic_dimensions,
                }
                for metric in (
                    "connectionsPerSecond2",
                    "concurrentSession",
                    "trafficInByte",
                    "trafficOutByte",
                )
            ],
            "legacy": [
                {
                    "metric": metric,
                    "options": self._options("AVG", "MAX"),
                    "dimensions": {
                        "clusterId": "cluster-old",
                        "controller": "deployment/api",
                        "pod": "api-1",
                        "container": "api",
                    },
                }
                for metric in ("real_cpu", "real_mem", "rqst_cpu")
            ],
        }


class FailingDiscoveryAPI:
    def get_system_schema_key_list(self):
        return [{"prodName": "Load Balancer(VPC)", "cwKey": "lb"}]

    def get_search_metric_list(self, prod_key, **kwargs):
        del prod_key
        del kwargs
        raise RuntimeError(
            "failed https://example.test/metric?privateKey=do-not-store"
        )


class OptionalDeniedAPI(DiscoveryAPI):
    def get_search_metric_list(self, prod_key, **kwargs):
        del prod_key
        del kwargs
        response = requests.Response()
        response.status_code = 403
        response._content = (
            b'{"error":{"errorCode":"2300",'
            b'"privateKey":"do-not-store"}}'
        )
        response.headers["Content-Type"] = "application/json"
        error = requests.HTTPError(
            "forbidden https://example.test/metric?privateKey=do-not-store",
            response=response,
        )
        raise error


class EmptyQueryAPI(DiscoveryAPI):
    def get_query_data_multiple(
        self,
        time_start,
        time_end,
        metric_info_list,
    ):
        self.query_calls.append(
            {
                "start": time_start,
                "end": time_end,
                "payloads": metric_info_list,
            }
        )
        return []


class PartialSearchFailureAPI(DiscoveryAPI):
    def get_search_metric_list(
        self,
        prod_key,
        dim_values=None,
        dimensions_selected_list=None,
    ):
        selected_id = dimensions_selected_list[0]["values"][0]
        if selected_id == "lb-bad":
            response = requests.Response()
            response.status_code = 404
            response._content = b'{"error":{"errorCode":"300"}}'
            response.headers["Content-Type"] = "application/json"
            raise requests.HTTPError("not found", response=response)
        return super().get_search_metric_list(
            prod_key,
            dim_values=dim_values,
            dimensions_selected_list=dimensions_selected_list,
        )


class PartialQueryFailureAPI(DiscoveryAPI):
    def get_query_data_multiple(
        self,
        time_start,
        time_end,
        metric_info_list,
    ):
        self.query_calls.append(
            {
                "start": time_start,
                "end": time_end,
                "payloads": metric_info_list,
            }
        )
        if any(
            payload["dimensions"].get("instanceId") == "lb-bad"
            for payload in metric_info_list
        ):
            response = requests.Response()
            response.status_code = 400
            response._content = b'{"error":{"errorCode":"100"}}'
            response.headers["Content-Type"] = "application/json"
            raise requests.HTTPError("bad dimension", response=response)
        return {
            "metrics": [
                {
                    "metric": payload["metric"],
                    "dimensions": payload["dimensions"],
                    "dps": [[time_start, 1.0], [time_end, 2.0]],
                }
                for payload in metric_info_list
            ]
        }


class InfrastructureMetricCollectorTests(unittest.TestCase):
    def setUp(self):
        self.infrastructure = [
            {
                "category": "LOAD_BALANCER",
                "resource_id": "lb-1",
                "resource_name": "main-lb",
            },
            {
                "category": "CDB",
                "resource_id": "db-1",
                "resource_name": "postgres",
                "platform": "POSTGRESQL",
                "details": {"server_instance_nos": ["db-node-1"]},
            },
            {
                "category": "NKS",
                "resource_id": "cluster-1",
                "resource_name": "production",
            },
            {
                "category": "SERVER",
                "resource_id": "server-1",
                "resource_name": "ignored",
            },
        ]

    def _collector(self, api):
        collector = InfrastructureMetricCollector(FakeFactory(api))
        collector._select_metric_interval = (
            lambda start_time, end_time: "Min5"
        )
        return collector

    def test_empty_or_non_monitored_resources_are_normal_empty_results(self):
        factory = FakeFactory()
        collector = InfrastructureMetricCollector(factory)

        self.assertEqual(
            collector.collect(
                [{"category": "SERVER", "resource_id": "one"}],
                start_time=1,
                end_time=2,
            ),
            [],
        )
        self.assertEqual(factory.calls, [])
        self.assertEqual(collector.last_errors, [])
        self.assertEqual(collector.last_warnings, [])

    def test_runtime_discovery_filters_inventory_and_uses_supported_options(self):
        api = DiscoveryAPI()
        collector = self._collector(api)

        groups = collector.collect(
            self.infrastructure,
            start_time=1,
            end_time=2,
        )

        by_category = {}
        for group in groups:
            by_category.setdefault(group["category"], []).append(group)

        self.assertEqual(len(by_category["LOAD_BALANCER"]), 4)
        self.assertEqual(len(by_category["CLOUD_DB"]), 4)
        self.assertEqual(len(by_category["KUBERNETES"]), 3)
        self.assertEqual(
            {group["metric"] for group in by_category["CLOUD_DB"]},
            {
                "cpu_total",
                "mem_used",
                "disk_usage",
                "total_session_count",
            },
        )
        self.assertEqual(
            {group["aggregation"] for group in by_category["CLOUD_DB"]},
            {"AVG"},
        )
        connection_group = next(
            group
            for group in by_category["CLOUD_DB"]
            if group["metric"] == "total_session_count"
        )
        self.assertEqual(connection_group["unit"], "count")
        self.assertTrue(
            all(
                group["aggregation"] == "AVG"
                and group["unit"] == "bytes/sec"
                for group in by_category["LOAD_BALANCER"]
                if group["metric"].startswith("traffic_")
            )
        )
        self.assertTrue(
            all(
                series["resource_id"] != "unmanaged-lb"
                for group in groups
                for series in group["series"]
            )
        )
        lb_payload = next(
            payload
            for call in api.query_calls
            for payload in call["payloads"]
            if payload["metric"] == "connections_per_second"
        )
        self.assertEqual(
            lb_payload["dimensions"],
            {
                "instanceId": "lb-1",
                "layerType": "APPLICATION",
                "loadBalancerName": "main-lb",
                "loadBalancerPort": "443",
            },
        )
        self.assertLessEqual(
            max(len(call["payloads"]) for call in api.query_calls),
            20,
        )
        self.assertTrue(
            all(
                series["points"] == [[1, 4.0], [2, 2.5]]
                or series["points"] == [[1, 1.0], [2, 2.5]]
                or series["points"] == [[1, 2.0], [2, 2.5]]
                for group in groups
                if group["metric"] != "node_available_ratio"
                for series in group["series"]
            )
        )
        ratio_group = next(
            group
            for group in by_category["KUBERNETES"]
            if group["metric"] == "node_available_ratio"
        )
        self.assertEqual(ratio_group["unit"], "%")
        self.assertEqual(
            ratio_group["series"][0]["points"],
            [[1, 80.0], [2, 90.0]],
        )
        self.assertTrue(
            all(
                len(call["dimensions_selected_list"][0]["values"]) == 1
                for call in api.search_calls
            )
        )
        nks_search = next(
            call for call in api.search_calls if call["prod_key"] == "nks"
        )
        self.assertEqual(
            nks_search["dim_values"],
            [{"name": "type", "value": "NodeAvailability"}],
        )
        self.assertEqual(collector.last_errors, [])

    def test_classic_aliases_are_used_but_legacy_pod_metrics_are_excluded(self):
        api = ClassicAndLegacyAPI()
        collector = self._collector(api)
        infrastructure = [
            {
                "category": "LOAD_BALANCER",
                "resource_id": "lb-classic",
                "resource_name": "classic",
            },
            {
                "category": "NKS",
                "resource_id": "cluster-old",
                "resource_name": "legacy",
            },
        ]

        groups = collector.collect(infrastructure, 1, 2)

        self.assertEqual(
            {
                group["metric"]
                for group in groups
                if group["category"] == "LOAD_BALANCER"
            },
            {
                "connectionsPerSecond2",
                "concurrentSession",
                "trafficInByte",
                "trafficOutByte",
            },
        )
        self.assertEqual(
            {
                group["metric"]
                for group in groups
                if group["category"] == "KUBERNETES"
            },
            set(),
        )
        self.assertFalse(
            any(
                payload["metric"] in {"real_cpu", "real_mem", "rqst_cpu"}
                for call in api.query_calls
                for payload in call["payloads"]
            )
        )
        classic_payload = next(
            payload
            for call in api.query_calls
            for payload in call["payloads"]
            if payload["metric"] == "connectionsPerSecond2"
        )
        self.assertEqual(
            classic_payload["dimensions"],
            {
                "instanceId": "lb-classic",
                "loadBalancerPort": "443",
                "publicIp": "192.0.2.10",
                "regionNumber": "1",
                "serverIp": "10.0.0.10",
                "serverPort": "8443",
            },
        )

    def test_extended_categories_use_documented_metrics_and_id_dimensions(self):
        api = ExpandedDiscoveryAPI()
        collector = self._collector(api)
        infrastructure = [
            {
                "category": "NAS",
                "resource_id": "nas-1",
                "resource_name": "shared-volume",
                "platform": "VPC",
            },
            {
                "category": "OBJECT_STORAGE",
                "resource_id": "bucket-1",
                "resource_name": "report-archive",
            },
            {
                "category": "AUTO_SCALING",
                "resource_id": "asg-1",
                "resource_name": "web-tier",
            },
            {
                "category": "SEARCH_ENGINE",
                "resource_id": "search-1",
                "resource_name": "catalog-search",
            },
            {
                "category": "DATA_STREAMING",
                "resource_id": "streaming-1",
                "resource_name": "events-kafka",
            },
            {
                "category": "CLOUD_HADOOP",
                "resource_id": "hadoop-1",
                "resource_name": "analytics",
            },
            {
                "category": "DATA_STREAM",
                "resource_id": "topic-1",
                "resource_name": "orders",
            },
        ]

        groups = collector.collect(infrastructure, 1, 2)

        by_category = {}
        for group in groups:
            by_category.setdefault(group["category"], set()).add(
                group["metric"]
            )
        self.assertEqual(
            by_category,
            {
                "NAS": {
                    "volume_size",
                    "volume_used_size",
                    "volume_used_ratio",
                },
                "OBJECT_STORAGE": {"bucket_size", "object_count"},
                "AUTO_SCALING": {
                    "avg_cpu_used_rto",
                    "mem_usert",
                    "avg_fs_usert",
                },
                "SEARCH_ENGINE": {
                    "cluster_node_count",
                    "cluster_documents_total",
                    "cluster_disk_used",
                    "cpu_total",
                    "mem_usage",
                    "disk_used",
                },
                "DATA_STREAMING": {
                    "cluster_total_partition",
                    "cluster_total_topic",
                    "cluster_total_message",
                    "cluster_messagesInSecMean",
                    "cluster_bytesInSec",
                    "cluster_bytesOutSec",
                    "cpu_total",
                    "mem_usage",
                    "disk_used_ratio",
                },
                "CLOUD_HADOOP": {
                    "avg_cpu_used_rto",
                    "active_nodes",
                    "queue_used_memory_percent",
                    "queue_used_v_cores_percent",
                },
                "DATA_STREAM": {
                    "bytes_in_total",
                    "messages_in_total",
                    "bytes_out_total",
                    "log_size",
                    "consumer_group_lag",
                },
            },
        )
        expected_dimensions = {
            "nas": "instanceNo",
            "object": "resourceId",
            "autoscaling": "autoScalingGroupNo",
            "search": "Svc_group_instance_no",
            "streaming": "instanceNo",
            "hadoop": "instanceNo",
            "data-stream": "topicId",
        }
        self.assertEqual(
            {
                call["prod_key"]:
                call["dimensions_selected_list"][0]["name"]
                for call in api.search_calls
            },
            expected_dimensions,
        )
        expected_resource_ids = {
            item["category"]: item["resource_id"]
            for item in infrastructure
        }
        self.assertTrue(
            all(
                series["resource_id"]
                == expected_resource_ids[group["category"]]
                for group in groups
                for series in group["series"]
            )
        )
        lag_group = next(
            group
            for group in groups
            if group["metric"] == "consumer_group_lag"
        )
        self.assertEqual(lag_group["aggregation"], "MAX")
        self.assertEqual(collector.last_errors, [])

    def test_name_and_unrelated_dimensions_never_join_inventory(self):
        collector = InfrastructureMetricCollector(FakeFactory())
        resource = {
            "category": "OBJECT_STORAGE",
            "resource_id": "bucket-1",
            "resource_name": "same-name",
        }

        self.assertIsNone(
            collector._match_resource(
                category="OBJECT_STORAGE",
                resources=[resource],
                dimensions={
                    "resourceName": "same-name",
                    "regionCode": "bucket-1",
                },
                metric_item={"resourceName": "same-name"},
            )
        )
        self.assertIsNone(
            collector._match_resource(
                category="SEARCH_ENGINE",
                resources=[
                    {
                        "resource_id": "search-1",
                        "resource_name": "search",
                    }
                ],
                dimensions={"instanceNo": "search-1"},
                metric_item={},
            )
        )
        self.assertIsNotNone(
            collector._match_resource(
                category="SEARCH_ENGINE",
                resources=[
                    {
                        "resource_id": "search-1",
                        "resource_name": "search",
                    }
                ],
                dimensions={"Svc_group_instance_no": "search-1"},
                metric_item={},
            )
        )
        self.assertEqual(
            collector._attach_search_target(
                items=[
                    {
                        "idDimension": "resourceName",
                        "dimensions": {"resourceName": "same-name"},
                    }
                ],
                fallback_id_dimension="resourceId",
                target_id="bucket-1",
            ),
            [],
        )

    def test_selected_categories_skip_unrequested_products(self):
        api = ExpandedDiscoveryAPI()
        collector = self._collector(api)

        groups = collector.collect(
            [
                {
                    "category": "NAS",
                    "resource_id": "nas-1",
                    "platform": "VPC",
                },
                {
                    "category": "OBJECT_STORAGE",
                    "resource_id": "bucket-1",
                },
            ],
            1,
            2,
            selected_categories=["NAS"],
        )

        self.assertEqual({group["category"] for group in groups}, {"NAS"})
        self.assertEqual(
            {call["prod_key"] for call in api.search_calls},
            {"nas"},
        )

    def test_nas_products_only_query_resources_from_matching_platform(self):
        api = ExpandedDiscoveryAPI()
        api.schemas = [
            {"prodName": "System/NAS", "cwKey": "nas-classic"},
            {"prodName": "System/NAS(VPC)", "cwKey": "nas-vpc"},
        ]
        api.metrics = {
            "nas-classic": api._metric_items(
                ("volume_used_size", "volume_used_ratio"),
                {"instanceNo": "classic-nas-1"},
            ),
            "nas-vpc": api._metric_items(
                ("volume_used_size", "volume_used_ratio"),
                {"instanceNo": "vpc-nas-1"},
            ),
        }
        collector = self._collector(api)

        groups = collector.collect(
            [
                {
                    "category": "NAS",
                    "resource_id": "classic-nas-1",
                    "resource_name": "classic-volume",
                    "platform": "CLASSIC",
                },
                {
                    "category": "NAS",
                    "resource_id": "vpc-nas-1",
                    "resource_name": "vpc-volume",
                    "platform": "VPC",
                },
            ],
            1,
            2,
            selected_categories=["NAS"],
        )

        selected_ids_by_product = {
            call["prod_key"]: call["dimensions_selected_list"][0][
                "values"
            ]
            for call in api.search_calls
        }
        self.assertEqual(
            selected_ids_by_product,
            {
                "nas-classic": ["classic-nas-1"],
                "nas-vpc": ["vpc-nas-1"],
            },
        )
        resource_ids_by_product = {
            group["product_name"]: {
                series["resource_id"] for series in group["series"]
            }
            for group in groups
        }
        self.assertEqual(
            resource_ids_by_product,
            {
                "System/NAS": {"classic-nas-1"},
                "System/NAS(VPC)": {"vpc-nas-1"},
            },
        )
        self.assertEqual(
            collector.api_factory.calls,
            ["cloud_insight"],
        )

    def test_query_windowing_and_series_limit_are_bounded(self):
        api = DiscoveryAPI()
        api.schemas = [
            {"prodName": "Load Balancer(VPC)", "cwKey": "lb"},
        ]
        api.metrics["lb"] = [
            {
                "metric": "connections_per_second",
                "options": {"Min5": ["AVG"]},
                "dimensions": {"instanceId": f"lb-{index}"},
            }
            for index in range(3)
        ]
        collector = self._collector(api)
        collector.MAX_SERIES = 2
        day = 24 * 60 * 60 * 1000

        groups = collector.collect(
            [
                {
                    "category": "LOAD_BALANCER",
                    "resource_id": f"lb-{index}",
                    "resource_name": f"lb-{index}",
                }
                for index in range(3)
            ],
            start_time=0,
            end_time=20 * day - 1,
        )

        self.assertEqual(len(groups[0]["series"]), 2)
        self.assertEqual(
            [(call["start"], call["end"]) for call in api.query_calls],
            [
                (0, 7 * day - 1),
                (7 * day, 14 * day - 1),
                (14 * day, 20 * day - 1),
            ],
        )
        self.assertTrue(
            any(
                warning["stage"] == "series_limit"
                and warning["omitted_count"] == 1
                for warning in collector.last_warnings
            )
        )

    def test_series_limit_keeps_each_metric_category_represented(self):
        api = DiscoveryAPI()
        for index in range(2, 20):
            api.metrics["lb"].append(
                {
                    "metric": "connections_per_second",
                    "unit": "count/s",
                    "options": api._options("AVG"),
                    "dimensions": {"instanceId": f"lb-{index}"},
                }
            )
        collector = self._collector(api)
        collector.MAX_SERIES = 3
        infrastructure = self.infrastructure + [
            {
                "category": "LOAD_BALANCER",
                "resource_id": f"lb-{index}",
                "resource_name": f"lb-{index}",
            }
            for index in range(2, 20)
        ]

        groups = collector.collect(infrastructure, 1, 2)

        self.assertEqual(
            {group["category"] for group in groups},
            {"LOAD_BALANCER", "CLOUD_DB", "KUBERNETES"},
        )
        self.assertEqual(
            sum(len(group["series"]) for group in groups),
            collector.MAX_SERIES,
        )

    def test_discovery_failure_is_sanitized_without_raw_response(self):
        collector = self._collector(FailingDiscoveryAPI())

        groups = collector.collect(
            [
                {
                    "category": "LOAD_BALANCER",
                    "resource_id": "lb-1",
                }
            ],
            1,
            2,
        )

        self.assertEqual(groups, [])
        self.assertEqual(len(collector.last_errors), 1)
        rendered = str(collector.last_errors)
        self.assertNotIn("do-not-store", rendered)
        self.assertNotIn("privateKey", rendered)
        self.assertNotIn("?", rendered)

    def test_optional_http_denial_is_a_sanitized_warning_with_codes(self):
        api = OptionalDeniedAPI()
        api.schemas = [
            {"prodName": "Load Balancer(VPC)", "cwKey": "lb"},
        ]
        collector = self._collector(api)

        groups = collector.collect(
            [
                {
                    "category": "LOAD_BALANCER",
                    "resource_id": "lb-1",
                }
            ],
            1,
            2,
        )

        self.assertEqual(groups, [])
        self.assertEqual(collector.last_errors, [])
        self.assertEqual(len(collector.last_warnings), 1)
        warning = collector.last_warnings[0]
        self.assertEqual(warning["status_code"], 403)
        self.assertEqual(warning["error_code"], "2300")
        self.assertFalse(warning["retryable"])
        rendered = str(warning)
        self.assertNotIn("privateKey", rendered)
        self.assertNotIn("do-not-store", rendered)

    def test_empty_query_points_add_monitoring_guidance_warning(self):
        api = EmptyQueryAPI()
        api.schemas = [
            {"prodName": "Load Balancer(VPC)", "cwKey": "lb"},
        ]
        api.metrics = {
            "lb": [
                {
                    "metric": "connections_per_second",
                    "options": {"Min5": ["AVG"]},
                    "dimensions": {"instanceId": "lb-1"},
                }
            ]
        }
        collector = self._collector(api)

        groups = collector.collect(
            [
                {
                    "category": "LOAD_BALANCER",
                    "resource_id": "lb-1",
                    "resource_name": "main-lb",
                }
            ],
            1,
            2,
        )

        self.assertEqual(groups[0]["series"][0]["points"], [])
        self.assertTrue(
            any(
                warning["stage"] == "no_metric_data"
                and warning["category"] == "LOAD_BALANCER"
                and "모니터링 활성화" in warning["message"]
                and "보관 기간" in warning["message"]
                and "dimension" in warning["message"]
                for warning in collector.last_warnings
            )
        )

    def test_metric_discovery_failure_is_isolated_per_target(self):
        api = PartialSearchFailureAPI()
        api.schemas = [
            {"prodName": "Load Balancer(VPC)", "cwKey": "lb"}
        ]
        api.metrics["lb"].append(
            {
                "metric": "connections_per_second",
                "unit": "count/sec",
                "options": api._options("AVG"),
                "dimensions": {"instanceId": "lb-bad"},
            }
        )
        collector = self._collector(api)

        groups = collector.collect(
            [
                {
                    "category": "LOAD_BALANCER",
                    "resource_id": "lb-1",
                    "resource_name": "good",
                },
                {
                    "category": "LOAD_BALANCER",
                    "resource_id": "lb-bad",
                    "resource_name": "bad",
                },
            ],
            1,
            2,
        )

        self.assertTrue(groups)
        self.assertTrue(
            all(
                series["resource_id"] == "lb-1"
                for group in groups
                for series in group["series"]
            )
        )
        self.assertTrue(
            any(
                warning["stage"] == "metric_discovery"
                and warning["target_id"] == "lb-bad"
                for warning in collector.last_warnings
            )
        )

    def test_bad_query_dimension_is_split_from_valid_series(self):
        api = PartialQueryFailureAPI()
        api.schemas = [
            {"prodName": "Load Balancer(VPC)", "cwKey": "lb"}
        ]
        api.metrics["lb"].append(
            {
                "metric": "connections_per_second",
                "unit": "count/sec",
                "options": api._options("AVG"),
                "dimensions": {"instanceId": "lb-bad"},
            }
        )
        collector = self._collector(api)

        groups = collector.collect(
            [
                {
                    "category": "LOAD_BALANCER",
                    "resource_id": "lb-1",
                    "resource_name": "good",
                },
                {
                    "category": "LOAD_BALANCER",
                    "resource_id": "lb-bad",
                    "resource_name": "bad",
                },
            ],
            1,
            2,
        )

        points_by_resource = {
            series["resource_id"]: series["points"]
            for group in groups
            for series in group["series"]
        }
        self.assertEqual(points_by_resource["lb-1"], [[1, 1.0], [2, 2.0]])
        self.assertEqual(points_by_resource["lb-bad"], [])
        self.assertTrue(
            any(error["stage"] == "query" for error in collector.last_errors)
        )

    def test_metric_discovery_target_count_is_bounded(self):
        api = DiscoveryAPI()
        api.schemas = [
            {"prodName": "Load Balancer(VPC)", "cwKey": "lb"}
        ]
        api.metrics["lb"] = [
            {
                "metric": "connections_per_second",
                "unit": "count/sec",
                "options": api._options("AVG"),
                "dimensions": {"instanceId": f"lb-{index}"},
            }
            for index in range(3)
        ]
        collector = self._collector(api)
        collector.MAX_DISCOVERY_TARGETS = 2

        groups = collector.collect(
            [
                {
                    "category": "LOAD_BALANCER",
                    "resource_id": f"lb-{index}",
                    "resource_name": f"lb-{index}",
                }
                for index in range(3)
            ],
            1,
            2,
        )

        self.assertEqual(len(api.search_calls), 2)
        self.assertEqual(len(groups[0]["series"]), 2)
        self.assertTrue(
            any(
                warning["stage"] == "discovery_target_limit"
                and warning["omitted_count"] == 1
                for warning in collector.last_warnings
            )
        )

    def test_supported_option_uses_coarser_retained_interval(self):
        collector = InfrastructureMetricCollector(FakeFactory())

        self.assertEqual(
            collector._select_supported_option(
                options={
                    "Min1": ["SUM"],
                    "Min30": ["AVG"],
                    "Hour2": ["MAX"],
                },
                preferred_interval="Min5",
                aggregation_order=("AVG", "MAX"),
            ),
            ("Min30", "AVG"),
        )

    def test_metric_interval_uses_report_duration_and_retention(self):
        collector = InfrastructureMetricCollector(FakeFactory())
        hour = 60 * 60 * 1000
        day = 24 * hour
        now = 200 * day

        self.assertEqual(
            collector._select_metric_interval(
                now - 6 * hour,
                now,
                now_time=now,
            ),
            "Min1",
        )
        self.assertEqual(
            collector._select_metric_interval(
                now - 7 * day,
                now,
                now_time=now,
            ),
            "Min30",
        )
        self.assertEqual(
            collector._select_metric_interval(
                now - 31 * day,
                now,
                now_time=now,
            ),
            "Hour2",
        )

    def test_missing_cdb_child_ids_reports_metric_mapping_warning(self):
        api = DiscoveryAPI()
        api.schemas = [
            {"prodName": "Cloud DB for PostgreSQL(VPC)", "cwKey": "pg"}
        ]
        collector = self._collector(api)

        groups = collector.collect(
            [
                {
                    "category": "CLOUD_DB",
                    "resource_id": "db-service-1",
                    "resource_name": "postgres",
                    "platform": "POSTGRESQL",
                    "details": {},
                }
            ],
            1,
            2,
        )

        self.assertEqual(groups, [])
        self.assertEqual(api.search_calls, [])
        self.assertTrue(
            any(
                warning["stage"] == "metric_mapping"
                and warning["category"] == "CLOUD_DB"
                and "dimension" in warning["message"]
                for warning in collector.last_warnings
            )
        )

    def test_mssql_user_connections_are_selected_as_count(self):
        api = DiscoveryAPI()
        api.schemas = [
            {"prodName": "Cloud DB for MSSQL(VPC)", "cwKey": "mssql"}
        ]
        api.metrics = {
            "mssql": [
                {
                    "metric": "mssql_user_connection",
                    "unit": "num",
                    "options": api._options("AVG"),
                    "dimensions": {"instanceNo": "mssql-node-1"},
                }
            ]
        }
        collector = self._collector(api)

        groups = collector.collect(
            [
                {
                    "category": "CLOUD_DB",
                    "resource_id": "mssql-service-1",
                    "resource_name": "mssql",
                    "platform": "MSSQL",
                    "details": {
                        "server_instance_nos": ["mssql-node-1"]
                    },
                }
            ],
            1,
            2,
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["metric"], "mssql_user_connection")
        self.assertEqual(groups[0]["unit"], "count")

    def test_target_group_metrics_use_target_group_numbers_without_lb_mixup(self):
        api = DiscoveryAPI()
        api.schemas = [
            {
                "prodName": "System/Load Balancer(VPC)",
                "cwKey": "lb",
            },
            {
                "prodName": "System/Load Balancer Target Group(VPC)",
                "cwKey": "target-group",
            },
        ]
        api.metrics = {
            "lb": api._lb_metrics(),
            "target-group": [
                {
                    "metric": "available_host_count",
                    "unit": "num",
                    "options": api._options("MIN"),
                    "dimensions": {"targetGroupNo": "tg-1"},
                },
                {
                    "metric": "unavailable_host_count",
                    "unit": "num",
                    "options": api._options("MAX"),
                    "dimensions": {"targetGroupNo": "tg-1"},
                },
                {
                    "metric": "connections_per_second",
                    "unit": "num/sec",
                    "options": api._options("AVG"),
                    "dimensions": {"targetGroupNo": "tg-1"},
                },
                {
                    "metric": "available_host_count",
                    "unit": "num",
                    "options": api._options("MIN"),
                    "dimensions": {"targetGroupNo": "unmanaged-tg"},
                },
            ],
        }
        collector = self._collector(api)

        groups = collector.collect(
            [
                {
                    "category": "LOAD_BALANCER",
                    "resource_id": "lb-1",
                    "resource_name": "main-lb",
                },
                {
                    "category": "TARGET_GROUP",
                    "resource_id": "tg-1",
                    "resource_name": "web-targets",
                    "resource_type": "TargetGroup",
                    "details": {"target_group_no": "tg-1"},
                },
            ],
            1,
            2,
            selected_categories=["LOAD_BALANCER"],
        )

        self.assertEqual(
            collector._product_category(
                "System/Load Balancer Target Group(VPC)"
            ),
            "TARGET_GROUP",
        )
        target_group_searches = [
            call
            for call in api.search_calls
            if call["prod_key"] == "target-group"
        ]
        self.assertEqual(len(target_group_searches), 1)
        self.assertEqual(
            target_group_searches[0]["dimensions_selected_list"],
            [{"name": "targetGroupNo", "values": ["tg-1"]}],
        )
        load_balancer_searches = [
            call for call in api.search_calls if call["prod_key"] == "lb"
        ]
        self.assertEqual(len(load_balancer_searches), 1)
        self.assertEqual(
            load_balancer_searches[0]["dimensions_selected_list"],
            [{"name": "instanceId", "values": ["lb-1"]}],
        )

        target_group_payloads = [
            payload
            for call in api.query_calls
            for payload in call["payloads"]
            if payload["prodKey"] == "target-group"
        ]
        self.assertEqual(
            {
                payload["metric"]: payload["aggregation"]
                for payload in target_group_payloads
            },
            {
                "available_host_count": "MIN",
                "unavailable_host_count": "MAX",
            },
        )
        self.assertTrue(
            all(
                payload["dimensions"] == {"targetGroupNo": "tg-1"}
                for payload in target_group_payloads
            )
        )
        self.assertTrue(
            all(
                "targetGroupNo" not in payload["dimensions"]
                for call in api.query_calls
                for payload in call["payloads"]
                if payload["prodKey"] == "lb"
            )
        )

        target_group_groups = [
            group
            for group in groups
            if group.get("metric_scope") == "TARGET_GROUP"
        ]
        self.assertEqual(len(target_group_groups), 2)
        self.assertEqual(
            {group["category"] for group in target_group_groups},
            {"LOAD_BALANCER"},
        )
        self.assertEqual(
            {group["resource_type"] for group in target_group_groups},
            {"TargetGroup"},
        )
        self.assertEqual(
            {
                group["metric"]: group["aggregation"]
                for group in target_group_groups
            },
            {
                "available_host_count": "MIN",
                "unavailable_host_count": "MAX",
            },
        )
        self.assertTrue(
            all(group["unit"] == "count" for group in target_group_groups)
        )
        self.assertTrue(
            all(
                group["series"] == [{
                    "resource_id": "tg-1",
                    "resource_name": "web-targets",
                    "dimensions": {"targetGroupNo": "tg-1"},
                    "points": [[1, 1.0], [2, 2.5]],
                }]
                for group in target_group_groups
            )
        )

    def test_target_group_resources_are_not_monitored_without_lb_selection(self):
        api = DiscoveryAPI()
        api.schemas = [{
            "prodName": "System/Load Balancer Target Group(VPC)",
            "cwKey": "target-group",
        }]
        api.metrics = {
            "target-group": [{
                "metric": "available_host_count",
                "options": api._options("MIN"),
                "dimensions": {"targetGroupNo": "tg-1"},
            }]
        }
        collector = self._collector(api)

        groups = collector.collect(
            [{
                "category": "TARGET_GROUP",
                "resource_id": "tg-1",
                "resource_name": "web-targets",
            }],
            1,
            2,
            selected_categories=["NAS"],
        )

        self.assertEqual(groups, [])
        self.assertEqual(api.search_calls, [])
        self.assertEqual(api.query_calls, [])

    def test_server_error_remains_error_classification(self):
        collector = InfrastructureMetricCollector(FakeFactory())
        response = requests.Response()
        response.status_code = 500
        response._content = b'{"error":{"errorCode":"900"}}'
        response.headers["Content-Type"] = "application/json"
        error = requests.HTTPError("internal error", response=response)

        severity, metadata = collector._classify_exception(error)

        self.assertEqual(severity, "error")
        self.assertEqual(metadata["status_code"], 500)
        self.assertEqual(metadata["error_code"], "900")
        self.assertTrue(metadata["retryable"])

    def test_query_chunks_never_exceed_twenty_series(self):
        api = DiscoveryAPI()
        api.schemas = [
            {"prodName": "Load Balancer(VPC)", "cwKey": "lb"},
        ]
        api.metrics = {
            "lb": [
                {
                    "metric": "connections_per_second",
                    "options": {"Min5": ["AVG"]},
                    "dimensions": {"instanceId": f"lb-{index:02d}"},
                }
                for index in range(25)
            ]
        }
        collector = self._collector(api)

        collector.collect(
            [
                {
                    "category": "LOAD_BALANCER",
                    "resource_id": f"lb-{index:02d}",
                    "resource_name": f"lb-{index:02d}",
                }
                for index in range(25)
            ],
            1,
            2,
        )

        self.assertEqual(
            [len(call["payloads"]) for call in api.query_calls],
            [20, 5],
        )


if __name__ == "__main__":
    unittest.main()

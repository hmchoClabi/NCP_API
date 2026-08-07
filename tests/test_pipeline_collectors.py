import unittest
from collections import defaultdict
from datetime import datetime, timedelta
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import requests

from collectors.activitytracercollector import ActivityTracerEventCollector
from collectors.insighteventcollector import InsightEventCollector
from collectors.insightmetriccollector import InsightMetricCollector
from collectors.servercollector import ServerCollector
from normalizers.insightmetricnormalizer import InsightMetricNormalizer
from normalizers.servernormalizer import ServerNormalizer


class FakeFactory:
    def __init__(self, **apis):
        self.apis = apis

    def get(self, name):
        return self.apis[name]


class EmptyVServerAPI:
    def get_server_instance_list(self, page_no, page_size):
        return {
            "getServerInstanceListResponse": {
                "serverInstanceList": [],
            }
        }

    def get_network_interface_instance_list(self, page_no, page_size):
        return {
            "getNetworkInterfaceListResponse": {
                "networkInterfaceList": [],
            }
        }

    def get_block_storage_instance_list(self, page_no, page_size):
        return {
            "getBlockStorageInstanceListResponse": {
                "blockStorageInstanceList": [],
            }
        }


class RepeatingVServerAPI(EmptyVServerAPI):
    def get_server_instance_list(self, page_no, page_size):
        return {
            "getServerInstanceListResponse": {
                "serverInstanceList": [
                    {
                        "serverInstanceNo": 1,
                        "serverName": "one",
                    },
                    {
                        "serverInstanceNo": 2,
                        "serverName": "two",
                    },
                ],
            }
        }


class FailingVServerAPI(EmptyVServerAPI):
    def get_server_instance_list(self, page_no, page_size):
        raise RuntimeError("server API unavailable")


class ErrorEnvelopeVServerAPI(EmptyVServerAPI):
    def get_server_instance_list(self, page_no, page_size):
        return {
            "error": {
                "errorCode": "210",
                "message": "authentication failed",
            }
        }


class SensitiveFailingVServerAPI(EmptyVServerAPI):
    def get_server_instance_list(self, page_no, page_size):
        raise RuntimeError(
            "request failed for "
            "https://example.com/path?token=do-not-store&privateKey=hidden"
        )


class EventAPIWithoutCwKey:
    def __init__(self):
        self.calls = []

    def get_search_event(
        self,
        start_time,
        end_time,
        page_no,
        page_size,
    ):
        self.calls.append(
            {
                "start_time": start_time,
                "end_time": end_time,
                "page_no": page_no,
                "page_size": page_size,
            }
        )
        return {
            "events": [
                {
                    "eventId": 1,
                    "prodKey": "server-key",
                    "resourceName": "server-one",
                    "dimension": [
                        {"dim": "instanceNo", "val": 101},
                    ],
                },
                {
                    "eventId": 2,
                    "prodKey": "server-key",
                    "resourceName": "server-two",
                    "dimension": "malformed-but-contained",
                },
                {
                    "eventId": 3,
                    "prodKey": "other-key",
                    "resourceName": "other",
                },
            ],
            "totalRecords": 3,
        }


class RepeatingEventAPI:
    def get_search_event(
        self,
        start_time,
        end_time,
        page_no,
        page_size,
    ):
        return {
            "events": [{"eventId": "same", "resourceName": "server"}],
            "totalRecords": 2,
        }


class ErrorEnvelopeEventAPI(RepeatingEventAPI):
    def get_search_event(
        self,
        start_time,
        end_time,
        page_no,
        page_size,
    ):
        return {"errorCode": "500", "message": "internal error"}


class RepeatingActivityAPI:
    def get_activity_list(
        self,
        fromEventTime,
        toEventTime,
        page,
        size,
        nrn,
    ):
        return {
            "items": [
                {
                    "historyId": 10,
                    "resourceId": 20,
                    "resourceName": "server",
                    "productData": "malformed-but-contained",
                }
            ],
            "hasMore": "true",
        }


class MalformedActivityAPI(RepeatingActivityAPI):
    def get_activity_list(
        self,
        fromEventTime,
        toEventTime,
        page,
        size,
        nrn,
    ):
        return {"text": "temporary maintenance", "status_code": 200}


class MetricAPI:
    def __init__(self):
        self.search_calls = []
        self.metric_payloads = []
        self.metric_query_windows = []

    def get_system_schema_key_list(self):
        return [{"prodName": "Server(VPC)", "cwKey": "server-key"}]

    def get_search_metric_list(
        self,
        prod_key,
        dimensions_selected_list=None,
    ):
        instance_no = dimensions_selected_list[0]["values"][0]
        self.search_calls.append(instance_no)
        mount = "/" if instance_no == "1" else "/data"
        return {
            "metrics": [
                {
                    "metric": "fs_usert",
                    "dimensions": [
                        {"dim": "instanceNo", "val": instance_no},
                        {"dim": "mnt_nm", "val": mount},
                    ],
                }
            ]
        }

    def get_query_data_multiple(
        self,
        time_start,
        time_end,
        metric_info_list,
    ):
        self.metric_payloads.extend(metric_info_list)
        self.metric_query_windows.append((time_start, time_end))
        return []


class ErrorEnvelopeMetricAPI(MetricAPI):
    def get_query_data_multiple(
        self,
        time_start,
        time_end,
        metric_info_list,
    ):
        self.metric_payloads.extend(metric_info_list)
        return {"error": {"errorCode": "500"}}


class PipelineCollectorTests(unittest.TestCase):
    def test_server_collector_distinguishes_empty_from_failure(self):
        empty_collector = ServerCollector(
            FakeFactory(vserver=EmptyVServerAPI())
        )
        self.assertEqual(empty_collector.collect(), [])
        self.assertEqual(empty_collector.last_errors, [])

        failed_collector = ServerCollector(
            FakeFactory(vserver=FailingVServerAPI())
        )
        self.assertEqual(failed_collector.collect(), [])
        self.assertTrue(failed_collector.last_errors)
        self.assertEqual(
            failed_collector.last_errors[0]["stage"],
            "pagination",
        )

    def test_server_collector_records_http_status_and_provider_code(self):
        response = requests.Response()
        response.status_code = 403
        response._content = b'{"error":{"errorCode":"2300","message":"denied"}}'
        response.headers["Content-Type"] = "application/json"
        api = Mock()
        api.get_server_instance_list.side_effect = requests.HTTPError(
            "forbidden", response=response
        )
        factory = Mock()
        factory.get.return_value = api

        collector = ServerCollector(factory)
        collector._get_all_servers()

        self.assertEqual(collector.last_errors[0]["status_code"], 403)
        self.assertEqual(collector.last_errors[0]["error_code"], "2300")

    def test_server_collector_forwards_configured_region(self):
        api = Mock()
        api.get_server_instance_list.return_value = {
            "getServerInstanceListResponse": {"serverInstanceList": []}
        }
        api.get_network_interface_instance_list.return_value = {
            "getNetworkInterfaceListResponse": {"networkInterfaceList": []}
        }
        api.get_block_storage_instance_list.return_value = {
            "getBlockStorageInstanceListResponse": {
                "blockStorageInstanceList": []
            }
        }
        factory = FakeFactory(vserver=api)
        factory.credentials = Mock(region="SGN")

        ServerCollector(factory).collect()

        api.get_server_instance_list.assert_called_once_with(
            region_code="SGN",
            page_no=1,
            page_size=100,
        )
        api.get_network_interface_instance_list.assert_called_once_with(
            region_code="SGN",
            page_no=1,
            page_size=100,
        )
        api.get_block_storage_instance_list.assert_called_once_with(
            region_code="SGN",
            page_no=1,
            page_size=100,
        )

    def test_server_collector_records_http_200_error_envelope(self):
        collector = ServerCollector(
            FakeFactory(vserver=ErrorEnvelopeVServerAPI())
        )

        self.assertEqual(collector.collect(), [])
        self.assertTrue(
            any(
                error["stage"] == "response"
                for error in collector.last_errors
            )
        )

    def test_collector_error_message_redacts_exception_url_query(self):
        collector = ServerCollector(
            FakeFactory(vserver=SensitiveFailingVServerAPI())
        )

        collector.collect()

        rendered_errors = str(collector.last_errors)
        self.assertNotIn("do-not-store", rendered_errors)
        self.assertNotIn("hidden", rendered_errors)
        self.assertNotIn("token=", rendered_errors)

    def test_server_pagination_guard_deduplicates_repeated_page(self):
        collector = ServerCollector(
            FakeFactory(vserver=RepeatingVServerAPI())
        )
        collector.PAGE_SIZE = 2

        servers = collector.collect()

        self.assertEqual([item["server_id"] for item in servers], [1, 2])
        self.assertTrue(
            any(
                error["stage"] == "pagination_guard"
                for error in collector.last_errors
            )
        )

    def test_server_normalizer_joins_numeric_and_string_ids(self):
        normalized = ServerNormalizer().normalize(
            {
                "servers": [
                    {
                        "serverInstanceNo": 100,
                        "serverName": "server",
                        "networkInterfaceNoList": [200],
                        "createDate": "Jun 10, 2026, 3:49:51 PM",
                    }
                ],
                "nics": [
                    {
                        "networkInterfaceNo": "200",
                        "ip": "10.0.0.1",
                    }
                ],
                "storages": [
                    {
                        "blockStorageInstanceNo": 300,
                        "serverInstanceNo": "100",
                        "blockStorageType": {"code": "BASIC"},
                    }
                ],
            }
        )

        self.assertEqual(normalized[0]["server_id"], 100)
        self.assertEqual(normalized[0]["nic_id"], "200")
        self.assertEqual(normalized[0]["storages"][0]["storage_id"], 300)
        self.assertNotIn("create_date", normalized[0])

    def test_insight_event_filters_cw_key_without_forwarding_keyword(self):
        api = EventAPIWithoutCwKey()
        collector = InsightEventCollector(
            FakeFactory(cloud_insight=api)
        )

        grouped = collector.collect(
            start_time=1,
            end_time=2,
            cw_key="server-key",
        )

        self.assertEqual(len(collector.last_events), 2)
        self.assertEqual(
            {event["event_id"] for event in collector.last_events},
            {1, 2},
        )
        self.assertEqual(set(grouped), {"101", "server-two"})
        self.assertEqual(len(api.calls), 1)
        self.assertEqual(collector.last_errors, [])

    def test_insight_event_repeated_page_is_bounded_and_deduplicated(self):
        collector = InsightEventCollector(
            FakeFactory(cloud_insight=RepeatingEventAPI())
        )
        collector.EVENT_PAGE_SIZE = 1

        collector.collect(start_time=1, end_time=2)

        self.assertEqual(len(collector.last_events), 1)
        self.assertTrue(
            any(
                error["stage"] == "pagination_guard"
                for error in collector.last_errors
            )
        )

    def test_insight_event_records_http_200_error_envelope(self):
        collector = InsightEventCollector(
            FakeFactory(cloud_insight=ErrorEnvelopeEventAPI())
        )

        self.assertEqual(collector.collect(start_time=1, end_time=2), {})
        self.assertTrue(
            any(
                error["stage"] == "response"
                for error in collector.last_errors
            )
        )

    def test_activity_repeated_page_is_bounded_and_malformed_row_is_safe(self):
        collector = ActivityTracerEventCollector(
            FakeFactory(
                cloud_activity_tracer=RepeatingActivityAPI()
            )
        )
        collector.PAGE_SIZE = 1

        grouped = collector.collect(start_time=1, end_time=2)

        self.assertEqual(len(collector.last_events), 1)
        self.assertEqual(collector.last_events[0]["event_id"], 10)
        self.assertEqual(collector.last_events[0]["resource_id"], 20)
        self.assertEqual(collector.last_events[0]["product_data"], {})
        self.assertEqual(set(grouped), {20})
        self.assertTrue(
            any(
                error["stage"] == "pagination_guard"
                for error in collector.last_errors
            )
        )

    def test_activity_records_malformed_success_envelope(self):
        collector = ActivityTracerEventCollector(
            FakeFactory(cloud_activity_tracer=MalformedActivityAPI())
        )

        self.assertEqual(collector.collect(start_time=1, end_time=2), {})
        self.assertTrue(
            any(
                error["stage"] == "response"
                for error in collector.last_errors
            )
        )

    def test_metric_mount_candidates_are_scoped_per_server(self):
        api = MetricAPI()
        collector = InsightMetricCollector(
            FakeFactory(cloud_insight=api)
        )
        collector._select_metric_interval = (
            lambda start_time, end_time: "Hour2"
        )
        end_time = int(
            datetime(
                2026,
                6,
                30,
                23,
                59,
                59,
                tzinfo=ZoneInfo("Asia/Seoul"),
            ).timestamp()
            * 1000
        )
        start_time = int(
            datetime(
                2026,
                6,
                1,
                tzinfo=ZoneInfo("Asia/Seoul"),
            ).timestamp()
            * 1000
        )

        reports = collector.collect(
            [
                {
                    "server_id": 1,
                    "server_name": "one",
                    "create_date": "2026-01-01T00:00:00",
                },
                {
                    "server_id": "2",
                    "server_name": "two",
                    "create_date": "2026-01-01T00:00:00",
                },
            ],
            start_time=start_time,
            end_time=end_time,
        )

        filesystem_pairs = {
            (
                payload["dimensions"]["instanceNo"],
                payload["dimensions"]["mnt_nm"],
            )
            for payload in api.metric_payloads
            if payload["metric"] == "fs_usert"
        }

        self.assertEqual(api.search_calls, ["1", "2"])
        self.assertEqual(filesystem_pairs, {("1", "/"), ("2", "/data")})
        self.assertEqual(
            {payload["interval"] for payload in api.metric_payloads},
            {"Hour2"},
        )
        self.assertEqual([report["server_id"] for report in reports], [1, "2"])
        self.assertEqual(collector.last_errors, [])

    def test_metric_interval_matches_data_retention_age(self):
        collector = InsightMetricCollector(FakeFactory())
        now_dt = datetime(
            2026,
            7,
            30,
            12,
            tzinfo=ZoneInfo("Asia/Seoul"),
        )
        now_time = int(now_dt.timestamp() * 1000)

        def timestamp(days_ago):
            return int(
                (now_dt - timedelta(days=days_ago)).timestamp()
                * 1000
            )

        self.assertEqual(
            collector._select_metric_interval(
                timestamp(7),
                now_time,
                now_time=now_time,
            ),
            "Min1",
        )
        self.assertEqual(
            collector._select_metric_interval(
                timestamp(20),
                now_time,
                now_time=now_time,
            ),
            "Min5",
        )
        self.assertEqual(
            collector._select_metric_interval(
                timestamp(60),
                now_time,
                now_time=now_time,
            ),
            "Min30",
        )
        self.assertEqual(
            collector._select_metric_interval(
                timestamp(150),
                now_time,
                now_time=now_time,
            ),
            "Hour2",
        )
        self.assertEqual(
            collector._select_metric_interval(
                timestamp(400),
                now_time,
                now_time=now_time,
            ),
            "Day1",
        )

    def test_metric_query_windows_follow_interval_recommendations(self):
        collector = InsightMetricCollector(FakeFactory())
        day = 24 * 60 * 60 * 1000

        windows = collector._query_time_windows(
            start_time=0,
            end_time=20 * day - 1,
            interval="Min5",
        )

        self.assertEqual(
            windows,
            [
                (0, 7 * day - 1),
                (7 * day, 14 * day - 1),
                (14 * day, 20 * day - 1),
            ],
        )

    def test_metric_execution_queries_and_merges_each_time_window(self):
        api = MetricAPI()
        collector = InsightMetricCollector(
            FakeFactory(cloud_insight=api)
        )
        day = 24 * 60 * 60 * 1000
        queries = [
            {
                "stat_name": "avg",
                "payload": {
                    "prodKey": "server-key",
                    "metric": "used_rto",
                    "interval": "Min5",
                    "aggregation": "AVG",
                    "dimensions": {"instanceNo": "1"},
                },
            }
        ]

        collector._execute_metric_queries(
            metric_queries=queries,
            start_time=0,
            end_time=20 * day - 1,
        )

        self.assertEqual(
            api.metric_query_windows,
            [
                (0, 7 * day - 1),
                (7 * day, 14 * day - 1),
                (14 * day, 20 * day - 1),
            ],
        )

    def test_metric_records_http_200_error_envelope(self):
        api = ErrorEnvelopeMetricAPI()
        collector = InsightMetricCollector(
            FakeFactory(cloud_insight=api)
        )
        start_time = int(
            datetime(
                2026,
                6,
                1,
                tzinfo=ZoneInfo("Asia/Seoul"),
            ).timestamp()
            * 1000
        )
        end_time = int(
            datetime(
                2026,
                6,
                30,
                23,
                59,
                59,
                tzinfo=ZoneInfo("Asia/Seoul"),
            ).timestamp()
            * 1000
        )

        reports = collector.collect(
            [
                {
                    "server_id": "1",
                    "server_name": "one",
                    "create_date": "2026-01-01T00:00:00",
                }
            ],
            start_time=start_time,
            end_time=end_time,
        )

        self.assertEqual(len(reports), 1)
        self.assertTrue(
            any(
                error["stage"] == "response"
                for error in collector.last_errors
            )
        )

    def test_metric_excludes_server_created_after_report_period(self):
        api = MetricAPI()
        collector = InsightMetricCollector(
            FakeFactory(cloud_insight=api)
        )
        end_time = int(
            datetime(
                2026,
                6,
                30,
                23,
                59,
                59,
                tzinfo=ZoneInfo("Asia/Seoul"),
            ).timestamp()
            * 1000
        )
        start_time = int(
            datetime(
                2026,
                6,
                1,
                tzinfo=ZoneInfo("Asia/Seoul"),
            ).timestamp()
            * 1000
        )

        reports = collector.collect(
            [
                {
                    "server_id": "future",
                    "server_name": "future",
                    "create_date": "2026-07-01T00:00:00",
                }
            ],
            start_time=start_time,
            end_time=end_time,
        )

        self.assertEqual(reports, [])
        self.assertEqual(api.search_calls, [])
        self.assertTrue(
            any(
                error.get("severity") == "warning"
                and error["stage"] == "period_filter"
                for error in collector.last_errors
            )
        )

    def test_metric_normalizer_uses_string_join_ids_and_os_mounts(self):
        normalizer = InsightMetricNormalizer(
            aggregations={"min": "MIN", "avg": "AVG", "max": "MAX"},
            simple_metrics=[
                {
                    "metric": "used_rto",
                    "output_prefix": "cpu",
                }
            ],
            filesystem_metric={"metric": "fs_usert"},
        )
        raw_metrics = defaultdict(
            lambda: defaultdict(lambda: defaultdict(list))
        )
        normalizer.merge_metric_response(
            raw_metrics=raw_metrics,
            response=[
                {
                    "metric": "used_rto",
                    "dimensions": {"instanceNo": 1},
                    "dps": [[1, 12.5]],
                }
            ],
            stat_name="min",
        )

        report = normalizer.build_report_metrics(
            raw_metrics,
            [{"server_id": "1", "server_name": "one"}],
        )[0]

        self.assertEqual(report["cpu_min"], 12.5)
        self.assertTrue(normalizer._is_os_mount("C:\\"))
        self.assertTrue(normalizer._is_os_mount("/etc/hosts"))
        self.assertFalse(normalizer._is_os_mount("/data"))


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.customer import CustomerProfile
from app.report_options import ReportOptions
from app.runner import ReportRunner


class LegacyGroupedEventCollector:
    def __init__(self, api_factory):
        self.last_events = []
        self.last_errors = [
            {
                "collector": "InsightEventCollector",
                "stage": "pagination",
                "message": "partial",
            }
        ]

    def collect(self, start_time, end_time):
        event = {
            "event_id": "event-1",
            "resource_id": "server-1",
        }
        return {"server-1": [event, event]}


class EnvelopeEventCollector:
    def __init__(self, api_factory):
        self.last_events = []
        self.last_errors = []

    def collect(self, start_time, end_time):
        return {
            "events": [
                {
                    "event_id": "event-2",
                    "resource_id": "server-2",
                }
            ],
            "grouped_events": {},
            "errors": [
                {
                    "collector": "InsightEventCollector",
                    "stage": "response",
                    "message": "warning",
                }
            ],
        }


class MetricCollectorWithLastErrors:
    def __init__(self, api_factory):
        self.last_errors = [
            {
                "collector": "InsightMetricCollector",
                "stage": "query",
                "message": "partial",
            }
        ]

    def collect(self, servers, start_time, end_time):
        return [{"server_id": "one"}]


class EmptyServerCollector:
    def __init__(self, api_factory):
        self.last_errors = []

    def collect(self):
        return []


class CurrentServerCollector:
    def __init__(self, api_factory):
        self.last_errors = []
        self.last_raw_data = {}

    def collect(self):
        return [{
            "server_id": "current-server",
            "server_name": "current-server",
            "status": "RUN",
        }]


class EmptyInfrastructureCollector:
    def __init__(self, api_factory):
        self.last_errors = []
        self.last_warnings = []

    def collect(self, servers, server_raw_data, categories=None):
        return []


class CurrentInfrastructureCollector:
    def __init__(self, api_factory):
        self.last_errors = []
        self.last_warnings = []

    def collect(self, servers, server_raw_data, categories=None):
        return [
            {
                "category": "SERVER",
                "resource_id": "current-server",
                "resource_name": "current-server",
                "details": {"server_instance_no": "current-server"},
            },
            {
                "category": "VPC",
                "resource_id": "current-vpc",
                "resource_name": "current-vpc",
                "details": {"vpc_no": "current-vpc"},
            },
        ]


class HistoricalFallbackServerCollector:
    def __init__(self, api_factory):
        self.last_errors = []
        self.last_raw_data = {}

    def collect(self):
        return [
            {
                "server_id": "old-server",
                "server_name": "old-server",
                "status": "RUN",
            },
            {
                "server_id": "boundary-server",
                "server_name": "boundary-server",
                "status": "RUN",
            },
            {
                "server_id": "unknown-server",
                "server_name": "unknown-server",
                "status": "RUN",
            },
        ]


class HistoricalFallbackInfrastructureCollector:
    def __init__(self, api_factory):
        self.last_errors = []
        self.last_warnings = []

    def collect(self, servers, server_raw_data, categories=None):
        del servers, server_raw_data, categories
        kst = ZoneInfo("Asia/Seoul")
        before_end = int(
            datetime(2026, 8, 8, 23, 59, 59, tzinfo=kst).timestamp()
            * 1000
        )
        at_end = int(
            datetime(2026, 8, 9, 0, 0, 0, tzinfo=kst).timestamp()
            * 1000
        )
        after_end = int(
            datetime(2026, 8, 9, 0, 0, 1, tzinfo=kst).timestamp()
            * 1000
        )
        return [
            {
                "category": "SERVER",
                "resource_id": "old-server",
                "resource_name": "old-server",
                "create_time": before_end,
                "details": {"create_time_source": "RESOURCE_MANAGER"},
            },
            {
                "category": "SERVER",
                "resource_id": "boundary-server",
                "resource_name": "boundary-server",
                "create_time": at_end,
                "details": {"create_time_source": "RESOURCE_MANAGER"},
            },
            {
                "category": "SERVER",
                "resource_id": "unknown-server",
                "resource_name": "unknown-server",
                "create_time": None,
                "details": {},
            },
            {
                "category": "BLOCK_STORAGE",
                "resource_id": "old-storage",
                "resource_name": "old-storage",
                "create_time": before_end,
                "details": {"create_time_source": "RESOURCE_MANAGER"},
            },
            {
                "category": "BLOCK_STORAGE",
                "resource_id": "new-storage",
                "resource_name": "new-storage",
                "create_time": after_end,
                "details": {"create_time_source": "RESOURCE_MANAGER"},
            },
        ]


class SnapshotRepository:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.saved_report = None

    def load_period_infrastructure_snapshot(
        self,
        period,
        customer,
        reference_at=None,
    ):
        return self.snapshot

    def save_report(self, report, artifacts=None):
        self.saved_report = report
        return "report-run-id"


class EmptyInfrastructureMetricCollector:
    def __init__(self, api_factory):
        self.last_errors = []
        self.last_warnings = []

    def collect(
        self,
        infrastructure,
        start_time,
        end_time,
        selected_categories=None,
    ):
        return []


class FailingInfrastructureCollector:
    def __init__(self, api_factory):
        self.last_errors = []
        self.last_warnings = []

    def collect(self, servers, server_raw_data, categories=None):
        raise RuntimeError(
            "inventory failed https://example.test/path?privateKey=hidden"
        )


class FailingInfrastructureMetricCollector:
    def __init__(self, api_factory):
        self.last_errors = []
        self.last_warnings = []

    def collect(
        self,
        infrastructure,
        start_time,
        end_time,
        selected_categories=None,
    ):
        raise RuntimeError(
            "metric failed https://example.test/path?privateKey=hidden"
        )


class EmptyActivityCollector:
    def __init__(self, api_factory):
        self.last_errors = []

    def collect(self, start_time, end_time):
        return {}


class EmptyBillingCollector:
    def __init__(self, api_factory):
        pass

    def collect_raw(self, **kwargs):
        return {}


class FailingBillingCollector:
    def __init__(self, api_factory):
        self.last_errors = []

    def collect_raw(self, **kwargs):
        raise RuntimeError("billing unavailable")


class CapturingBillingNormalizer:
    comparison_flags = []

    def normalize(self, **kwargs):
        self.comparison_flags.append(kwargs["comparison_enabled"])
        return {
            "summary": {
                "billing_month": kwargs["billing_month"],
                "confirmed_total_amount": 0,
                "row_count": 0,
            },
            "service_summary": [],
            "network_usage_summary": [],
            "usage_summary": [],
        }


class RunnerPipelineTests(unittest.TestCase):
    def _runner_without_factory_init(self, output_dir="."):
        runner = ReportRunner.__new__(ReportRunner)
        runner.api_factory = object()
        runner.output_dir = output_dir
        return runner

    def test_runner_accepts_report_repository(self):
        repository = object()
        with patch("app.runner.APIFactory"):
            runner = ReportRunner(report_repository=repository)

        self.assertIs(runner.report_repository, repository)

    def test_runner_default_output_keeps_legacy_path(self):
        with (
            patch.dict("app.runner.os.environ", {}, clear=True),
            patch("app.runner.APIFactory"),
        ):
            runner = ReportRunner()

        self.assertEqual(runner.output_dir, "./output/report")

    def test_runner_accepts_legacy_group_map_and_preserves_flat_events(self):
        runner = self._runner_without_factory_init()

        with patch(
            "app.runner.InsightEventCollector",
            LegacyGroupedEventCollector,
        ):
            events, grouped, errors = runner.collect_insight_events(
                {"start_time": 1, "end_time": 2}
            )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_id"], "event-1")
        self.assertEqual(set(grouped), {"server-1"})
        self.assertEqual(errors[0]["message"], "partial")

    def test_runner_accepts_event_envelope_and_builds_missing_groups(self):
        runner = self._runner_without_factory_init()

        with patch(
            "app.runner.InsightEventCollector",
            EnvelopeEventCollector,
        ):
            events, grouped, errors = runner.collect_insight_events(
                {"start_time": 1, "end_time": 2}
            )

        self.assertEqual(len(events), 1)
        self.assertEqual(set(grouped), {"server-2"})
        self.assertEqual(errors[0]["stage"], "response")

    def test_runner_merges_metric_collector_last_errors(self):
        runner = self._runner_without_factory_init()

        with patch(
            "app.runner.InsightMetricCollector",
            MetricCollectorWithLastErrors,
        ):
            metrics, errors = runner.collect_insight_metrics(
                server_data=[{"server_id": "one"}],
                period={"start_time": 1, "end_time": 2},
            )

        self.assertEqual(metrics, [{"server_id": "one"}])
        self.assertEqual(errors[0]["stage"], "query")

    def test_load_balancer_monitoring_keeps_target_group_resources(self):
        runner = self._runner_without_factory_init()

        class CapturingInfrastructureMetricCollector:
            received = []

            def __init__(self, api_factory):
                self.last_errors = []
                self.last_warnings = []

            def collect(
                self,
                infrastructure,
                start_time,
                end_time,
                selected_categories=None,
            ):
                del start_time, end_time, selected_categories
                self.__class__.received = list(infrastructure)
                return []

        resources = [
            {"category": "LOAD_BALANCER", "resource_id": "lb-1"},
            {"category": "TARGET_GROUP", "resource_id": "tg-1"},
            {"category": "NAS", "resource_id": "nas-1"},
        ]

        with patch(
            "app.runner.InfrastructureMetricCollector",
            CapturingInfrastructureMetricCollector,
        ):
            runner.collect_infrastructure_metrics(
                resources,
                1,
                2,
                categories={"LOAD_BALANCER"},
            )

        self.assertEqual(
            [
                item["category"]
                for item in CapturingInfrastructureMetricCollector.received
            ],
            ["LOAD_BALANCER", "TARGET_GROUP"],
        )

    def test_optional_infrastructure_collectors_are_failure_isolated(self):
        runner = self._runner_without_factory_init()

        with patch(
            "app.runner.InfrastructureCollector",
            FailingInfrastructureCollector,
        ):
            inventory, errors, warnings = runner.collect_infrastructure(
                servers=[],
                server_raw_data={},
            )

        self.assertEqual(inventory, [])
        self.assertEqual(warnings, [])
        self.assertEqual(errors[0]["collector"], "InfrastructureCollector")
        self.assertNotIn("privateKey", errors[0]["message"])
        self.assertNotIn("hidden", errors[0]["message"])

        with patch(
            "app.runner.InfrastructureMetricCollector",
            FailingInfrastructureMetricCollector,
        ):
            metrics, errors, warnings = (
                runner.collect_infrastructure_metrics([], 1, 2)
            )

        self.assertEqual(metrics, [])
        self.assertEqual(warnings, [])
        self.assertEqual(
            errors[0]["collector"],
            "InfrastructureMetricCollector",
        )
        self.assertNotIn("privateKey", errors[0]["message"])
        self.assertNotIn("hidden", errors[0]["message"])

    def test_period_marks_only_complete_calendar_month_comparable(self):
        runner = self._runner_without_factory_init()
        runner._today_kst = lambda: date(2026, 7, 15)

        full_month = runner.build_period(
            start=date(2026, 6, 1),
            end=date(2026, 6, 30),
            period_type="month",
        )
        partial_range = runner.build_period(
            start=date(2026, 6, 2),
            end=date(2026, 6, 30),
            period_type="range",
        )
        current_month = runner.build_period(
            start=date(2026, 7, 1),
            end=date(2026, 7, 31),
            period_type="month",
        )

        self.assertTrue(full_month["is_full_month"])
        self.assertTrue(full_month["is_closed_month"])
        self.assertFalse(partial_range["is_full_month"])
        self.assertFalse(partial_range["is_closed_month"])
        self.assertTrue(current_month["is_full_month"])
        self.assertFalse(current_month["is_closed_month"])

    def test_previous_month_range_uses_injected_kst_today(self):
        runner = self._runner_without_factory_init()
        runner._today_kst = lambda: date(2026, 1, 15)

        period = runner.get_month_range()

        self.assertEqual(period["start_dt"], "2025-12-01 00:00:00")
        self.assertEqual(period["end_dt"], "2025-12-31 23:59:59")
        self.assertTrue(period["is_full_month"])
        self.assertTrue(period["is_closed_month"])

    def test_current_month_billing_query_is_clamped_to_today(self):
        runner = self._runner_without_factory_init()
        runner._today_kst = lambda: date(2026, 8, 7)
        period = runner.get_period(target_month="2026-08")

        context = runner._billing_period_context(period)

        self.assertEqual(context["usage_query_end_date"], "20260807")
        self.assertEqual(context["month_to_date_start"], "20260801")
        self.assertEqual(context["month_to_date_end"], "20260807")
        self.assertEqual(context["confirmed_demand_month"], "202607")
        self.assertFalse(context["target_month_closed"])

    def test_topology_uses_only_snapshot_observed_inside_report_period(self):
        runner = self._runner_without_factory_init()
        period = runner.build_period(
            start=date(2026, 6, 1),
            end=date(2026, 6, 30),
            period_type="month",
        )
        infrastructure = [
            {
                "category": "VPC",
                "resource_id": "vpc-1",
                "resource_name": "production-vpc",
                "details": {"vpc_no": "vpc-1"},
            },
            {
                "category": "SUBNET",
                "resource_id": "subnet-1",
                "resource_name": "application-subnet",
                "details": {"subnet_no": "subnet-1", "vpc_no": "vpc-1"},
            },
        ]

        topology = runner._build_period_topology(
            period=period,
            infrastructure=infrastructure,
            collection_metadata={
                "infrastructure": {
                    "completed_at": "2026-06-30T23:50:00+09:00",
                    "reference_at": "2026-07-15T12:00:00+09:00",
                    "source": "STORED_REPORT_SNAPSHOT",
                }
            },
            report_options=ReportOptions(),
        )

        self.assertEqual(
            topology["summary"]["time_basis"],
            "REPORT_PERIOD",
        )
        self.assertEqual(
            topology["summary"]["snapshot_source"],
            "STORED_REPORT_SNAPSHOT",
        )
        self.assertEqual(topology["summary"]["verified_edge_count"], 0)
        self.assertEqual(
            topology["summary"]["presentation_policy"][
                "excluded_empty_subnet_count"
            ],
            1,
        )

    def test_monthly_snapshot_window_covers_full_report_period(self):
        runner = self._runner_without_factory_init()
        period = runner.build_period(
            start=date(2026, 7, 1),
            end=date(2026, 7, 31),
            period_type="month",
        )

        window = runner._snapshot_eligibility_window(
            period,
            "2026-08-07T12:00:00+09:00",
        )

        self.assertEqual(
            window["eligible_start"].isoformat(),
            "2026-07-01T00:00:00+09:00",
        )
        self.assertEqual(
            window["eligible_end"].isoformat(),
            "2026-08-01T00:00:00+09:00",
        )

    def test_topology_accepts_snapshot_from_earlier_report_period_date(self):
        runner = self._runner_without_factory_init()
        period = runner.build_period(
            start=date(2026, 7, 1),
            end=date(2026, 7, 31),
            period_type="month",
        )

        topology = runner._build_period_topology(
            period=period,
            infrastructure=[{
                "category": "VPC",
                "resource_id": "stale-vpc",
                "resource_name": "must-not-appear",
                "details": {"vpc_no": "stale-vpc"},
            }],
            collection_metadata={
                "infrastructure": {
                    "completed_at": "2026-07-01T12:00:00+09:00",
                    "reference_at": "2026-07-31T23:59:59.999999+09:00",
                    "source": "STORED_REPORT_SNAPSHOT",
                }
            },
            report_options=ReportOptions(),
        )

        self.assertEqual(len(topology["nodes"]), 1)
        self.assertNotEqual(topology["summary"]["confidence"], "UNAVAILABLE")
        self.assertEqual(
            topology["summary"]["eligible_start"],
            "2026-07-01T00:00:00+09:00",
        )

    def test_live_collection_crossing_period_end_uses_stored_snapshot(self):
        snapshot = {
            "servers": [{
                "server_id": "stored-server",
                "server_name": "stored-server",
                "status": "RUN",
            }],
            "infrastructure": [{
                "category": "SERVER",
                "resource_id": "stored-server",
                "resource_name": "stored-server",
                "details": {"server_instance_no": "stored-server"},
            }],
            "report_options": {
                "resource_categories": ["SERVER"],
            },
            "collection_metadata": {
                "infrastructure": {
                    "completed_at": "2026-08-07T11:00:00+09:00",
                    "source": "LIVE_API_COLLECTION",
                    "collected_categories": ["SERVER"],
                    "inventory_completeness": (
                        "COMPLETE_FOR_SELECTED_SCOPE"
                    ),
                    "collection_issue_count": 0,
                }
            },
            "_snapshot_reference": {
                "report_run_id": "stored-run",
                "observed_at": "2026-08-07T11:00:00+09:00",
                "reference_at": "2026-08-07T12:00:00.500+09:00",
            },
        }
        repository = SnapshotRepository(snapshot)

        with tempfile.TemporaryDirectory() as temp_dir:
            runner = self._runner_without_factory_init(temp_dir)
            runner.customer = CustomerProfile(
                customer_id="customer-1",
                customer_name="Customer 1",
                cloud_account_id="account-1",
                report_options={
                    "sections": [
                        "infrastructure_inventory",
                        "infrastructure_diagram",
                    ],
                    "resource_categories": ["SERVER", "VPC"],
                    "monitoring_categories": [],
                    "diagram": {"enabled": True},
                },
            )
            runner.report_repository = repository
            runner._today_kst = lambda: date(2026, 8, 7)

            with (
                patch("app.runner.ServerCollector", CurrentServerCollector),
                patch(
                    "app.runner.InfrastructureCollector",
                    CurrentInfrastructureCollector,
                ),
                patch.object(
                    runner,
                    "_now_kst_iso",
                    side_effect=[
                        "2026-08-07T11:59:58.000000+09:00",
                        "2026-08-07T11:59:59.000000+09:00",
                        "2026-08-07T12:00:00.500000+09:00",
                        "2026-08-07T12:00:00.750000+09:00",
                    ],
                ),
            ):
                report = runner.run(
                    start_datetime="2026-08-07T00:00:00+09:00",
                    end_datetime="2026-08-07T12:00:00+09:00",
                )

        self.assertEqual(
            [item["resource_id"] for item in report.infrastructure],
            ["stored-server"],
        )
        self.assertEqual(
            report.collection_metadata["infrastructure"]["source"],
            "STORED_REPORT_SNAPSHOT",
        )
        self.assertEqual(
            report.collection_metadata["infrastructure"][
                "inventory_completeness"
            ],
            "PARTIAL",
        )
        self.assertTrue(any(
            warning.get("code")
            == "SNAPSHOT_CATEGORY_COVERAGE_INCOMPLETE"
            for warning in report.collection_warnings
        ))

    def test_past_period_without_snapshot_uses_creation_time_fallback(self):
        repository = SnapshotRepository(None)

        with tempfile.TemporaryDirectory() as temp_dir:
            runner = self._runner_without_factory_init(temp_dir)
            runner.customer = CustomerProfile(
                customer_id="customer-1",
                customer_name="Customer 1",
                cloud_account_id="account-1",
                report_options={
                    "sections": [
                        "infrastructure_inventory",
                        "infrastructure_diagram",
                        "monitoring",
                    ],
                    "resource_categories": ["SERVER", "BLOCK_STORAGE"],
                    "monitoring_categories": ["SERVER"],
                    "diagram": {"enabled": True},
                },
            )
            runner.report_repository = repository
            runner._today_kst = lambda: date(2026, 8, 9)

            with (
                patch(
                    "app.runner.ServerCollector",
                    HistoricalFallbackServerCollector,
                ),
                patch(
                    "app.runner.InfrastructureCollector",
                    HistoricalFallbackInfrastructureCollector,
                ),
                patch.object(
                    runner,
                    "_now_kst_iso",
                    return_value="2026-08-09T12:00:00+09:00",
                ),
                patch.object(
                    runner,
                    "collect_insight_metrics",
                    return_value=([{"server_id": "old-server"}], []),
                ) as metric_collector,
            ):
                report = runner.run(target_day="2026-08-08")
                html_text = (
                    Path(temp_dir) / "ncp_report_20260808_20260808.html"
                ).read_text(encoding="utf-8")

        self.assertEqual(
            [server["server_id"] for server in report.servers],
            ["old-server", "unknown-server"],
        )
        self.assertEqual(
            [resource["resource_id"] for resource in report.infrastructure],
            ["old-server", "unknown-server", "old-storage"],
        )
        metric_servers = metric_collector.call_args.kwargs["server_data"]
        self.assertEqual(
            [server["server_id"] for server in metric_servers],
            ["old-server", "unknown-server"],
        )
        metadata = report.collection_metadata["infrastructure"]
        self.assertEqual(metadata["source"], "CURRENT_API_COLLECTION")
        self.assertEqual(
            metadata["time_basis"],
            "CURRENT_STATE_FILTERED_BY_CREATE_TIME",
        )
        self.assertEqual(metadata["inventory_completeness"], "PARTIAL")
        self.assertEqual(
            metadata["historical_filter"]["infrastructure"][
                "excluded_after_period_count"
            ],
            2,
        )
        self.assertEqual(
            metadata["historical_filter"]["unknown_create_time_count"],
            1,
        )
        self.assertTrue(any(
            warning.get("code")
            == "CURRENT_STATE_FILTERED_BY_CREATE_TIME"
            for warning in report.collection_warnings
        ))
        self.assertTrue(any(
            warning.get("code") == "RESOURCE_CREATE_TIME_UNAVAILABLE"
            for warning in report.collection_warnings
        ))
        self.assertEqual(
            report.infrastructure_topology["summary"]["confidence"],
            "PARTIAL",
        )
        self.assertEqual(
            {
                node.get("resource_id")
                for node in report.infrastructure_topology["nodes"]
            },
            {"old-server", "unknown-server", "old-storage"},
        )
        self.assertTrue(any(
            warning.get("code") == "CURRENT_STATE_TOPOLOGY_FALLBACK"
            for warning in report.infrastructure_topology["warnings"]
        ))
        self.assertIn("old-server", html_text)
        self.assertIn("old-storage", html_text)
        self.assertIn("인프라 시간 기준 안내", html_text)
        self.assertIn("보고서 생성 시점의 현재 값", html_text)
        self.assertIn("생성 시각 기반 추정", html_text)
        self.assertIn("생성 시각 미확인", html_text)
        self.assertIn("현재 관계 기반 추정", html_text)
        self.assertIn("보고 기간 당시의 정확한 구성은 아닙니다", html_text)
        self.assertNotIn("boundary-server", html_text)
        self.assertNotIn("new-storage", html_text)
        public_payload = report.to_dict()
        public_old_server = next(
            server
            for server in public_payload["servers"]
            if server["server_id"] == "old-server"
        )
        self.assertEqual(
            public_old_server["historical_presence_confidence"],
            "INFERRED_FROM_CREATE_TIME",
        )
        public_old_resource = next(
            resource
            for resource in public_payload["infrastructure"]
            if resource["resource_id"] == "old-server"
        )
        self.assertEqual(
            public_old_resource["details"][
                "historical_presence_confidence"
            ],
            "INFERRED_FROM_CREATE_TIME",
        )

    def test_future_period_does_not_use_current_state_fallback(self):
        repository = SnapshotRepository(None)

        with tempfile.TemporaryDirectory() as temp_dir:
            runner = self._runner_without_factory_init(temp_dir)
            runner.customer = CustomerProfile(
                customer_id="customer-1",
                customer_name="Customer 1",
                cloud_account_id="account-1",
                report_options={
                    "sections": ["infrastructure_inventory"],
                    "resource_categories": ["SERVER", "BLOCK_STORAGE"],
                    "monitoring_categories": [],
                    "diagram": {"enabled": False},
                },
            )
            runner.report_repository = repository
            runner._today_kst = lambda: date(2026, 8, 9)

            with (
                patch("app.runner.ServerCollector") as server_collector,
                patch(
                    "app.runner.InfrastructureCollector"
                ) as infrastructure_collector,
                patch.object(
                    runner,
                    "_now_kst_iso",
                    return_value="2026-08-09T12:00:00+09:00",
                ),
            ):
                report = runner.run(target_day="2026-08-10")

        server_collector.assert_not_called()
        infrastructure_collector.assert_not_called()
        self.assertEqual(report.servers, [])
        self.assertEqual(report.infrastructure, [])
        self.assertEqual(
            report.collection_metadata["infrastructure"]["source"],
            "UNAVAILABLE",
        )

    def test_topology_does_not_substitute_current_state_for_past_period(self):
        runner = self._runner_without_factory_init()
        period = runner.build_period(
            start=date(2026, 6, 1),
            end=date(2026, 6, 30),
            period_type="month",
        )

        topology = runner._build_period_topology(
            period=period,
            infrastructure=[{
                "category": "SERVER",
                "resource_id": "current-server",
                "resource_name": "must-not-appear",
                "details": {"server_instance_no": "current-server"},
            }],
            collection_metadata={
                "infrastructure": {
                    "completed_at": "2026-08-07T16:00:00+09:00",
                    "source": "LIVE_API_COLLECTION",
                }
            },
            report_options=ReportOptions(),
        )

        self.assertEqual(topology["summary"]["confidence"], "UNAVAILABLE")
        self.assertEqual(topology["nodes"], [])
        self.assertEqual(
            topology["warnings"][0]["code"],
            "PERIOD_SNAPSHOT_UNAVAILABLE",
        )

    def test_datetime_range_uses_exclusive_end_and_time_file_suffix(self):
        runner = self._runner_without_factory_init()

        period = runner.get_period(
            start_datetime="2026-08-02 09:00",
            end_datetime="2026-08-03 09:00",
        )

        self.assertEqual(period["period_type"], "datetime_range")
        self.assertEqual(period["start_dt"], "2026-08-02 09:00:00")
        self.assertEqual(period["end_dt"], "2026-08-03 09:00:00")
        self.assertEqual(period["end_time"] - period["start_time"], 86_399_999)
        self.assertEqual(period["use_start_date"], "20260802")
        self.assertEqual(period["use_end_date"], "20260803")
        self.assertEqual(
            period["file_suffix"],
            "20260802_090000_20260803_090000",
        )
        self.assertTrue(period["end_exclusive"])

    def test_datetime_range_preserves_fractional_period_boundaries(self):
        runner = self._runner_without_factory_init()

        period = runner.get_period(
            start_datetime="2026-08-02T09:00:00.125+09:00",
            end_datetime="2026-08-02T10:00:00.875+09:00",
        )

        self.assertEqual(period["start_dt"], "2026-08-02 09:00:00.125")
        self.assertEqual(period["end_dt"], "2026-08-02 10:00:00.875")
        self.assertEqual(period["end_time"] - period["start_time"], 3_600_749)
        self.assertFalse(
            runner._period_contains_timestamp(
                period,
                "2026-08-02T09:00:00.100+09:00",
            )
        )
        self.assertTrue(
            runner._period_contains_timestamp(
                period,
                "2026-08-02T09:00:00.125+09:00",
            )
        )

    def test_midnight_datetime_end_does_not_expand_billing_day(self):
        runner = self._runner_without_factory_init()

        period = runner.get_period(
            start_datetime="2026-08-02T00:00:00",
            end_datetime="2026-08-03T00:00:00",
        )

        self.assertEqual(period["use_end_date"], "20260802")

    def test_datetime_range_rejects_non_positive_duration(self):
        runner = self._runner_without_factory_init()

        with self.assertRaisesRegex(ValueError, "빨라야"):
            runner.get_period(
                start_datetime="2026-08-02 10:00",
                end_datetime="2026-08-02 10:00",
            )

    def test_datetime_range_accepts_today_and_yesterday_aliases(self):
        runner = self._runner_without_factory_init()
        runner._today_kst = lambda: date(2026, 8, 3)

        period = runner.get_period(
            start_datetime="yesterday 09:00",
            end_datetime="today 09:00",
        )

        self.assertEqual(period["start_dt"], "2026-08-02 09:00:00")
        self.assertEqual(period["end_dt"], "2026-08-03 09:00:00")

    def test_datetime_range_accepts_korean_alias_and_t_separator(self):
        runner = self._runner_without_factory_init()
        runner._today_kst = lambda: date(2026, 8, 3)

        period = runner.get_period(
            start_datetime="오늘T14:00",
            end_datetime="오늘T15:00",
        )

        self.assertEqual(period["start_dt"], "2026-08-03 14:00:00")
        self.assertEqual(period["end_dt"], "2026-08-03 15:00:00")

    def test_period_topology_refuses_a_live_snapshot_outside_report_date(self):
        runner = self._runner_without_factory_init()
        period = runner.build_period(
            start=date(2026, 7, 1),
            end=date(2026, 7, 31),
            period_type="month",
        )

        topology = runner._build_period_topology(
            period=period,
            infrastructure=[{
                "category": "VPC",
                "resource_id": "vpc-1",
                "resource_name": "current-vpc",
                "details": {"vpc_no": "vpc-1"},
            }],
            collection_metadata={
                "infrastructure": {
                    "completed_at": "2026-08-07T12:00:00+09:00",
                    "source": "LIVE_API_COLLECTION",
                }
            },
            report_options=ReportOptions(),
        )

        self.assertEqual(topology["nodes"], [])
        self.assertEqual(topology["summary"]["confidence"], "UNAVAILABLE")
        self.assertEqual(
            topology["warnings"][0]["code"],
            "PERIOD_SNAPSHOT_UNAVAILABLE",
        )

    def test_period_topology_uses_an_observation_inside_report_date(self):
        runner = self._runner_without_factory_init()
        period = runner.build_period(
            start=date(2026, 7, 1),
            end=date(2026, 7, 31),
            period_type="month",
        )
        infrastructure = [
            {
                "category": "VPC",
                "resource_id": "vpc-1",
                "resource_name": "period-vpc",
                "details": {"vpc_no": "vpc-1"},
            },
            {
                "category": "SUBNET",
                "resource_id": "subnet-1",
                "resource_name": "period-subnet",
                "details": {
                    "subnet_no": "subnet-1",
                    "vpc_no": "vpc-1",
                },
            },
        ]

        topology = runner._build_period_topology(
            period=period,
            infrastructure=infrastructure,
            collection_metadata={
                "infrastructure": {
                    "completed_at": "2026-07-31T23:00:00+09:00",
                    "source": "STORED_REPORT_SNAPSHOT",
                    "source_report_run_id": "run-1",
                }
            },
            report_options=ReportOptions(),
        )

        self.assertEqual(topology["summary"]["verified_edge_count"], 0)
        self.assertEqual(
            topology["summary"]["presentation_policy"][
                "excluded_empty_subnet_count"
            ],
            1,
        )
        self.assertEqual(
            topology["summary"]["snapshot_source"],
            "STORED_REPORT_SNAPSHOT",
        )
        self.assertEqual(
            topology["summary"]["source_report_run_id"],
            "run-1",
        )

    def test_run_passes_billing_comparison_flag_for_scope(self):
        CapturingBillingNormalizer.comparison_flags = []

        with tempfile.TemporaryDirectory() as temp_dir:
            runner = self._runner_without_factory_init(temp_dir)
            runner._today_kst = lambda: date(2026, 7, 15)

            with (
                patch("app.runner.ServerCollector", EmptyServerCollector),
                patch(
                    "app.runner.InfrastructureCollector",
                    EmptyInfrastructureCollector,
                ),
                patch(
                    "app.runner.InfrastructureMetricCollector",
                    EmptyInfrastructureMetricCollector,
                ),
                patch(
                    "app.runner.ActivityTracerEventCollector",
                    EmptyActivityCollector,
                ),
                patch("app.runner.BillingCollector", EmptyBillingCollector),
                patch(
                    "app.runner.BillingNormalizer",
                    CapturingBillingNormalizer,
                ),
                patch.object(
                    runner,
                    "collect_insight_metrics",
                    return_value=([], []),
                ),
                patch.object(
                    runner,
                    "collect_insight_events",
                    return_value=([], {}, []),
                ),
            ):
                runner.run(target_month="2026-06")
                runner.run(target_day="2026-06-15")

        self.assertEqual(
            CapturingBillingNormalizer.comparison_flags,
            [True, False],
        )

    def test_run_returns_web_ready_result_and_writes_html(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = self._runner_without_factory_init(temp_dir)
            runner._today_kst = lambda: date(2026, 7, 15)

            with (
                patch("app.runner.ServerCollector", EmptyServerCollector),
                patch(
                    "app.runner.InfrastructureCollector",
                    EmptyInfrastructureCollector,
                ),
                patch(
                    "app.runner.InfrastructureMetricCollector",
                    EmptyInfrastructureMetricCollector,
                ),
                patch(
                    "app.runner.ActivityTracerEventCollector",
                    EmptyActivityCollector,
                ),
                patch("app.runner.BillingCollector", EmptyBillingCollector),
                patch(
                    "app.runner.BillingNormalizer",
                    CapturingBillingNormalizer,
                ),
                patch.object(
                    runner,
                    "collect_insight_metrics",
                    return_value=([], []),
                ),
                patch.object(
                    runner,
                    "collect_insight_events",
                    return_value=([], {}, []),
                ),
            ):
                report = runner.run(target_month="2026-06")

            suffix = "20260601_20260630"
            html_path = Path(temp_dir) / f"ncp_report_{suffix}.html"
            json_path = Path(temp_dir) / f"ncp_report_{suffix}.json"
            infrastructure_path = Path(temp_dir) / (
                f"infrastructure_inventory_{suffix}.json"
            )
            infrastructure_metrics_path = Path(temp_dir) / (
                f"infrastructure_metrics_{suffix}.json"
            )

            self.assertEqual(report.report_id, suffix)
            self.assertTrue(html_path.exists())
            self.assertTrue(json_path.exists())
            self.assertEqual(
                json.loads(infrastructure_path.read_text(encoding="utf-8")),
                [],
            )
            self.assertEqual(
                json.loads(
                    infrastructure_metrics_path.read_text(encoding="utf-8")
                ),
                [],
            )
            self.assertIn(
                "NCP 이용 보고서",
                html_path.read_text(encoding="utf-8"),
            )
            self.assertEqual(
                json.loads(json_path.read_text(encoding="utf-8"))[
                    "schema_version"
                ],
                "1.3",
            )

    def test_period_scoped_empty_summary_files_replace_stale_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = self._runner_without_factory_init(temp_dir)
            suffix = "20260601_20260630"
            metric_path = Path(temp_dir) / (
                f"server_metric_summary_{suffix}.json"
            )
            error_path = Path(temp_dir) / (
                f"cloud_insight_errors_{suffix}.json"
            )
            metric_path.write_text('[{"stale": true}]', encoding="utf-8")
            error_path.write_text('[{"stale": true}]', encoding="utf-8")

            runner.print_server_metric_summary([], file_suffix=suffix)
            runner.print_insight_error_summary([], file_suffix=suffix)

            self.assertEqual(
                json.loads(metric_path.read_text(encoding="utf-8")),
                [],
            )
            self.assertEqual(
                json.loads(error_path.read_text(encoding="utf-8")),
                [],
            )
            self.assertEqual(
                json.loads(
                    (Path(temp_dir) / "server_metric_summary.json").read_text(
                        encoding="utf-8"
                    )
                ),
                [],
            )
            self.assertEqual(
                json.loads(
                    (Path(temp_dir) / "cloud_insight_errors.json").read_text(
                        encoding="utf-8"
                    )
                ),
                [],
            )

    def test_billing_failure_preserves_completed_nonbilling_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = self._runner_without_factory_init(temp_dir)
            runner._today_kst = lambda: date(2026, 7, 15)

            with (
                patch("app.runner.ServerCollector", EmptyServerCollector),
                patch(
                    "app.runner.InfrastructureCollector",
                    EmptyInfrastructureCollector,
                ),
                patch(
                    "app.runner.InfrastructureMetricCollector",
                    EmptyInfrastructureMetricCollector,
                ),
                patch(
                    "app.runner.ActivityTracerEventCollector",
                    EmptyActivityCollector,
                ),
                patch(
                    "app.runner.BillingCollector",
                    FailingBillingCollector,
                ),
                patch.object(
                    runner,
                    "collect_insight_metrics",
                    return_value=([], []),
                ),
                patch.object(
                    runner,
                    "collect_insight_events",
                    return_value=([], {}, []),
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "billing unavailable",
                ):
                    runner.run(target_month="2026-06")

            suffix = "20260601_20260630"
            for filename in (
                f"server_metric_summary_{suffix}.json",
                f"cloud_insight_events_{suffix}.json",
                f"activity_tracer_events_{suffix}.json",
                f"collection_errors_{suffix}.json",
                f"infrastructure_inventory_{suffix}.json",
                f"infrastructure_metrics_{suffix}.json",
            ):
                with self.subTest(filename=filename):
                    self.assertTrue((Path(temp_dir) / filename).exists())

            errors = json.loads(
                (
                    Path(temp_dir)
                    / f"collection_errors_{suffix}.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(errors[-1]["collector"], "BillingCollector")


if __name__ == "__main__":
    unittest.main()

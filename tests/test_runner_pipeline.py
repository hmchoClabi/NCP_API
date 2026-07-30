import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

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

    def test_run_passes_billing_comparison_flag_for_scope(self):
        CapturingBillingNormalizer.comparison_flags = []

        with tempfile.TemporaryDirectory() as temp_dir:
            runner = self._runner_without_factory_init(temp_dir)
            runner._today_kst = lambda: date(2026, 7, 15)

            with (
                patch("app.runner.ServerCollector", EmptyServerCollector),
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

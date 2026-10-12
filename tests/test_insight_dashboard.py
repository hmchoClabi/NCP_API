import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from webapp.insight_dashboard import summarize_insight_alarms


KST = timezone(timedelta(hours=9))
TODAY = datetime(2026, 9, 21, tzinfo=KST)


def event(event_id="event-1", **changes):
    return {
        "event_id": event_id,
        "resource_id": "server-1",
        "resource_name": "web-1",
        "rule_id": "rule-1",
        "rule_name": "CPU 높음",
        "metric": "used_rto",
        "criteria": 90,
        "operator": "GT",
        "operator_symbol": ">",
        "unit": "%",
        "prod_key": "server",
        "level": "WARNING",
        "dimension": {"instanceNo": "server-1"},
        "start_time": "2026-09-20T11:00:00+09:00",
        "end_time": 0,
        **changes,
    }


def report(report_id="report-1", events=None, **changes):
    return {
        "id": report_id,
        "tenant_id": "tenant-1",
        "customer_name": "고객 A",
        "cloud_account_id": "account-1",
        "account_name": "운영 계정",
        "environment": "public",
        "completed_at": TODAY + timedelta(hours=9),
        "insight_events": events if events is not None else [event()],
        "dataset_statuses": [{"key": "insight_events", "status": "COLLECTED"}],
        **changes,
    }


class InsightDashboardTests(unittest.TestCase):
    def test_cronjob_recreated_pods_are_one_alarm_with_six_occurrences(self):
        events = [
            event(
                str(index),
                start_time=f"2026-09-20T{hour:02d}:03:31+09:00",
                dimension={
                    "clusterUUID": "cluster-1",
                    "namespace": "clabi",
                    "controller": "cronjob:back-sched",
                    "type": "CpuMem",
                    "pod": f"back-sched-run-{index}",
                    "nodeInstanceNo": str(index % 2),
                },
            )
            for index, hour in enumerate(range(1, 24, 4))
        ]
        original = deepcopy(events)
        result = summarize_insight_alarms([report(events=events)], TODAY)
        self.assertEqual((result["group_count"], result["event_count"]), (1, 6))
        item = result["items"][0]
        self.assertEqual((item["count"], item["open_count"]), (6, 6))
        self.assertEqual((item["first_at"].hour, item["last_at"].hour), (1, 21))
        self.assertEqual(
            [row["pod"] for row in item["occurrences"]], [row["dimension"]["pod"] for row in events]
        )
        self.assertEqual(item["workload"], "clabi · cronjob:back-sched")
        self.assertNotIn('"pod"', item["dimension"])
        self.assertEqual(events, original)

    def test_cronjob_grouping_keeps_workloads_and_measurement_dimensions_separate(self):
        dimension = {
            "clusterUUID": "cluster-1",
            "namespace": "clabi",
            "controller": "cronjob:back-sched",
            "pod": "first",
            "nodeInstanceNo": "node-1",
        }
        for changes in (
            {"clusterUUID": "cluster-2"},
            {"namespace": "other"},
            {"controller": "cronjob:other"},
            {"mount": "/data"},
            {"container": "sidecar"},
        ):
            with self.subTest(changes=changes):
                result = summarize_insight_alarms(
                    [
                        report(
                            events=[
                                event("one", dimension=dimension),
                                event("two", dimension={**dimension, "pod": "second", **changes}),
                            ]
                        )
                    ],
                    TODAY,
                )
                self.assertEqual(result["group_count"], 2)

    def test_unknown_or_non_cronjob_owner_does_not_merge_pods(self):
        dimension = {
            "clusterUUID": "cluster-1",
            "namespace": "clabi",
            "controller": "cronjob:back-sched",
            "pod": "first",
        }
        for changes in (
            {"clusterUUID": ""},
            {"namespace": ""},
            {"controller": ""},
            {"controller": "cronjob:"},
            {"controller": "deployment:api"},
        ):
            with self.subTest(changes=changes):
                result = summarize_insight_alarms(
                    [
                        report(
                            events=[
                                event("one", dimension={**dimension, **changes}),
                                event("two", dimension={**dimension, **changes, "pod": "second"}),
                            ]
                        )
                    ],
                    TODAY,
                )
                self.assertEqual(result["group_count"], 2)

    def test_simultaneous_pods_without_event_ids_are_not_deduplicated_as_one(self):
        dimension = {
            "clusterUUID": "cluster-1",
            "namespace": "clabi",
            "controller": "cronjob:back-sched",
        }
        events = [event(None, dimension={**dimension, "pod": pod}) for pod in ("first", "second")]
        result = summarize_insight_alarms([report("old", events), report("new", events)], TODAY)
        self.assertEqual((result["group_count"], result["event_count"]), (1, 2))
        self.assertEqual(len(result["items"][0]["occurrences"]), 2)

    def test_repeat_occurrences_not_report_copies_and_latest_state_wins(self):
        events = [
            event(),
            event("event-2", start_time="2026-09-20T12:00:00+09:00", level="CRITICAL"),
        ]
        result = summarize_insight_alarms(
            [
                report("old", events),
                report(
                    "new",
                    [event(end_time="2026-09-20T11:05:00+09:00"), events[1]],
                    completed_at=TODAY + timedelta(hours=10),
                ),
            ],
            TODAY,
        )
        self.assertEqual(
            (result["report_count"], result["event_count"], result["group_count"]), (2, 2, 1)
        )
        item = result["items"][0]
        self.assertEqual(
            (item["count"], item["open_count"], item["report_id"], item["severity"]),
            (2, 1, "new", "CRITICAL"),
        )
        self.assertEqual(item["first_at"].day, 20)
        self.assertEqual(item["last_at"].hour, 12)

    def test_today_is_kst_completion_not_occurrence_day(self):
        rows = [
            report("before", completed_at=TODAY - timedelta(microseconds=1)),
            report("start", completed_at="2026-09-20T15:00:00Z"),
            report("end", completed_at=TODAY + timedelta(days=1)),
            report("invalid", completed_at="invalid"),
        ]
        result = summarize_insight_alarms(rows, TODAY)
        self.assertEqual(result["report_count"], 1)
        self.assertEqual(result["items"][0]["report_id"], "start")

    def test_accounts_customers_and_dimensions_do_not_merge(self):
        result = summarize_insight_alarms(
            [
                report(),
                report("account", cloud_account_id="account-2"),
                report("customer", tenant_id="tenant-2"),
                report("gov", environment="gov"),
                report("disk", [event("event-2", dimension={"mount": "/data"})]),
                report("threshold", [event("event-3", criteria=95)]),
            ],
            TODAY,
        )
        self.assertEqual(
            (result["event_count"], result["group_count"], result["affected_customer_count"]),
            (6, 6, 2),
        )

    def test_missing_event_id_uses_identity_and_timestamp_with_explicit_uncertainty(self):
        known = event(None)
        unknown = event(None, start_time="invalid")
        result = summarize_insight_alarms(
            [
                report("one", [known, unknown]),
                report("two", [known, unknown]),
            ],
            TODAY,
        )
        self.assertEqual((result["event_count"], result["unidentified_count"]), (3, 2))
        self.assertEqual(result["items"][0]["count"], 3)

    def test_empty_failed_disabled_and_legacy_collection_are_distinguished(self):
        rows = [
            report(str(index), [], dataset_statuses=[{"key": "insight_events", "status": status}])
            for index, status in enumerate(
                ["COLLECTED_EMPTY", "PARTIAL", "FAILED", "NOT_REQUESTED"]
            )
        ]
        rows.append(report("legacy", [], dataset_statuses=None))
        result = summarize_insight_alarms(rows, TODAY)
        self.assertEqual(result["incomplete_report_count"], 4)
        self.assertEqual(result["event_count"], 0)
        self.assertEqual(summarize_insight_alarms([], TODAY)["report_count"], 0)

    def test_zero_threshold_and_bad_legacy_values_are_safe(self):
        result = summarize_insight_alarms(
            [
                report(
                    events=[
                        None,
                        event(criteria=0, start_time=10**30),
                        event("two", criteria=None, start_time=-1),
                    ]
                ),
            ],
            TODAY,
        )
        self.assertEqual(result["group_count"], 2)
        self.assertIn("> 0 %", {item["condition"] for item in result["items"]})

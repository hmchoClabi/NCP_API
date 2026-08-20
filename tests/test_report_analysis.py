import json
import unittest
from copy import deepcopy
from types import SimpleNamespace

from app.report_analysis import analyze_report
from app.report_analysis.provenance import historical_source_state


class ReportAnalysisTests(unittest.TestCase):
    def _report(self, **overrides):
        report = {
            "period": {"period_type": "day"},
            "report_options": {
                "sections": [
                    "executive_summary",
                    "billing",
                    "infrastructure_inventory",
                    "monitoring",
                    "insight_events",
                    "activity_history",
                ]
            },
            "servers": [],
            "server_metrics": [],
            "infrastructure": [],
            "infrastructure_metrics": [],
            "insight_events": [],
            "activity_events": {},
            "billing": {},
            "service_availability": {},
            "security_monitoring": {},
            "dataset_statuses": [
                {"key": "service_availability", "status": "NOT_REQUESTED"},
                {"key": "security_events", "status": "NOT_REQUESTED"},
            ],
            "collection_errors": [],
            "collection_warnings": [],
        }
        report.update(overrides)
        return report

    def _monthly_inventory_report(
        self,
        start,
        end,
        infrastructure,
        *,
        categories,
        **overrides,
    ):
        report = self._report(
            schema_version="1.5",
            period={
                "period_type": "month",
                "start_dt": f"{start} 00:00:00",
                "end_dt": f"{end} 23:59:59",
            },
            report_options={
                "schema_version": "1.4",
                "sections": ["infrastructure_inventory"],
                "resource_categories": list(categories),
                "monitoring_categories": [],
            },
            infrastructure=infrastructure,
            collection_metadata={
                "infrastructure": {
                    "time_basis": "REPORT_PERIOD",
                    "inventory_completeness": (
                        "COMPLETE_FOR_SELECTED_SCOPE"
                    ),
                    "collection_issue_count": 0,
                    "collected_categories": list(categories),
                }
            },
        )
        report.update(overrides)
        return report

    @staticmethod
    def _resource(
        category,
        resource_id,
        *,
        platform="VPC",
        name=None,
        details=None,
    ):
        return {
            "category": category,
            "resource_id": resource_id,
            "resource_name": name or resource_id,
            "platform": platform,
            "details": details or {},
        }

    def test_missing_data_is_unknown_and_never_normal_or_zero(self):
        analysis = analyze_report(self._report())

        self.assertEqual(analysis["overall_status"], "UNKNOWN")
        monitoring = self._dataset(analysis, "monitoring")
        self.assertEqual(monitoring["status"], "UNAVAILABLE")
        self.assertIsNone(monitoring["record_count"])
        self.assertNotEqual(analysis["metrics"]["status"], "AVAILABLE")
        json.dumps(analysis, ensure_ascii=False)

    def test_report_result_like_object_is_supported(self):
        report = SimpleNamespace(**self._report())

        analysis = analyze_report(report)

        self.assertEqual(analysis["version"], "1.3")
        self.assertEqual(analysis["period_type"], "DAILY")

    def test_runner_period_type_aliases_are_normalized(self):
        aliases = {
            "today": "DAILY",
            "yesterday": "DAILY",
            "prev_month": "MONTHLY",
            "datetime_range": "RANGE",
        }

        for raw, expected in aliases.items():
            with self.subTest(period_type=raw):
                analysis = analyze_report(
                    self._report(period={"period_type": raw})
                )
                self.assertEqual(analysis["period_type"], expected)

    def test_explicit_empty_is_distinct_from_failed_and_not_requested(self):
        report = self._report(dataset_statuses=[
            {
                "key": "service_availability",
                "status": "COLLECTED_EMPTY",
                "record_count": 0,
            },
            {
                "key": "security_events",
                "status": "FAILED",
                "record_count": 0,
            },
        ])

        analysis = analyze_report(report)

        self.assertEqual(
            self._dataset(analysis, "service_availability")["status"],
            "COLLECTED_EMPTY",
        )
        self.assertEqual(
            self._dataset(analysis, "security_events")["status"],
            "FAILED",
        )
        self.assertEqual(analysis["security"]["status"], "FAILED")

    def test_explicit_success_with_related_warning_is_partial(self):
        report = self._report(
            server_metrics=[{
                "server_id": "server-1",
                "raw_metrics": {
                    "used_rto": {"avg": [{"raw": {"dps": [[1, 10]]}}]}
                },
            }],
            dataset_statuses=[
                {
                    "key": "monitoring",
                    "status": "COLLECTED",
                    "record_count": 1,
                    "warning_count": 1,
                },
                {"key": "service_availability", "status": "NOT_REQUESTED"},
                {"key": "security_events", "status": "NOT_REQUESTED"},
            ],
            collection_warnings=[{
                "collector": "InfrastructureMetricCollector",
                "target_type": "infrastructure_metric",
                "api": "get_query_data_multiple",
            }],
        )

        analysis = analyze_report(report)

        self.assertEqual(
            self._dataset(analysis, "monitoring")["status"],
            "PARTIAL",
        )
        self.assertEqual(analysis["data_quality"]["overall_status"], "PARTIAL")

    def test_metric_p95_and_duration_do_not_join_across_collection_gap(self):
        minute = 60_000
        points = [
            [0, 91],
            [minute, 92],
            [5 * minute, 93],
            [6 * minute, 94],
        ]
        report = self._report(
            server_metrics=[{
                "server_id": "server-1",
                "server_name": "web-1",
                "metric_interval": "Min1",
                "raw_metrics": {
                    "used_rto": {
                        "avg": [{
                            "dimensions": {"instanceNo": "server-1"},
                            "raw": {"dps": points},
                        }]
                    }
                },
            }],
        )
        policy = {
            "thresholds": {
                "cpu_warning_percent": 90,
                "cpu_critical_percent": 95,
                "sustained_minutes": 3,
            }
        }

        analysis = analyze_report(report, policy=policy)

        summary = analysis["metrics"]["summaries"][0]
        self.assertEqual(summary["sample_count"], 4)
        self.assertAlmostEqual(summary["p95"], 93.85)
        self.assertEqual(summary["warning_duration_seconds"], 120)
        self.assertEqual(summary["critical_duration_seconds"], 0)
        self.assertFalse(any(
            finding["rule_id"] == "METRIC_CPU_SUSTAINED"
            for finding in analysis["findings"]
        ))

    def test_utilization_alert_starts_at_90_and_becomes_critical_at_95(self):
        cases = (
            (89.9, None),
            (90.0, "WARNING"),
            (95.0, "CRITICAL"),
        )

        for value, expected_severity in cases:
            with self.subTest(value=value):
                report = self._report(server_metrics=[{
                    "server_id": "server-1",
                    "server_name": "web-1",
                    "metric_interval": "Min1",
                    "raw_metrics": {
                        "used_rto": {
                            "avg": [{
                                "raw": {
                                    "dps": [
                                        [index * 60_000, value]
                                        for index in range(3)
                                    ]
                                }
                            }]
                        }
                    },
                }])

                analysis = analyze_report(
                    report,
                    policy={"thresholds": {"sustained_minutes": 3}},
                )
                metric_findings = [
                    item for item in analysis["findings"]
                    if item["rule_id"] == "METRIC_CPU_SUSTAINED"
                ]

                if expected_severity is None:
                    self.assertEqual(metric_findings, [])
                    self.assertNotIn(
                        "alert_severity",
                        analysis["metrics"]["summaries"][0],
                    )
                else:
                    self.assertEqual(len(metric_findings), 1)
                    self.assertEqual(
                        metric_findings[0]["severity"],
                        expected_severity,
                    )
                    self.assertEqual(
                        analysis["metrics"]["summaries"][0][
                            "alert_severity"
                        ],
                        expected_severity,
                    )

    def test_daily_average_bucket_does_not_claim_sustained_alert(self):
        report = self._report(server_metrics=[{
            "server_id": "server-1",
            "server_name": "web-1",
            "metric_interval": "Day1",
            "raw_metrics": {
                "used_rto": {
                    "avg": [{"raw": {"dps": [[0, 99]]}}]
                }
            },
        }])

        analysis = analyze_report(report)

        self.assertEqual(
            analysis["metrics"]["summaries"][0]["average"],
            99,
        )
        self.assertFalse(any(
            finding["rule_id"] == "METRIC_CPU_SUSTAINED"
            for finding in analysis["findings"]
        ))

    def test_zero_duration_policy_cannot_alert_below_90_percent(self):
        report = self._report(server_metrics=[{
            "server_id": "server-1",
            "server_name": "web-1",
            "metric_interval": "Min1",
            "raw_metrics": {
                "used_rto": {
                    "avg": [{"raw": {"dps": [[0, 89.9]]}}]
                }
            },
        }])
        policies = (
            {"thresholds": {"sustained_minutes": 0}},
            {"thresholds": {"CPU": {"duration_seconds": 0}}},
        )

        for policy in policies:
            with self.subTest(policy=policy):
                analysis = analyze_report(report, policy=policy)
                metric_findings = [
                    item for item in analysis["findings"]
                    if item["rule_id"] == "METRIC_CPU_SUSTAINED"
                ]

                self.assertEqual(metric_findings, [])
                self.assertNotIn(
                    "alert_severity",
                    analysis["metrics"]["summaries"][0],
                )

    def test_out_of_range_policy_is_clamped_to_supported_limits(self):
        report = self._report(server_metrics=[{
            "server_id": "server-1",
            "server_name": "web-1",
            "metric_interval": "Min1",
            "raw_metrics": {
                "used_rto": {
                    "avg": [{
                        "raw": {
                            "dps": [
                                [index * 60_000, 100]
                                for index in range(1440)
                            ]
                        }
                    }]
                }
            },
        }])
        policies = (
            {
                "thresholds": {
                    "cpu_warning_percent": 101,
                    "cpu_critical_percent": 1000,
                    "sustained_minutes": 999_999,
                }
            },
            {
                "thresholds": {
                    "CPU": {
                        "warning": 101,
                        "critical": 1000,
                        "duration_seconds": 999_999_999,
                    }
                }
            },
        )

        for policy in policies:
            with self.subTest(policy=policy):
                analysis = analyze_report(report, policy=policy)
                summary = analysis["metrics"]["summaries"][0]

                self.assertEqual(summary["warning_threshold"], 100)
                self.assertEqual(summary["critical_threshold"], 100)
                self.assertEqual(summary["critical_duration_seconds"], 86_400)
                self.assertEqual(summary["alert_severity"], "CRITICAL")

    def test_supported_server_nas_and_cdb_utilization_metrics_alert(self):
        points = [[index * 60_000, 92] for index in range(3)]
        report = self._report(
            server_metrics=[{
                "server_id": "server-1",
                "server_name": "web-1",
                "metric_interval": "Min1",
                "raw_metrics": {
                    metric: {"avg": [{"raw": {"dps": points}}]}
                    for metric in ("used_rto", "mem_usert", "fs_usert")
                },
            }],
            infrastructure_metrics=[
                {
                    "category": "NAS",
                    "metric": "volume_used_ratio",
                    "metric_label": "볼륨 사용률",
                    "unit": "%",
                    "interval": "Min1",
                    "aggregation": "AVG",
                    "series": [{
                        "resource_id": "nas-1",
                        "resource_name": "nas-prod",
                        "points": points,
                    }],
                },
                {
                    "category": "CLOUD_DB",
                    "metric": "disk_data_pct",
                    "metric_label": "데이터 디스크 사용률",
                    "unit": "%",
                    "interval": "Min1",
                    "aggregation": "AVG",
                    "series": [{
                        "resource_id": "cdb-1",
                        "resource_name": "mysql-prod",
                        "points": points,
                    }],
                },
            ],
        )

        analysis = analyze_report(
            report,
            policy={"thresholds": {"sustained_minutes": 3}},
        )
        summaries = {
            (item["resource_name"], item["metric"]): item
            for item in analysis["metrics"]["summaries"]
        }

        self.assertEqual(len(summaries), 5)
        self.assertEqual(summaries[("web-1", "used_rto")]["metric_kind"], "CPU")
        self.assertEqual(summaries[("web-1", "mem_usert")]["metric_kind"], "MEMORY")
        self.assertEqual(summaries[("web-1", "fs_usert")]["metric_kind"], "FILESYSTEM")
        self.assertEqual(summaries[("nas-prod", "volume_used_ratio")]["metric_kind"], "FILESYSTEM")
        self.assertEqual(summaries[("mysql-prod", "disk_data_pct")]["metric_kind"], "FILESYSTEM")
        self.assertTrue(all(
            item["alert_severity"] == "WARNING"
            for item in summaries.values()
        ))
        self.assertTrue(all(
            item["aggregation"] == "AVG"
            for item in summaries.values()
        ))

    def test_max_only_series_does_not_create_sustained_alert(self):
        points = [[index * 60_000, 99] for index in range(3)]
        report = self._report(
            server_metrics=[{
                "server_id": "server-1",
                "server_name": "web-1",
                "metric_interval": "Min1",
                "raw_metrics": {
                    "used_rto": {
                        "max": [{"raw": {"dps": points}}]
                    }
                },
            }],
            infrastructure_metrics=[{
                "category": "NAS",
                "metric": "volume_used_ratio",
                "metric_label": "볼륨 사용률",
                "unit": "%",
                "interval": "Min1",
                "aggregation": "MAX",
                "series": [{
                    "resource_id": "nas-1",
                    "resource_name": "nas-prod",
                    "points": points,
                }],
            }],
        )

        analysis = analyze_report(
            report,
            policy={"thresholds": {"sustained_minutes": 3}},
        )

        self.assertEqual(len(analysis["metrics"]["summaries"]), 2)
        self.assertFalse(any(
            finding["rule_id"].startswith("METRIC_")
            for finding in analysis["findings"]
        ))
        self.assertTrue(all(
            "alert_severity" not in summary
            for summary in analysis["metrics"]["summaries"]
        ))
        self.assertTrue(all(
            summary["aggregation"] == "MAX"
            for summary in analysis["metrics"]["summaries"]
        ))
        self.assertEqual(
            {
                summary["metric_kind"]
                for summary in analysis["metrics"]["summaries"]
            },
            {"CPU", "FILESYSTEM"},
        )

    def test_free_and_absolute_metrics_do_not_create_utilization_alerts(self):
        points = [[index * 60_000, 99] for index in range(3)]
        report = self._report(infrastructure_metrics=[
            {
                "category": "CLOUD_DB",
                "metric": "cpu_free_ratio",
                "metric_label": "CPU 여유율",
                "unit": "%",
                "interval": "Min1",
                "series": [{
                    "resource_id": "cdb-1",
                    "resource_name": "mysql-prod",
                    "points": points,
                }],
            },
            {
                "category": "CLOUD_DB",
                "metric": "disk_data_size",
                "metric_label": "데이터 디스크 크기",
                "unit": "byte",
                "interval": "Min1",
                "series": [{
                    "resource_id": "cdb-1",
                    "resource_name": "mysql-prod",
                    "points": points,
                }],
            },
        ])

        analysis = analyze_report(
            report,
            policy={"thresholds": {"sustained_minutes": 3}},
        )

        self.assertTrue(all(
            item["metric_kind"] is None
            for item in analysis["metrics"]["summaries"]
        ))
        self.assertFalse(any(
            item["rule_id"].startswith("METRIC_")
            for item in analysis["findings"]
        ))

    def test_sustained_metric_finding_has_stable_fingerprint(self):
        points = [[index * 60_000, 95] for index in range(3)]
        report = self._report(server_metrics=[{
            "server_id": "server-1",
            "server_name": "web-1",
            "metric_interval": "Min1",
            "raw_metrics": {
                "used_rto": {"avg": [{"raw": {"dps": points}}]}
            },
        }])
        policy = {"thresholds": {"sustained_minutes": 3}}

        first = analyze_report(report, policy=policy)
        second = analyze_report(report, policy=policy)
        finding = next(
            item for item in first["findings"]
            if item["rule_id"] == "METRIC_CPU_SUSTAINED"
        )

        self.assertEqual(first["overall_status"], "RISK")
        self.assertEqual(
            finding["fingerprint"],
            next(
                item["fingerprint"] for item in second["findings"]
                if item["rule_id"] == "METRIC_CPU_SUSTAINED"
            ),
        )

    def test_event_duration_is_not_labeled_as_mttr(self):
        start_time = 1_780_000_000_000
        report = self._report(insight_events=[{
            "event_id": "event-1",
            "level": "WARNING",
            "resource_id": "server-1",
            "resource_name": "web-1",
            "rule_name": "CPU high",
            "start_time": start_time,
            "end_time": start_time + 60_000,
        }])

        analysis = analyze_report(report)

        self.assertEqual(analysis["events"]["items"][0]["duration_seconds"], 60)
        self.assertIn("MTTA", analysis["events"]["duration_note"])
        self.assertIn("MTTR", analysis["events"]["duration_note"])

    def test_zero_event_end_time_is_treated_as_open(self):
        report = self._report(insight_events=[{
            "event_id": "event-open",
            "level": "CRITICAL",
            "start_time": 1_780_000_000_000,
            "end_time": 0,
        }])

        analysis = analyze_report(report)

        self.assertEqual(analysis["events"]["open_count"], 1)
        self.assertTrue(analysis["events"]["items"][0]["is_open"])
        self.assertIsNone(
            analysis["events"]["items"][0]["duration_seconds"]
        )

    def test_explicit_dataset_counts_prevent_cross_dataset_issue_matching(self):
        report = self._report(
            infrastructure=[{
                "category": "SERVER",
                "resource_id": "server-1",
            }],
            dataset_statuses=[
                {
                    "key": "infrastructure",
                    "status": "COLLECTED",
                    "record_count": 1,
                    "error_count": 0,
                    "warning_count": 0,
                },
                {
                    "key": "monitoring",
                    "status": "FAILED",
                    "record_count": 0,
                    "error_count": 1,
                },
                {"key": "service_availability", "status": "NOT_REQUESTED"},
                {"key": "security_events", "status": "NOT_REQUESTED"},
            ],
            collection_errors=[{
                "collector": "InsightMetricCollector",
                "target_type": "server",
                "api": "query_data",
            }],
        )

        analysis = analyze_report(report)

        self.assertEqual(
            self._dataset(analysis, "infrastructure")["status"],
            "AVAILABLE",
        )
        self.assertEqual(
            self._dataset(analysis, "monitoring")["status"],
            "FAILED",
        )

    def test_activity_failure_creates_change_finding(self):
        report = self._report(activity_events={"server-1": [{
            "event_id": "change-1",
            "event_time": 1_000,
            "product_display_name": "Server",
            "action_name": "Reboot",
            "result": "FAILED",
            "resource_id": "server-1",
            "resource_name": "web-1",
        }]})

        analysis = analyze_report(report)

        self.assertEqual(analysis["changes"]["failure_count"], 1)
        self.assertEqual(analysis["changes"]["failed_change_count"], 1)
        self.assertTrue(any(
            item["rule_id"] == "ACTIVITY_CHANGE_FAILED"
            for item in analysis["findings"]
        ))

    def test_failed_read_activity_is_not_reported_as_change_failure(self):
        report = self._report(activity_events={"server-1": [{
            "event_id": "read-1",
            "event_time": 1_000,
            "product_display_name": "Server",
            "action_name": "getServerInstanceList",
            "result": "FAILED",
            "resource_id": "server-1",
        }]})

        analysis = analyze_report(report)

        self.assertEqual(analysis["changes"]["change_count"], 0)
        self.assertEqual(analysis["changes"]["failed_change_count"], 0)
        finding = next(
            item for item in analysis["findings"]
            if item["rule_id"] == "ACTIVITY_READ_FAILED"
        )
        self.assertEqual(finding["category"], "EVENT")

    def test_distinct_events_on_same_resource_have_distinct_fingerprints(self):
        report = self._report(insight_events=[
            {
                "event_id": "event-1",
                "level": "WARNING",
                "resource_id": "server-1",
                "resource_name": "web-1",
                "rule_name": "CPU high",
                "start_time": 1_780_000_000_000,
            },
            {
                "event_id": "event-2",
                "level": "WARNING",
                "resource_id": "server-1",
                "resource_name": "web-1",
                "rule_name": "Memory high",
                "start_time": 1_780_000_060_000,
            },
        ])

        analysis = analyze_report(report)
        fingerprints = {
            item["fingerprint"]
            for item in analysis["findings"]
            if item["category"] == "EVENT"
        }

        self.assertEqual(len(fingerprints), 2)

    @staticmethod
    def _cost_fact(
        *,
        start="2026-08-01",
        end=None,
        total_amount=120,
        **overrides,
    ):
        end = end or start
        return {
            "cost_type": "PERIOD_ESTIMATE",
            "status": "AVAILABLE",
            "total_amount": total_amount,
            "currency": "KRW",
            "amount_basis": "PRE_DISCOUNT_LIST_PRICE",
            "confidence": "VERIFIED_ESTIMATE",
            "includes_discount": False,
            "includes_vat": False,
            "period_start": start,
            "period_end": end,
            "coverage_start": start,
            "coverage_end": end,
            **overrides,
        }

    def test_cost_comparison_requires_matching_basis_and_confidence(self):
        fact = self._cost_fact()
        report = self._report(billing={"period_estimate": fact})
        baseline = self._report(billing={
            "period_estimate": {
                **fact,
                "total_amount": 100,
                "period_start": "2026-07-31",
                "period_end": "2026-07-31",
                "coverage_start": "2026-07-31",
                "coverage_end": "2026-07-31",
            }
        })

        compatible = analyze_report(report, baseline=baseline)
        incompatible = analyze_report(
            report,
            baseline=self._report(billing={
                "period_estimate": {
                    **fact,
                    "total_amount": 100,
                    "confidence": "PARTIAL",
                    "period_start": "2026-07-31",
                    "period_end": "2026-07-31",
                    "coverage_start": "2026-07-31",
                    "coverage_end": "2026-07-31",
                }
            }),
        )

        self.assertEqual(compatible["costs"]["comparison"]["status"], "AVAILABLE")
        self.assertEqual(compatible["costs"]["comparison"]["rate_change"], 20)
        comparison = incompatible["costs"]["comparison"]
        self.assertEqual(comparison["status"], "INCOMPATIBLE")
        self.assertEqual(comparison["current_amount"], 120)
        self.assertEqual(comparison["baseline_amount"], 100)
        self.assertEqual(comparison["current_period_start"], "2026-08-01")
        self.assertEqual(comparison["baseline_period_start"], "2026-07-31")
        self.assertIsNone(comparison["amount_change"])
        self.assertIsNone(comparison["rate_change"])
        self.assertEqual(comparison["incompatible_fields"], ["confidence"])
        self.assertIn("신뢰도", comparison["reason"])

    def test_daily_cost_ignores_monthly_fallback_when_baseline_day_is_missing(self):
        current = self._cost_fact(
            start="2026-08-15",
            total_amount=38385.48,
        )
        monthly = {
            **current,
            "cost_type": "MONTH_TO_DATE_ESTIMATE",
            "total_amount": 628740,
            "confidence": "PARTIAL",
            "period_start": "2026-08-01",
            "coverage_start": "2026-08-01",
        }
        analysis = analyze_report(
            self._report(billing={
                "period_estimate": current,
                "month_to_date_estimate": monthly,
            }),
            baseline=self._report(billing={
                "period_estimate": {
                    **current,
                    "status": "UNAVAILABLE",
                    "total_amount": 0,
                    "period_start": "2026-08-14",
                    "period_end": "2026-08-14",
                    "coverage_start": None,
                    "coverage_end": None,
                },
                "month_to_date_estimate": {
                    **monthly,
                    "total_amount": 544374.89,
                    "period_end": "2026-08-14",
                    "coverage_end": "2026-08-14",
                },
            }),
        )

        comparison = analysis["costs"]["comparison"]
        self.assertEqual(comparison["status"], "UNAVAILABLE")
        self.assertEqual(comparison["fact_name"], "period_estimate")
        self.assertEqual(comparison["current_amount"], 38385.48)
        self.assertEqual(comparison["current_period_start"], "2026-08-15")
        self.assertEqual(
            comparison["amount_basis"], "PRE_DISCOUNT_LIST_PRICE"
        )
        self.assertIsNone(comparison["baseline_amount"])
        self.assertIsNone(comparison["amount_change"])
        self.assertIsNone(comparison["rate_change"])

    def test_range_cost_uses_only_period_estimate(self):
        fact = self._cost_fact(start="2026-08-03", end="2026-08-04")
        fallback = {
            **fact,
            "cost_type": "MONTH_TO_DATE_ESTIMATE",
        }
        analysis = analyze_report(
            self._report(
                period={"period_type": "range"},
                billing={
                    "period_estimate": fact,
                    "month_to_date_estimate": fallback,
                },
            ),
            baseline=self._report(
                period={"period_type": "range"},
                billing={
                    "period_estimate": {**fact, "status": "UNAVAILABLE"},
                    "month_to_date_estimate": {
                        **fallback,
                        "total_amount": 100,
                        "period_start": "2026-08-01",
                        "period_end": "2026-08-02",
                        "coverage_start": "2026-08-01",
                        "coverage_end": "2026-08-02",
                    },
                },
            ),
        )

        comparison = analysis["costs"]["comparison"]
        self.assertEqual(comparison["status"], "UNAVAILABLE")
        self.assertEqual(comparison["fact_name"], "period_estimate")

    def test_cost_comparison_rejects_nonadjacent_equal_length_periods(self):
        fact = self._cost_fact(start="2026-08-03")
        analysis = analyze_report(
            self._report(billing={"period_estimate": fact}),
            baseline=self._report(billing={
                "period_estimate": {
                    **fact,
                    "total_amount": 100,
                    "period_start": "2026-08-01",
                    "period_end": "2026-08-01",
                    "coverage_start": "2026-08-01",
                    "coverage_end": "2026-08-01",
                }
            }),
        )

        comparison = analysis["costs"]["comparison"]
        self.assertEqual(comparison["status"], "INCOMPATIBLE")
        self.assertIn("comparison_period", comparison["incompatible_fields"])
        self.assertIn("비교 기간", comparison["reason"])

    def test_cost_threshold_and_distinct_period_are_required(self):
        fact = self._cost_fact()
        report = self._report(billing={"period_estimate": fact})
        distinct_baseline = self._report(billing={
            "period_estimate": {
                **fact,
                "total_amount": 100,
                "period_start": "2026-07-31",
                "period_end": "2026-07-31",
                "coverage_start": "2026-07-31",
                "coverage_end": "2026-07-31",
            }
        })

        high_threshold = analyze_report(
            report,
            baseline=distinct_baseline,
            policy={"thresholds": {"cost_increase_warning_percent": 50}},
        )
        same_period = analyze_report(
            report,
            baseline=self._report(billing={
                "period_estimate": {**fact, "total_amount": 100}
            }),
        )

        self.assertFalse(any(
            item["rule_id"] == "COST_INCREASE_BASELINE"
            for item in high_threshold["findings"]
        ))
        self.assertEqual(
            same_period["costs"]["comparison"]["status"],
            "INCOMPATIBLE",
        )

    def test_cost_comparison_rejects_different_collection_coverage(self):
        current = self._cost_fact(
            start="2026-08-01",
            end="2026-08-10",
            confidence="PARTIAL",
        )
        previous = {
            **current,
            "total_amount": 100,
            "period_start": "2026-07-22",
            "period_end": "2026-07-31",
            "coverage_start": "2026-07-22",
            "coverage_end": "2026-07-30",
        }

        analysis = analyze_report(
            self._report(
                period={"period_type": "range"},
                billing={"period_estimate": current},
            ),
            baseline=self._report(
                period={"period_type": "range"},
                billing={"period_estimate": previous},
            ),
        )

        comparison = analysis["costs"]["comparison"]
        self.assertEqual(comparison["status"], "INCOMPATIBLE")
        self.assertIn("coverage", comparison["incompatible_fields"])
        self.assertNotIn("comparison_period", comparison["incompatible_fields"])

    def test_consecutive_monthly_periods_remain_comparable(self):
        current = self._cost_fact(
            start="2026-07-01",
            end="2026-07-31",
            cost_type="CONFIRMED",
            amount_basis="CURRENT_MONTH_INVOICE_TOTAL",
            confidence="CONFIRMED",
            includes_discount=True,
            includes_vat=True,
        )
        previous = {
            **current,
            "total_amount": 100,
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "coverage_start": "2026-06-01",
            "coverage_end": "2026-06-30",
        }

        analysis = analyze_report(
            self._report(
                period={"period_type": "prev_month"},
                billing={"invoice_summary": current},
            ),
            baseline=self._report(
                period={"period_type": "prev_month"},
                billing={"invoice_summary": previous},
            ),
        )

        self.assertEqual(analysis["period_type"], "MONTHLY")
        self.assertEqual(
            analysis["costs"]["comparison"]["status"],
            "AVAILABLE",
        )

        current["period_end"] = current["coverage_end"] = "2026-07-15"
        previous["period_end"] = previous["coverage_end"] = "2026-06-15"
        partial = analyze_report(
            self._report(
                period={"period_type": "prev_month"},
                billing={"invoice_summary": current},
            ),
            baseline=self._report(
                period={"period_type": "prev_month"},
                billing={"invoice_summary": previous},
            ),
        )
        self.assertEqual(
            partial["costs"]["comparison"]["status"],
            "AVAILABLE",
        )

    def test_wms_and_security_use_only_explicit_evidence(self):
        report = self._report(
            service_availability={
                "status": "COLLECTED",
                "source": "NCP_WMS",
                "scenarios": [{
                    "scenario_id": "wms-1",
                    "name": "homepage",
                    "availability_percent": 94,
                    "total_count": 100,
                    "success_count": 94,
                    "error_count": 6,
                }],
            },
            security_monitoring={
                "status": "COLLECTED",
                "scope": "VPC",
                "service_statuses": {"WAF": "COLLECTED"},
                "events": [{
                    "event_id": "security-1",
                    "service": "WAF",
                    "event_name": "SQL Injection",
                    "detected_at": 1_000,
                    "vpc_name": "prod-vpc",
                }],
            },
            dataset_statuses=[
                {"key": "service_availability", "status": "COLLECTED", "record_count": 1},
                {"key": "security_events", "status": "COLLECTED", "record_count": 1},
            ],
        )

        analysis = analyze_report(report)
        rule_ids = [item["rule_id"] for item in analysis["findings"]]

        self.assertIn("WMS_AVAILABILITY_BELOW_THRESHOLD", rule_ids)
        self.assertIn("SECURITY_MONITORING_EVENT_DETECTED", rule_ids)
        self.assertEqual(analysis["security"]["event_count"], 1)

    def test_iso_security_times_sort_and_event_time_fallback(self):
        analysis = analyze_report(self._report(
            insight_events=[{
                "event_id": "event-1",
                "level": "WARNING",
                "start_time": None,
                "event_time": 1_720_000_000_000,
                "end_time": 1_720_000_001_000,
            }],
            security_monitoring={
                "status": "COLLECTED",
                "events": [
                    {
                        "event_id": "older",
                        "detected_at": "2026-08-14T01:00:00+09:00",
                    },
                    {
                        "event_id": "newer",
                        "detected_at": "2026-08-14T02:00:00+09:00",
                    },
                ],
            },
        ))

        self.assertEqual(
            [item["event_id"] for item in analysis["security"]["items"]],
            ["newer", "older"],
        )
        event = analysis["events"]["items"][0]
        self.assertEqual(event["start_time"], 1_720_000_000_000)
        self.assertEqual(event["duration_seconds"], 1)

    def test_configuration_only_fields_do_not_create_operational_findings(self):
        report = self._report(
            report_options={"sections": ["infrastructure_inventory"]},
            infrastructure=[
                {
                    "category": "BLOCK_STORAGE",
                    "resource_id": "disk-1",
                    "resource_name": "data-disk",
                    "details": {"encrypted": False},
                },
                {
                    "category": "KUBERNETES",
                    "resource_id": "cluster-1",
                    "resource_name": "prod-cluster",
                    "details": {"termination_protection": False},
                },
            ],
            dataset_statuses=[{
                "key": "infrastructure",
                "status": "COLLECTED",
                "record_count": 2,
            }],
        )

        analysis = analyze_report(report)
        rule_ids = {item["rule_id"] for item in analysis["findings"]}

        self.assertNotIn("BLOCK_STORAGE_ENCRYPTION_DISABLED", rule_ids)
        self.assertNotIn(
            "KUBERNETES_TERMINATION_PROTECTION_DISABLED",
            rule_ids,
        )

    def test_source_states_distinguish_observed_calculated_and_missing_data(self):
        report = self._report(
            server_metrics=[{
                "server_id": "server-1",
                "server_name": "web-1",
                "metric_interval": "Min1",
                "raw_metrics": {
                    "used_rto": {
                        "avg": [{"raw": {"dps": [[1_000, 95]]}}]
                    }
                },
            }],
            insight_events=[{
                "event_id": "event-1",
                "level": "WARNING",
                "resource_id": "server-1",
                "start_time": 1_000,
            }],
            activity_events={"server-1": [{
                "event_id": "change-1",
                "event_time": 1_000,
                "result": "SUCCESS",
            }]},
            billing={
                "invoice_summary": {
                    "cost_type": "CONFIRMED",
                    "status": "AVAILABLE",
                    "total_amount": 100,
                },
                "period_estimate": {
                    "cost_type": "PERIOD_ESTIMATE",
                    "status": "AVAILABLE",
                    "total_amount": 90,
                },
            },
            service_availability={
                "status": "COLLECTED",
                "scenarios": [{
                    "scenario_id": "wms-1",
                    "name": "homepage",
                    "availability_percent": 100,
                    "total_count": 1,
                    "success_count": 1,
                }],
            },
            security_monitoring={
                "status": "COLLECTED",
                "events": [{
                    "event_id": "security-1",
                    "service": "WAF",
                    "detected_at": 1_000,
                }],
            },
            dataset_statuses=[
                {
                    "key": "service_availability",
                    "status": "COLLECTED",
                    "record_count": 1,
                },
                {
                    "key": "security_events",
                    "status": "COLLECTED",
                    "record_count": 1,
                },
            ],
        )

        analysis = analyze_report(report)
        cost_facts = {
            item["name"]: item for item in analysis["costs"]["facts"]
        }

        self.assertEqual(analysis["source_state"], "CALCULATED")
        self.assertEqual(
            analysis["events"]["items"][0]["source_state"],
            "OBSERVED",
        )
        self.assertEqual(analysis["events"]["source_state"], "CALCULATED")
        self.assertEqual(
            analysis["changes"]["items"][0]["source_state"],
            "OBSERVED",
        )
        self.assertEqual(
            analysis["availability"]["items"][0]["source_state"],
            "OBSERVED",
        )
        self.assertEqual(
            analysis["security"]["items"][0]["source_state"],
            "OBSERVED",
        )
        self.assertEqual(
            analysis["metrics"]["summaries"][0]["source_state"],
            "CALCULATED",
        )
        self.assertTrue(all(
            item["source_state"] == "CALCULATED"
            for item in analysis["findings"]
        ))
        self.assertEqual(
            cost_facts["invoice_summary"]["source_state"],
            "OBSERVED",
        )
        self.assertEqual(
            cost_facts["period_estimate"]["source_state"],
            "CALCULATED",
        )

    def test_source_state_distinguishes_collection_failure_from_unavailable(self):
        analysis = analyze_report(self._report(dataset_statuses=[
            {"key": "security_events", "status": "FAILED"},
            {"key": "service_availability", "status": "NOT_REQUESTED"},
        ]))

        self.assertEqual(
            self._dataset(analysis, "security_events")["source_state"],
            "COLLECTION_FAILED",
        )
        self.assertEqual(
            analysis["security"]["source_state"],
            "COLLECTION_FAILED",
        )
        self.assertEqual(
            self._dataset(analysis, "service_availability")["source_state"],
            "UNAVAILABLE",
        )

    def test_resource_changes_compare_adjacent_complete_months(self):
        categories = ("SERVER", "BLOCK_STORAGE", "NAS")
        baseline = self._monthly_inventory_report(
            "2026-07-01",
            "2026-07-31",
            [
                self._resource(
                    "SERVER",
                    "server-1",
                    name="web-1",
                    details={"cpu_count": 2, "memory_gb": 8},
                ),
                self._resource(
                    "BLOCK_STORAGE",
                    "storage-old",
                    details={"size_gb": 100},
                ),
            ],
            categories=categories,
        )
        current = self._monthly_inventory_report(
            "2026-08-01",
            "2026-08-31",
            [
                self._resource(
                    "SERVER",
                    "server-1",
                    name="web-1",
                    details={"cpu_count": 4, "memory_gb": 8.0},
                ),
                self._resource(
                    "NAS",
                    "nas-new",
                    details={"size_gb": 500},
                ),
            ],
            categories=categories,
        )

        analysis = analyze_report(current, baseline=baseline)
        changes = analysis["resource_changes"]

        self.assertEqual(changes["status"], "AVAILABLE")
        self.assertEqual(changes["created_count"], 1)
        self.assertEqual(changes["removed_count"], 1)
        self.assertEqual(changes["spec_changed_count"], 1)
        self.assertEqual(
            [
                (item["change_type"], item["resource_id"])
                for item in changes["items"]
            ],
            [
                ("CREATED", "nas-new"),
                ("REMOVED", "storage-old"),
                ("SPEC_CHANGED", "server-1"),
            ],
        )
        self.assertEqual(
            changes["items"][2]["changed_fields"],
            [{
                "field": "cpu_count",
                "label": "vCPU",
                "before": 2,
                "after": 4,
            }],
        )
        self.assertFalse(any(
            finding.get("category") == "RESOURCE_CHANGE"
            for finding in analysis["findings"]
        ))

    def test_resource_change_identity_and_values_are_stable(self):
        categories = ("SERVER", "LOAD_BALANCER")
        baseline = self._monthly_inventory_report(
            "2026-07-01",
            "2026-07-31",
            [
                self._resource(
                    "SERVER",
                    "shared-id",
                    platform="VPC",
                    details={"cpu_count": 2},
                ),
                self._resource(
                    "SERVER",
                    "shared-id",
                    platform="CLASSIC",
                    details={"cpu_count": 4},
                ),
                self._resource(
                    "LOAD_BALANCER",
                    "lb-1",
                    details={"network_type": "PUBLIC"},
                ),
            ],
            categories=categories,
        )
        current = self._monthly_inventory_report(
            "2026-08-01",
            "2026-08-31",
            [
                self._resource(
                    "SERVER",
                    "shared-id",
                    platform="VPC",
                    details={"cpu_count": 3},
                ),
                self._resource(
                    "SERVER",
                    "shared-id",
                    platform="CLASSIC",
                    details={"cpu_count": "4"},
                ),
                self._resource(
                    "LOAD_BALANCER",
                    "lb-1",
                    details={"network_type": "public"},
                ),
            ],
            categories=categories,
        )

        changes = analyze_report(current, baseline=baseline)[
            "resource_changes"
        ]

        self.assertEqual(changes["spec_changed_count"], 1)
        self.assertEqual(len(changes["items"]), 1)
        self.assertEqual(changes["items"][0]["platform"], "VPC")

    def test_resource_changes_require_exact_kst_month_boundaries(self):
        baseline = self._monthly_inventory_report(
            "2026-07-01",
            "2026-07-31",
            [self._resource("SERVER", "server-1")],
            categories=("SERVER",),
        )
        current = self._monthly_inventory_report(
            "2026-08-01",
            "2026-08-31",
            [self._resource("SERVER", "server-1")],
            categories=("SERVER",),
        )
        invalid_periods = (
            {
                **current["period"],
                "start_dt": "2026-08-01 12:00:00",
            },
            {
                **current["period"],
                "end_dt": "2026-08-31 12:00:00",
            },
            {
                **current["period"],
                "is_full_month": False,
            },
        )

        for period in invalid_periods:
            with self.subTest(period=period):
                candidate = deepcopy(current)
                candidate["period"] = period
                changes = analyze_report(candidate, baseline=baseline)[
                    "resource_changes"
                ]

                self.assertEqual(changes["status"], "NOT_APPLICABLE")
                self.assertEqual(
                    changes["reason_code"],
                    "MONTHLY_REPORT_REQUIRED",
                )

        utc_period = deepcopy(current)
        utc_period["period"].update({
            "start_dt": "2026-07-31T15:00:00Z",
            "end_dt": "2026-08-31T14:59:59Z",
            "is_full_month": True,
        })
        changes = analyze_report(utc_period, baseline=baseline)[
            "resource_changes"
        ]
        self.assertEqual(changes["status"], "AVAILABLE")

    def test_resource_changes_fail_closed_for_incompatible_snapshots(self):
        current = self._monthly_inventory_report(
            "2026-08-01",
            "2026-08-31",
            [self._resource("SERVER", "server-1")],
            categories=("SERVER",),
        )
        good_baseline = self._monthly_inventory_report(
            "2026-07-01",
            "2026-07-31",
            [self._resource("SERVER", "server-1")],
            categories=("SERVER",),
        )
        nonadjacent = self._monthly_inventory_report(
            "2026-06-01",
            "2026-06-30",
            [self._resource("SERVER", "server-1")],
            categories=("SERVER",),
        )
        nonmonthly = self._report(schema_version="1.5")
        schema_mismatch = deepcopy(good_baseline)
        schema_mismatch["schema_version"] = "1.4"
        scope_mismatch = deepcopy(good_baseline)
        scope_mismatch["report_options"]["resource_categories"] = [
            "SERVER",
            "NAS",
        ]
        partial = deepcopy(good_baseline)
        partial["collection_metadata"]["infrastructure"].update({
            "inventory_completeness": "PARTIAL",
            "collection_issue_count": 1,
        })

        cases = (
            (None, "UNAVAILABLE", "BASELINE_UNAVAILABLE"),
            (nonmonthly, "UNAVAILABLE", "BASELINE_NOT_MONTHLY"),
            (nonadjacent, "UNAVAILABLE", "BASELINE_NOT_ADJACENT"),
            (schema_mismatch, "UNAVAILABLE", "SCHEMA_MISMATCH"),
            (scope_mismatch, "UNAVAILABLE", "RESOURCE_SCOPE_MISMATCH"),
            (partial, "PARTIAL", "SNAPSHOT_INCOMPLETE"),
        )
        for baseline, status, reason_code in cases:
            with self.subTest(reason_code=reason_code):
                changes = analyze_report(current, baseline=baseline)[
                    "resource_changes"
                ]
                self.assertEqual(changes["status"], status)
                self.assertEqual(changes["reason_code"], reason_code)
                self.assertIsNone(changes["created_count"])
                self.assertIsNone(changes["removed_count"])
                self.assertIsNone(changes["spec_changed_count"])
                self.assertEqual(changes["items"], [])

    def test_resource_changes_reject_malformed_inventory_and_details(self):
        baseline = self._monthly_inventory_report(
            "2026-07-01",
            "2026-07-31",
            [self._resource(
                "SERVER",
                "server-1",
                details={"cpu_count": 2},
            )],
            categories=("SERVER",),
        )
        malformed_details = self._resource("SERVER", "server-1")
        malformed_details["details"] = "corrupt"
        missing_platform = self._resource("SERVER", "server-1")
        missing_platform["platform"] = ""
        malformed_inventory = (
            "corrupt",
            ["corrupt"],
            [{
                "resource_id": "server-1",
                "platform": "VPC",
                "details": {},
            }],
            [malformed_details],
            [missing_platform],
        )

        for inventory in malformed_inventory:
            with self.subTest(inventory=inventory):
                current = self._monthly_inventory_report(
                    "2026-08-01",
                    "2026-08-31",
                    inventory,
                    categories=("SERVER",),
                )
                changes = analyze_report(current, baseline=baseline)[
                    "resource_changes"
                ]

                self.assertEqual(changes["status"], "PARTIAL")
                self.assertEqual(
                    changes["reason_code"],
                    "MALFORMED_SNAPSHOT",
                )
                self.assertIsNone(changes["created_count"])
                self.assertIsNone(changes["removed_count"])
                self.assertIsNone(changes["spec_changed_count"])
                self.assertEqual(changes["items"], [])

    def test_resource_changes_require_actual_collection_scope_coverage(self):
        categories = ("SERVER", "NAS")
        baseline = self._monthly_inventory_report(
            "2026-07-01",
            "2026-07-31",
            [
                self._resource("SERVER", "server-1"),
                self._resource("NAS", "nas-1"),
            ],
            categories=categories,
        )
        current = self._monthly_inventory_report(
            "2026-08-01",
            "2026-08-31",
            [self._resource("SERVER", "server-1")],
            categories=categories,
        )
        current["collection_metadata"]["infrastructure"].update({
            "inventory_completeness": "COMPLETE_FOR_SNAPSHOT_SCOPE",
            "collected_categories": ["SERVER"],
        })
        requested_scope_only = deepcopy(current)
        metadata = requested_scope_only["collection_metadata"][
            "infrastructure"
        ]
        metadata.pop("collected_categories")
        metadata["resource_categories"] = list(categories)

        for candidate in (current, requested_scope_only):
            with self.subTest(metadata=candidate["collection_metadata"]):
                changes = analyze_report(candidate, baseline=baseline)[
                    "resource_changes"
                ]

                self.assertEqual(changes["status"], "PARTIAL")
                self.assertEqual(
                    changes["reason_code"],
                    "SNAPSHOT_INCOMPLETE",
                )
                self.assertIsNone(changes["removed_count"])
                self.assertEqual(changes["items"], [])

    def test_resource_changes_require_explicit_valid_raw_options(self):
        baseline = self._monthly_inventory_report(
            "2026-07-01",
            "2026-07-31",
            [self._resource("SERVER", "server-1")],
            categories=("SERVER",),
        )
        current = self._monthly_inventory_report(
            "2026-08-01",
            "2026-08-31",
            [self._resource("SERVER", "server-1")],
            categories=("SERVER",),
        )
        invalid_options = (
            None,
            "corrupt",
            {
                "sections": ["infrastructure_inventory"],
                "resource_categories": ["SERVER"],
                "monitoring_categories": [],
            },
            {
                **current["report_options"],
                "schema_version": "0",
            },
            {
                **current["report_options"],
                "resource_categories": ["SERVER", "UNKNOWN_CATEGORY"],
            },
        )

        for options in invalid_options:
            with self.subTest(options=options):
                candidate = deepcopy(current)
                if options is None:
                    candidate.pop("report_options")
                else:
                    candidate["report_options"] = options
                changes = analyze_report(candidate, baseline=baseline)[
                    "resource_changes"
                ]

                self.assertEqual(changes["status"], "UNAVAILABLE")
                self.assertEqual(
                    changes["reason_code"],
                    "OPTIONS_UNAVAILABLE",
                )
                self.assertIsNone(changes["created_count"])
                self.assertEqual(changes["items"], [])

    def test_resource_change_contract_separates_lifecycle_and_spec_scope(self):
        categories = ("SERVER", "OBJECT_STORAGE", "GLOBAL_DNS")
        baseline = self._monthly_inventory_report(
            "2026-07-01",
            "2026-07-31",
            [
                self._resource(
                    "OBJECT_STORAGE",
                    "bucket-same",
                    details={"versioning": False},
                ),
                self._resource("OBJECT_STORAGE", "bucket-old"),
                self._resource(
                    "GLOBAL_DNS",
                    "domain-1",
                    platform="GLOBAL",
                    details={"dnssec_enabled": False},
                ),
                self._resource(
                    "GLOBAL_DNS",
                    "domain-2",
                    platform="GLOBAL",
                    details={"dnssec_enabled": False},
                ),
            ],
            categories=categories,
        )
        current = self._monthly_inventory_report(
            "2026-08-01",
            "2026-08-31",
            [
                self._resource(
                    "OBJECT_STORAGE",
                    "bucket-same",
                    details={"versioning": True},
                ),
                self._resource("OBJECT_STORAGE", "bucket-new"),
                self._resource(
                    "GLOBAL_DNS",
                    "domain-1",
                    platform="GLOBAL",
                    details={"dnssec_enabled": True},
                ),
                self._resource(
                    "GLOBAL_DNS",
                    "domain-2",
                    platform="GLOBAL",
                    details={"dnssec_enabled": "N"},
                ),
            ],
            categories=categories,
        )

        changes = analyze_report(current, baseline=baseline)[
            "resource_changes"
        ]

        self.assertEqual(changes["status"], "AVAILABLE")
        self.assertEqual(changes["created_count"], 1)
        self.assertEqual(changes["removed_count"], 1)
        self.assertEqual(changes["spec_changed_count"], 1)
        self.assertEqual(
            changes["lifecycle_compared_categories"],
            ["GLOBAL_DNS", "OBJECT_STORAGE", "SERVER"],
        )
        self.assertEqual(
            changes["spec_compared_categories"],
            ["GLOBAL_DNS", "SERVER"],
        )
        self.assertEqual(
            changes["lifecycle_only_categories"],
            ["OBJECT_STORAGE"],
        )
        self.assertEqual(
            [
                (item["change_type"], item["resource_id"])
                for item in changes["items"]
            ],
            [
                ("CREATED", "bucket-new"),
                ("REMOVED", "bucket-old"),
                ("SPEC_CHANGED", "domain-1"),
            ],
        )

    def test_resource_changes_exclude_network_configuration_and_duplicates(self):
        categories = ("SERVER", "ROUTE_TABLE")
        baseline = self._monthly_inventory_report(
            "2026-07-01",
            "2026-07-31",
            [self._resource(
                "ROUTE_TABLE",
                "route-1",
                details={"route_count": 1},
            )],
            categories=categories,
        )
        current = self._monthly_inventory_report(
            "2026-08-01",
            "2026-08-31",
            [self._resource(
                "ROUTE_TABLE",
                "route-2",
                details={"route_count": 10},
            )],
            categories=categories,
        )

        changes = analyze_report(current, baseline=baseline)[
            "resource_changes"
        ]

        self.assertEqual(changes["status"], "AVAILABLE")
        self.assertEqual(changes["created_count"], 0)
        self.assertEqual(changes["removed_count"], 0)
        self.assertEqual(changes["spec_changed_count"], 0)

        duplicate_baseline = deepcopy(baseline)
        duplicate_baseline["infrastructure"] = [
            self._resource("SERVER", "server-1"),
            self._resource("SERVER", "server-1"),
        ]
        changes = analyze_report(current, baseline=duplicate_baseline)[
            "resource_changes"
        ]
        self.assertEqual(changes["status"], "PARTIAL")
        self.assertEqual(
            changes["reason_code"],
            "RESOURCE_IDENTITY_INCOMPLETE",
        )

    def test_resource_changes_are_not_applicable_to_daily_reports(self):
        changes = analyze_report(self._report())["resource_changes"]

        self.assertEqual(changes["status"], "NOT_APPLICABLE")
        self.assertEqual(changes["reason_code"], "MONTHLY_REPORT_REQUIRED")
        self.assertIsNone(changes["created_count"])

    def test_inferred_source_requires_explicit_historical_confidence(self):
        self.assertEqual(
            historical_source_state("INFERRED_FROM_CREATE_TIME"),
            "INFERRED",
        )
        self.assertEqual(historical_source_state("UNKNOWN"), "UNAVAILABLE")
        self.assertEqual(historical_source_state(None), "OBSERVED")

    @staticmethod
    def _dataset(analysis, key):
        return next(
            item for item in analysis["data_quality"]["datasets"]
            if item["key"] == key
        )


if __name__ == "__main__":
    unittest.main()

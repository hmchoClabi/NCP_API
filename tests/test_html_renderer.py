import tempfile
import unittest
from pathlib import Path

from app.renderers import HtmlReportRenderer
from app.report_models import ReportResult


class HtmlReportRendererTests(unittest.TestCase):
    def _sample_report(self):
        return ReportResult(
            period={
                "period_type": "month",
                "start_dt": "2026-06-01 00:00:00",
                "end_dt": "2026-06-30 23:59:59",
                "file_suffix": "20260601_20260630",
            },
            servers=[{"server_id": "server-1"}],
            server_metrics=[
                {
                    "server_name": "web-01",
                    "metric_interval": "Hour2",
                    "cpu_min": 10,
                    "cpu_avg": 20,
                    "cpu_max": 30,
                    "mem_min": 40,
                    "mem_avg": 50,
                    "mem_max": 60,
                    "os_fs_details": [
                        {"mount": "/", "min": 20, "avg": 30, "max": 40}
                    ],
                    "data_fs_details": [
                        {
                            "mount": "/data",
                            "min": 50,
                            "avg": 60,
                            "max": 70,
                        }
                    ],
                    "raw_metrics": {
                        "must": "not leak",
                        "used_rto": {
                            "avg": [
                                {
                                    "dimensions": {"instanceNo": "one"},
                                    "raw": {
                                        "dps": [
                                            [1781485200000, 10],
                                            [1781492400000, 20],
                                        ]
                                    },
                                }
                            ]
                        },
                        "mem_usert": {
                            "avg": [
                                {
                                    "dimensions": {"instanceNo": "one"},
                                    "raw": {
                                        "dps": [
                                            [1781485200000, 40],
                                            [1781492400000, 50],
                                        ]
                                    },
                                }
                            ]
                        },
                        "fs_usert": {
                            "avg": [
                                {
                                    "dimensions": {
                                        "instanceNo": "one",
                                        "mnt_nm": "/",
                                    },
                                    "raw": {
                                        "dps": [
                                            [1781485200000, 30],
                                            [1781492400000, 35],
                                        ]
                                    },
                                },
                                {
                                    "dimensions": {
                                        "instanceNo": "one",
                                        "mnt_nm": "/data",
                                    },
                                    "raw": {
                                        "dps": [
                                            [1781485200000, 60],
                                            [1781492400000, 65],
                                        ]
                                    },
                                },
                            ]
                        },
                    },
                }
            ],
            insight_events=[
                {
                    "event_time": "2026-06-15 12:00:00",
                    "severity": "WARNING",
                    "resource_name": "<server>",
                    "event_type": "CPU",
                    "message": "<script>alert(1)</script>",
                }
            ],
            activity_events={
                "server-1": [
                    {
                        "event_id": "activity-1",
                        "event_time": 1781508312345,
                        "event_time_kst": (
                            "2026-06-15 13:45:12.345 KST"
                        ),
                        "user_name": "customer-admin",
                        "user_type": "Main",
                        "product_display_name": "Server",
                        "resource_type": "Server",
                        "resource_id": "server-123",
                        "resource_name": "web-01",
                        "action_name": "Reboot",
                        "result": "SUCCESS",
                        "source_ip": "127.0.0.1",
                        "product_data": {
                            "userAgent": "Mozilla/5.0",
                            "description": "<target details>",
                            "accessToken": "must-not-be-rendered",
                        },
                    }
                ]
            },
            billing={
                "summary": {"confirmed_total_amount": 12345},
                "service_summary": [
                    {
                        "service_name": "Server",
                        "amount": 12345,
                        "row_count": 1,
                    }
                ],
                "network_usage_summary": [],
                "usage_summary": [],
            },
            collection_errors=[],
        )

    def test_render_produces_standalone_responsive_printable_html(self):
        html = HtmlReportRenderer().render(self._sample_report())

        self.assertIn("<!doctype html>", html)
        self.assertIn('name="viewport"', html)
        self.assertIn("@media print", html)
        self.assertIn("NCP 이용 보고서", html)
        self.assertIn("12,345 <small>원</small>", html)
        self.assertIn("Cloud Activity Tracer", html)
        self.assertIn("보고 기간 메트릭 변화", html)
        self.assertIn("KST 2시간 AVG", html)
        self.assertIn(">06-01</text>", html)
        self.assertIn(">06-30</text>", html)
        self.assertIn("CPU 그룹", html)
        self.assertIn("MEM 그룹", html)
        self.assertIn("루트 디스크 그룹", html)
        self.assertIn("DATA 디스크 그룹", html)
        self.assertEqual(html.count("<polyline"), 4)
        self.assertIn("web-01 · /data", html)
        cpu_chart = html.split("<h3>CPU 그룹</h3>", 1)[1].split(
            "</article>",
            1,
        )[0]
        self.assertIn(">25%</text>", cpu_chart)
        self.assertNotIn(">100%</text>", cpu_chart)
        self.assertIn("발생 시각 (KST)", html)
        self.assertIn("2026-06-15 13:45:12.345 KST", html)
        self.assertIn("수행 계정", html)
        self.assertIn("customer-admin (Main)", html)
        self.assertIn("대상 객체", html)
        self.assertIn("Server: web-01", html)
        self.assertIn("상세 2개", html)
        self.assertIn("&lt;target details&gt;", html)
        self.assertNotIn("must-not-be-rendered", html)

    def test_infrastructure_inventory_renders_only_allowed_categories(self):
        report = self._sample_report()
        report.infrastructure = [
            {
                "category": category,
                "category_label": label,
                "service_name": label,
                "resource_type": f"{category}Resource",
                "resource_id": f"resource-{index}",
                "resource_name": f"allowed-{index}",
                "status": "RUN",
                "region_code": "KR",
                "zone_code": "KR-1",
                "create_time": 0 if index == 1 else None,
                "details": {},
            }
            for index, (category, label) in enumerate(
                (
                    ("SERVER", "서버"),
                    ("LOAD_BALANCER", "Load Balancer"),
                    ("BLOCK_STORAGE", "Block Storage"),
                    ("OBJECT_STORAGE", "Object Storage"),
                    ("NAS", "NAS"),
                    ("CLOUD_DB", "Cloud DB"),
                    ("CDN", "CDN"),
                    ("KUBERNETES", "Kubernetes"),
                ),
                start=1,
            )
        ] + [
            {
                "category": "ALARM",
                "category_label": "Alarm",
                "resource_name": "excluded-alarm-instance",
            },
            {
                "category": "IAM",
                "category_label": "IAM",
                "resource_name": "excluded-sub-account",
            },
        ]

        html = HtmlReportRenderer().render(report)
        inventory = html.split("<h2>대표 인프라 현황</h2>", 1)[1].split(
            "</section>",
            1,
        )[0]

        for index in range(1, 9):
            with self.subTest(index=index):
                self.assertIn(f"allowed-{index}", inventory)
        self.assertIn("8건", inventory)
        self.assertIn("1970-01-01 09:00 KST", inventory)
        self.assertNotIn("excluded-alarm-instance", html)
        self.assertNotIn("excluded-sub-account", html)

        details = HtmlReportRenderer()._infrastructure_details_text({
            "engine": "POSTGRESQL",
            "server_count": 2,
            "cpu_count_total": 8,
            "memory_gb_total": 32,
            "data_storage_gb_total": 500,
        })
        self.assertIn("DB 서버: 2개", details)
        self.assertIn("총 메모리: 32 GB", details)
        self.assertIn("데이터 용량: 500 GB", details)

    def test_infrastructure_charts_preserve_metric_units(self):
        report = self._sample_report()
        report.infrastructure = [
            {
                "category": "LOAD_BALANCER",
                "resource_name": "lb-1",
            },
            {
                "category": "CLOUD_DB",
                "resource_name": "mysql-1",
            },
            {
                "category": "KUBERNETES",
                "resource_name": "cluster-1",
            },
            {
                "category": "NAS",
                "resource_name": "nas-1",
            },
        ]
        report.infrastructure_metrics = [
            {
                "category": "LOAD_BALANCER",
                "product_name": "System/Load Balancer(VPC)",
                "metric": "traffic_in_byte",
                "metric_label": "수신 트래픽",
                "unit": "bytes/sec",
                "interval": "Min5",
                "aggregation": "AVG",
                "series": [{
                    "resource_id": "lb-1",
                    "resource_name": "lb-1",
                    "dimensions": {},
                    "points": [
                        [1780272000000, 1048576],
                        [1780272300000, 2097152],
                    ],
                }],
            },
            {
                "category": "CLOUD_DB",
                "product_name": "System/Cloud DB for MySQL(VPC)",
                "metric": "cpu_used_rto",
                "metric_label": "CPU 사용률",
                "unit": "%",
                "interval": "Min5",
                "aggregation": "AVG",
                "series": [{
                    "resource_id": "mysql-1",
                    "resource_name": "mysql-1",
                    "dimensions": {},
                    "points": [
                        [1780272000000, 25],
                        [1780272300000, 50],
                    ],
                }],
            },
            {
                "category": "KUBERNETES",
                "product_name": "System/Ncloud Kubernetes Service",
                "metric": "node_ready_count",
                "metric_label": "Ready 노드",
                "unit": "count",
                "interval": "Min5",
                "aggregation": "AVG",
                "series": [{
                    "resource_id": "cluster-1",
                    "resource_name": "cluster-1",
                    "dimensions": {},
                    "points": [
                        [1780272000000, 2],
                        [1780272300000, 3],
                    ],
                }],
            },
            {
                "category": "NAS",
                "product_name": "System/NAS(VPC)",
                "metric": "volume_used_ratio",
                "metric_label": "볼륨 사용률",
                "unit": "%",
                "interval": "Min5",
                "aggregation": "AVG",
                "series": [{
                    "resource_id": "nas-1",
                    "resource_name": "nas-1",
                    "dimensions": {},
                    "points": [
                        [1780272000000, 40],
                        [1780272300000, 45],
                    ],
                }],
            },
        ]

        html = HtmlReportRenderer().render(report)
        monitoring = html.split("<h2>주요 인프라 모니터링</h2>", 1)[1]
        lb_chart = monitoring.split(
            "<h3>Load Balancer · 수신 트래픽</h3>",
            1,
        )[1].split("</article>", 1)[0]
        cdb_chart = monitoring.split(
            "<h3>Cloud DB · CPU 사용률</h3>",
            1,
        )[1].split("</article>", 1)[0]
        nks_chart = monitoring.split(
            "<h3>Kubernetes · Ready 노드</h3>",
            1,
        )[1].split("</article>", 1)[0]
        nas_chart = monitoring.split(
            "<h3>NAS · 볼륨 사용률</h3>",
            1,
        )[1].split("</article>", 1)[0]

        self.assertIn("1.0 MiB/s", lb_chart)
        self.assertNotIn("%", lb_chart)
        self.assertIn("25%", cdb_chart)
        self.assertIn("50%", cdb_chart)
        self.assertIn("cluster-1", nks_chart)
        self.assertNotIn("2%", nks_chart)
        self.assertNotIn("3%", nks_chart)
        self.assertIn("40%", nas_chart)
        self.assertIn("45%", nas_chart)

    def test_insight_event_detail_fields_are_rendered_and_escaped(self):
        report = self._sample_report()
        report.insight_events = [
            {
                "event_id": "event-1",
                "start_time": 1781508312345,
                "start_time_kst": "2026-06-15 13:45:12.345 KST",
                "level": "CRITICAL",
                "resource_name": "web-01",
                "rule_name": "CPU high",
                "metric": "cpu_used_rto",
                "operator_symbol": ">=",
                "criteria": "80",
                "detect_value": "91.5",
                "unit": "%",
                "calc": "AVG",
                "interval": "Min5",
                "dimension": {"instanceNo": "<server-1>"},
            }
        ]

        html = HtmlReportRenderer().render(report)

        self.assertIn("2026-06-15 13:45:12.345 KST", html)
        self.assertIn("cpu_used_rto &gt;= 80 / 감지 91.5%", html)
        self.assertIn("집계 함수", html)
        self.assertIn("Min5", html)
        self.assertIn("&lt;server-1&gt;", html)

    def test_partial_period_uses_estimated_cost_instead_of_zero_demand(self):
        report = self._sample_report()
        report.period["is_closed_month"] = False
        report.billing = {
            "summary": {
                "confirmed_total_amount": 0,
                "expected_total_amount": 4321,
            },
            "service_summary": [
                {"service_name": "Server", "amount": 0, "row_count": 1}
            ],
            "expected_by_service": [
                {
                    "service_name": "Server",
                    "expected_amount": 4321,
                    "row_count": 2,
                }
            ],
            "network_usage_summary": [],
            "usage_summary": [],
        }

        html = HtmlReportRenderer().render(report)

        self.assertIn("서비스별 예상 비용", html)
        self.assertIn("4,321", html)
        self.assertIn("미확정 예상 비용", html)

    def test_month_to_date_ncp_cost_replaces_duplicate_period_card(self):
        report = self._sample_report()
        report.period["is_closed_month"] = False
        report.billing = {
            "summary": {"expected_total_amount": 9999},
            "period_estimate": {
                "cost_type": "PERIOD_ESTIMATE",
                "status": "NOT_APPLICABLE",
            },
            "month_to_date_estimate": {
                "cost_type": "MONTH_TO_DATE_ESTIMATE",
                "status": "AVAILABLE",
                "period_start": "2026-08-01",
                "period_end": "2026-08-16",
                "coverage_start": "2026-08-01",
                "coverage_end": "2026-08-16",
                "total_amount": 4321,
                "amount_basis": "NCP_PRODUCT_DEMAND_USE_AMOUNT",
                "confidence": "PARTIAL",
                "includes_discount": False,
                "includes_vat": False,
            },
            "target_service_summary": [
                {
                    "service_name": "Server",
                    "use_amount": 4321,
                    "row_count": 2,
                }
            ],
            "network_usage_summary": [],
            "usage_summary": [],
        }

        html = HtmlReportRenderer().render(report)

        self.assertIn("4,321", html)
        self.assertNotIn("9,999", html)
        self.assertIn("NCP 서비스별 누적 사용금액", html)
        self.assertNotIn("보고 기간 추정 데이터", html)

    def test_monthly_header_uses_inclusive_last_day(self):
        report = self._sample_report()
        report.period = {
            "period_type": "month",
            "start_dt": "2026-07-01 00:00:00",
            "end_dt": "2026-08-01 00:00:00",
            "end_exclusive": True,
            "file_suffix": "20260701_20260731",
        }

        html = HtmlReportRenderer().render(report)

        self.assertIn("2026-07-01", html)
        self.assertIn("2026-07-31", html)
        self.assertNotIn("2026-08-01", html)

    def test_single_day_report_uses_full_day_axis_and_hourly_average(self):
        report = self._sample_report()
        report.period = {
            "period_type": "day",
            "start_dt": "2026-06-15 00:00:00",
            "end_dt": "2026-06-15 23:59:59",
            "file_suffix": "20260615_20260615",
        }
        for metric in report.server_metrics:
            metric["metric_interval"] = "Min5"

        html = HtmlReportRenderer().render(report)

        self.assertIn("KST 5분 AVG", html)
        self.assertIn("CPU 5분 AVG 사용률", html)
        self.assertIn(">00:00</text>", html)
        self.assertIn(">23:59</text>", html)
        self.assertNotIn("2026-06-16 KST", html)

    def test_chart_splits_lines_across_missing_intervals(self):
        renderer = HtmlReportRenderer()
        two_hours = 2 * 60 * 60 * 1000
        points = [
            (0, 1.0),
            (two_hours, 2.0),
            (10 * two_hours, 3.0),
        ]

        segments = renderer._split_chart_points(
            points,
            expected_interval=two_hours,
        )

        self.assertEqual(segments, [points[:2], points[2:]])

    def test_chart_downsampling_bounds_svg_points_and_keeps_extrema(self):
        renderer = HtmlReportRenderer()
        points = [(index, float(index % 17)) for index in range(10_000)]
        points[5_000] = (5_000, 999.0)

        sampled = renderer._downsample_chart_points(points, max_points=600)

        self.assertLessEqual(len(sampled), 600)
        self.assertEqual(sampled[0], points[0])
        self.assertEqual(sampled[-1], points[-1])
        self.assertIn((5_000, 999.0), sampled)

    def test_event_tables_are_sorted_oldest_first(self):
        renderer = HtmlReportRenderer()
        insight_html = renderer._event_table(
            [
                {
                    "event_id": "late",
                    "start_time": 1781508600000,
                    "message": "insight-late",
                },
                {
                    "event_id": "early",
                    "start_time": 1781505000000,
                    "message": "insight-early",
                },
            ]
        )
        activity_rows = renderer._flatten_grouped(
            {
                "late-group": [
                    {
                        "event_id": "late",
                        "event_time": 1781508600000,
                    }
                ],
                "early-group": [
                    {
                        "event_id": "early",
                        "event_time": 1781505000000,
                    }
                ],
            }
        )

        self.assertLess(
            insight_html.index("insight-early"),
            insight_html.index("insight-late"),
        )
        self.assertEqual(
            [row["event_id"] for row in activity_rows],
            ["early", "late"],
        )

    def test_render_escapes_collected_values_and_omits_raw_metrics(self):
        html = HtmlReportRenderer().render(self._sample_report())

        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("must", html)

    def test_customer_report_options_hide_unselected_sections(self):
        report = self._sample_report()
        report.report_options = {
            "sections": ["activity_history"],
            "resource_categories": [],
            "monitoring_categories": [],
            "diagram": {"enabled": False},
        }

        html = HtmlReportRenderer().render(report)

        self.assertIn("<h2>Cloud Activity Tracer</h2>", html)
        self.assertNotIn("<h2>대표 인프라 현황</h2>", html)
        self.assertNotIn("<h2>클라우드 구성도</h2>", html)
        self.assertNotIn("<h2>과금 데이터 기준</h2>", html)
        self.assertNotIn("<h2>Cloud Insight 이벤트</h2>", html)
        self.assertNotIn("<h2>수집 오류</h2>", html)

    def test_write_creates_utf8_html_file(self):
        report = self._sample_report()

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "report.html"
            result = HtmlReportRenderer().write(report, path)

            self.assertEqual(result, path)
            self.assertTrue(path.exists())
            self.assertIn(
                "NCP 이용 보고서",
                path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()

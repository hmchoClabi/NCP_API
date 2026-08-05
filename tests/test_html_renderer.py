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

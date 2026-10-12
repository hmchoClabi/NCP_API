import tempfile
import unittest
from pathlib import Path

import pytest

from app.report_models import ReportResult
from database.config import DatabaseSettings
from database.report_repository import PostgresReportRepository
from webapp.repository import PortalRepository


@pytest.mark.integration
class DatabaseIntegrationTests(unittest.TestCase):
    CUSTOMER_ID = "integration-smoke-customer"

    def setUp(self):
        self.settings = DatabaseSettings.from_env()
        self.repository = PostgresReportRepository(self.settings)
        self._cleanup_test_customer()

    def tearDown(self):
        self._cleanup_test_customer()

    def _cleanup_test_customer(self):
        import psycopg

        customer_code = self.repository._customer_code(self.CUSTOMER_ID)
        with psycopg.connect(**self.settings.connection_kwargs()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM control.report_runs
                    WHERE tenant_id = (
                        SELECT id FROM control.tenants WHERE customer_code = %s
                    )
                    """,
                    (customer_code,),
                )
                cursor.execute(
                    "DELETE FROM control.tenants WHERE customer_code = %s",
                    (customer_code,),
                )

    def test_report_is_persisted_idempotently_with_searchable_details(self):
        report = ReportResult(
            period={
                "period_type": "day",
                "start_dt": "2026-07-29 00:00:00",
                "end_dt": "2026-07-29 23:59:59",
                "billing_month": "202607",
                "file_suffix": "20260729_20260729",
            },
            customer={
                "id": self.CUSTOMER_ID,
                "name": "Integration Smoke Customer",
                "api_type": "public",
                "region": "KR",
            },
            servers=[{"server_id": "server-1", "server_name": "web-1"}],
            server_metrics=[
                {
                    "server_id": "server-1",
                    "server_name": "web-1",
                    "cpu_min": 1.0,
                    "cpu_avg": 2.0,
                    "cpu_max": 3.0,
                    "raw_metrics": {"used_rto": {"avg": [{"values": [1.0, 2.0, 3.0]}]}},
                }
            ],
            insight_events=[
                {
                    "event_id": "insight-1",
                    "start_time": 1785250800000,
                    "level": "WARNING",
                    "resource_id": "server-1",
                    "resource_name": "web-1",
                    "rule_name": "CPU rule",
                }
            ],
            activity_events={
                "events": [
                    {
                        "event_id": "activity-1",
                        "event_time": 1785250800000,
                        "action_name": "Login",
                        "result": "SUCCESS",
                        "source_ip": "218.38.161.126",
                        "user_name": "viewer@example.com",
                    }
                ]
            },
            billing={
                "summary": {
                    "expected_total_amount": 1000,
                    "confirmed_total_amount": 900,
                    "comparison_status": "OK",
                },
                "expected_cost_summary": [
                    {
                        "service_name": "Server",
                        "item_name": "vCPU",
                        "item_code": "CPU",
                        "usage_quantity": 10,
                        "unit_code": "HOUR",
                        "raw_price": 100,
                        "expected_amount": 1000,
                        "calculation_method": "HOURLY",
                        "calculation_status": "OK",
                    }
                ],
            },
        )

        with tempfile.TemporaryDirectory() as directory:
            html_path = Path(directory) / "report.html"
            html_path.write_text("<html></html>", encoding="utf-8")
            first_run_id = self.repository.save_report(report, artifacts={"HTML": html_path})
            second_run_id = self.repository.save_report(report, artifacts={"HTML": html_path})

            versioned_repository = PostgresReportRepository(
                self.settings,
                idempotency_suffix="history-job-2",
                trigger_type="SCHEDULED",
            )
            versioned_run_id = versioned_repository.save_report(
                report, artifacts={"HTML": html_path}
            )

        self.assertEqual(first_run_id, second_run_id)
        self.assertNotEqual(first_run_id, versioned_run_id)

        history = PortalRepository(self.settings).report_history()
        history_ids = {str(item["report_id"]) for item in history}
        self.assertIn(first_run_id, history_ids)
        self.assertIn(versioned_run_id, history_ids)

        import psycopg

        with psycopg.connect(**self.settings.connection_kwargs()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT r.attempt_count,
                           (SELECT count(*) FROM public_data.report_snapshots s WHERE s.report_run_id = r.id),
                           (SELECT count(*) FROM public_data.insight_events e WHERE e.report_run_id = r.id),
                           (SELECT count(*) FROM public_data.activity_events a WHERE a.report_run_id = r.id),
                           (SELECT count(*) FROM public_data.metric_summaries m WHERE m.report_run_id = r.id),
                           (SELECT count(*) FROM public_data.cost_details c WHERE c.report_run_id = r.id)
                    FROM control.report_runs r
                    WHERE r.id = %s
                    """,
                    (first_run_id,),
                )
                counts = cursor.fetchone()

        self.assertEqual(counts, (2, 1, 1, 1, 1, 1))


if __name__ == "__main__":
    unittest.main()

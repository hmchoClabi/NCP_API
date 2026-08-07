import inspect
import unittest
from datetime import datetime, timezone

from database.config import DatabaseSettings
from database.report_repository import PostgresReportRepository
from app.report_models import ReportResult


class RecordingCursor:
    def __init__(self):
        self.calls = []

    def execute(self, query, parameters):
        self.calls.append((query, parameters))

    def fetchone(self):
        return ("report-run-id",)


class ReportRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.repository = PostgresReportRepository(DatabaseSettings())

    def test_customer_code_is_stable_and_schema_compatible(self):
        first = self.repository._customer_code("Customer.With Spaces")
        second = self.repository._customer_code("Customer.With Spaces")

        self.assertEqual(first, second)
        self.assertRegex(first, r"^[a-z0-9][a-z0-9_-]+[a-z0-9]$")
        self.assertLessEqual(len(first), 80)

    def test_inclusive_report_end_is_saved_as_exclusive(self):
        start, end, end_exclusive = self.repository._period_bounds(
            {
                "start_dt": "2026-07-01 00:00:00",
                "end_dt": "2026-07-01 23:59:59",
            }
        )

        self.assertTrue(end_exclusive)
        self.assertEqual(start.hour, 0)
        self.assertEqual(end, datetime(2026, 7, 2, tzinfo=self.repository.KST))

    def test_invalid_source_ip_is_not_sent_to_inet_column(self):
        self.assertIsNone(self.repository._ip_address("not-an-ip"))
        self.assertEqual(self.repository._ip_address("218.38.161.126"), "218.38.161.126")

    def test_period_aware_billing_fact_is_inserted(self):
        cursor = RecordingCursor()
        report = ReportResult(
            period={
                "start_dt": "2026-07-01 00:00:00",
                "end_dt": "2026-07-31 23:59:59",
            },
            billing={
                "cost_facts": [{
                    "cost_type": "CONFIRMED",
                    "status": "AVAILABLE",
                    "period_start": "2026-07-01",
                    "period_end": "2026-07-31",
                    "coverage_start": "2026-07-01",
                    "coverage_end": "2026-07-31",
                    "calculated_at": "2026-08-07T12:00:00+09:00",
                    "total_amount": 110,
                    "currency": "KRW",
                    "amount_basis": "CURRENT_MONTH_INVOICE_TOTAL",
                    "includes_discount": True,
                    "includes_vat": True,
                    "confidence": "CONFIRMED",
                    "source_api": "getDemandCostList",
                }]
            },
        )

        self.repository._insert_billing_cost_facts(
            cursor, "public_data", report,
            "report-id", "tenant-id", "account-id",
        )

        self.assertEqual(len(cursor.calls), 1)
        query, parameters = cursor.calls[0]
        self.assertIn("public_data.billing_cost_facts", query)
        self.assertEqual(parameters[3], "CONFIRMED")
        self.assertEqual(parameters[6], "2026-07-31")
        self.assertEqual(parameters[13], 110)

    def test_organization_account_fact_is_inserted(self):
        cursor = RecordingCursor()
        report = ReportResult(
            period={"start_dt": "2026-07-01", "end_dt": "2026-07-31"},
            billing={"account_costs": [{
                "member_no": "200",
                "display_name": "Child",
                "is_master": False,
                "service_summary": [{"service_name": "Server", "amount": 100}],
                "expected_by_service": [],
                "cost_facts": [{
                    "cost_type": "CONFIRMED", "status": "AVAILABLE",
                    "period_start": "2026-07-01", "period_end": "2026-07-31",
                    "subtotal_amount": 100, "vat_amount": 10,
                    "total_amount": 110, "confidence": "CONFIRMED",
                }],
            }]},
        )

        self.repository._insert_billing_account_cost_facts(
            cursor, "public_data", report,
            "report-id", "tenant-id", "account-id",
        )

        self.assertEqual(len(cursor.calls), 1)
        query, parameters = cursor.calls[0]
        self.assertIn("public_data.billing_account_cost_facts", query)
        self.assertEqual(parameters[3], "200")
        self.assertEqual(parameters[12], 110)

    def test_daily_fact_uses_month_to_date_when_period_is_not_applicable(self):
        cursor = RecordingCursor()
        report = ReportResult(
            period={
                "start_dt": "2026-08-01 00:00:00",
                "end_dt": "2026-08-31 23:59:59",
            },
            billing={
                "period_estimate": {
                    "status": "NOT_APPLICABLE",
                    "total_amount": None,
                    "confidence": "UNAVAILABLE",
                },
                "month_to_date_estimate": {
                    "status": "AVAILABLE",
                    "total_amount": 4321,
                    "confidence": "PARTIAL",
                },
                "invoice_summary": {"total_amount": 110},
            },
        )

        self.repository._upsert_daily_fact(
            cursor,
            report,
            "report-id",
            "tenant-id",
            "public",
        )

        _, parameters = cursor.calls[0]
        self.assertEqual(parameters[11], 4321)
        self.assertEqual(parameters[13], "PARTIAL")

    def test_daily_fact_does_not_replace_unavailable_period_with_month_total(self):
        cursor = RecordingCursor()
        report = ReportResult(
            period={
                "start_dt": "2026-08-16 00:00:00",
                "end_dt": "2026-08-16 23:59:59",
            },
            billing={
                "period_estimate": {
                    "status": "UNAVAILABLE",
                    "total_amount": None,
                    "confidence": "UNAVAILABLE",
                },
                "month_to_date_estimate": {
                    "status": "AVAILABLE",
                    "total_amount": 4321,
                    "confidence": "PARTIAL",
                },
                "invoice_summary": {"total_amount": 110},
            },
        )

        self.repository._upsert_daily_fact(
            cursor,
            report,
            "report-id",
            "tenant-id",
            "public",
        )

        _, parameters = cursor.calls[0]
        self.assertIsNone(parameters[11])
        self.assertEqual(parameters[13], "UNAVAILABLE")

    def test_report_run_retry_updates_pipeline_versions(self):
        cursor = RecordingCursor()
        report = ReportResult(
            period={
                "start_dt": "2026-07-01 00:00:00",
                "end_dt": "2026-07-31 23:59:59",
                "file_suffix": "20260701_20260731",
            },
        )

        run_id = self.repository._upsert_report_run(
            cursor,
            report,
            "tenant-id",
            "public",
            "account-id",
        )

        query, _ = cursor.calls[0]
        self.assertEqual(run_id, "report-run-id")
        self.assertIn(
            "collector_version = EXCLUDED.collector_version",
            query,
        )
        self.assertIn(
            "normalizer_version = EXCLUDED.normalizer_version",
            query,
        )
        self.assertIn(
            "renderer_version = EXCLUDED.renderer_version",
            query,
        )
        self.assertIn("'1.3', '1.3', '1.3'", query)

    def test_historical_snapshot_query_uses_observation_time_not_report_date(self):
        source = inspect.getsource(
            self.repository.load_period_infrastructure_snapshot
        )

        self.assertIn("collection_metadata,infrastructure,completed_at", source)
        self.assertIn("AT TIME ZONE 'Asia/Seoul'", source)
        self.assertIn("LIVE_API_COLLECTION", source)
        self.assertNotIn("jsonb_array_length", source)
        self.assertNotIn("generated_at", source)

    def test_snapshot_window_preserves_fractional_period_boundaries(self):
        window = self.repository._snapshot_eligibility_window(
            {
                "start_dt": "2026-08-02 09:00:00.125",
                "end_dt": "2026-08-02 10:00:00.875",
                "end_exclusive": True,
            },
            "2026-08-07T12:00:00+09:00",
        )

        self.assertIsNotNone(window)
        self.assertEqual(window["eligible_start"].microsecond, 125_000)
        self.assertEqual(window["eligible_end"].microsecond, 875_000)

    def test_historical_snapshot_window_uses_full_report_period(self):
        window = self.repository._snapshot_eligibility_window(
            {
                "start_dt": "2026-07-01 00:00:00",
                "end_dt": "2026-07-31 23:59:59",
            },
            "2026-08-07T00:00:00Z",
        )

        self.assertIsNotNone(window)
        self.assertEqual(
            window["reference_at"],
            datetime(
                2026, 7, 31, 23, 59, 59, 999999,
                tzinfo=self.repository.KST,
            ),
        )
        self.assertEqual(
            window["eligible_start"],
            datetime(2026, 7, 1, tzinfo=self.repository.KST),
        )
        self.assertEqual(
            window["eligible_end"],
            datetime(2026, 8, 1, tzinfo=self.repository.KST),
        )

    def test_current_snapshot_window_caps_at_reference_time(self):
        window = self.repository._snapshot_eligibility_window(
            {
                "start_dt": "2026-08-01 00:00:00",
                "end_dt": "2026-08-31 23:59:59",
            },
            datetime(2026, 8, 7, 3, 0, tzinfo=timezone.utc),
        )

        self.assertIsNotNone(window)
        self.assertEqual(
            window["eligible_start"],
            datetime(2026, 8, 1, tzinfo=self.repository.KST),
        )
        self.assertEqual(
            window["eligible_end"],
            datetime(
                2026, 8, 7, 12, 0, 0, 1,
                tzinfo=self.repository.KST,
            ),
        )

    def test_future_snapshot_window_is_unavailable(self):
        self.assertIsNone(self.repository._snapshot_eligibility_window(
            {
                "start_dt": "2026-08-08 00:00:00",
                "end_dt": "2026-08-08 23:59:59",
            },
            "2026-08-07T23:59:59+09:00",
        ))

    def test_naive_and_utc_snapshot_times_share_kst_interpretation(self):
        self.assertEqual(
            self.repository._parse_datetime("2026-08-07 12:00:00"),
            self.repository._parse_datetime("2026-08-07T03:00:00Z"),
        )

    def test_monthly_snapshot_window_is_not_limited_to_the_last_kst_day(self):
        window = self.repository._snapshot_eligibility_window(
            {
                "start_dt": "2026-07-01 00:00:00",
                "end_dt": "2026-07-31 23:59:59",
            },
            "2026-08-07T12:00:00+09:00",
        )

        self.assertEqual(window["eligible_start"].day, 1)
        self.assertEqual(window["eligible_end"].date().isoformat(), "2026-08-01")


if __name__ == "__main__":
    unittest.main()

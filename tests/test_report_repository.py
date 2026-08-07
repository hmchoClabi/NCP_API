import unittest
from datetime import datetime

from database.config import DatabaseSettings
from database.report_repository import PostgresReportRepository
from app.report_models import ReportResult


class RecordingCursor:
    def __init__(self):
        self.calls = []

    def execute(self, query, parameters):
        self.calls.append((query, parameters))


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


if __name__ == "__main__":
    unittest.main()

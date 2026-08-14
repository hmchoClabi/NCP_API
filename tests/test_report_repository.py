import inspect
import json
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

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

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


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
            "account-id",
        )

        self.assertEqual(len(cursor.calls), 3)
        self.assertIn("pg_advisory_xact_lock", cursor.calls[0][0])
        query, parameters = cursor.calls[1]
        self.assertIn("control.daily_account_facts", query)
        self.assertEqual(parameters[12], 4321)
        self.assertEqual(parameters[14], "PARTIAL")
        self.assertIn("control.daily_customer_facts", cursor.calls[2][0])

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
            "account-id",
        )

        self.assertEqual(len(cursor.calls), 3)
        _, parameters = cursor.calls[1]
        self.assertIsNone(parameters[12])
        self.assertEqual(parameters[14], "UNAVAILABLE")

    def test_daily_fact_uses_operational_analysis_for_dashboard_counts(self):
        cursor = RecordingCursor()
        report = ReportResult(
            period={
                "start_dt": "2026-08-12 00:00:00",
                "end_dt": "2026-08-12 23:59:59",
            },
            insight_events=[{"level": "INFO"}],
            analysis={
                "data_quality": {"overall_status": "PARTIAL"},
                "findings": [
                    {
                        "severity": "CRITICAL",
                        "category": "PERFORMANCE",
                        "status": "OPEN",
                    },
                    {
                        "severity": "WARNING",
                        "category": "COST",
                        "status": "OPEN",
                    },
                    {
                        "severity": "WARNING",
                        "category": "DATA_QUALITY",
                        "status": "OPEN",
                    },
                    {
                        "severity": "CRITICAL",
                        "category": "SECURITY",
                        "status": "EXCEPTION",
                    },
                ],
            },
        )

        self.repository._upsert_daily_fact(
            cursor,
            report,
            "report-id",
            "tenant-id",
            "public",
            "account-id",
        )

        self.assertEqual(len(cursor.calls), 3)
        _, parameters = cursor.calls[1]
        self.assertEqual(parameters[5], "PARTIAL_SUCCESS")
        self.assertEqual(parameters[7], 1)
        self.assertEqual(parameters[8], 1)
        self.assertEqual(parameters[9], 0)

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
        self.assertIn("'1.5', '1.5', '1.5'", query)

    def test_save_report_does_not_persist_analysis_action_cases(self):
        source = inspect.getsource(self.repository.save_report)

        self.assertNotIn("_upsert_analysis_cases", source)
        self.assertFalse(hasattr(self.repository, "_upsert_analysis_cases"))

    def test_historical_snapshot_query_uses_observation_time_not_report_date(self):
        source = inspect.getsource(
            self.repository.load_period_infrastructure_snapshot
        )

        self.assertIn("collection_metadata,infrastructure,completed_at", source)
        self.assertIn("AT TIME ZONE 'Asia/Seoul'", source)
        self.assertIn("LIVE_API_COLLECTION", source)
        self.assertNotIn("jsonb_array_length", source)
        self.assertNotIn("generated_at", source)

    def test_historical_snapshot_query_executes_with_json_path_literal(self):
        cursor = RecordingCursor()
        observed_at = datetime.fromisoformat("2026-08-08T23:00:00+09:00")
        cursor.fetchone = lambda: (
            {
                "infrastructure": [],
                "collection_metadata": {
                    "infrastructure": {
                        "completed_at": observed_at.isoformat(),
                    }
                },
            },
            "report-run-id",
            observed_at,
        )

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return cursor

        repository = PostgresReportRepository(
            DatabaseSettings(tenant_id="tenant-id")
        )
        fake_psycopg = SimpleNamespace(
            connect=lambda **_kwargs: Connection()
        )

        with patch.dict(sys.modules, {"psycopg": fake_psycopg}):
            snapshot = repository.load_period_infrastructure_snapshot(
                {
                    "start_dt": "2026-08-08T00:00:00+09:00",
                    "end_dt": "2026-08-09T00:00:00+09:00",
                    "end_exclusive": True,
                },
                {
                    "cloud_account_id": "account-id",
                    "api_type": "public",
                },
                "2026-08-09T12:00:00+09:00",
            )

        self.assertIsNotNone(snapshot)
        self.assertEqual(
            snapshot["_snapshot_reference"]["report_run_id"],
            "report-run-id",
        )
        query, parameters = cursor.calls[1]
        self.assertIn(
            "'{collection_metadata,infrastructure,source}'",
            query,
        )
        self.assertEqual(parameters[:2], ("tenant-id", "account-id"))

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

    def test_network_configuration_snapshot_is_stored_separately(self):
        cursor = RecordingCursor()
        report = ReportResult(
            period={
                "start_dt": "2026-08-01 00:00:00",
                "end_dt": "2026-08-10 23:59:59",
            },
            generated_at="2026-08-10T12:30:00+09:00",
        )
        report.network_configuration_snapshot = {
            "configuration": [{
                "category": "ROUTE_TABLE",
                "resource_id": "route-table-1",
                "details": {"routes": []},
            }],
            "captured_at": report.generated_at,
            "source": "REPORT_GENERATION",
            "selected_categories": ["ROUTE_TABLE", "NETWORK_ACL"],
            "reused": False,
            "metadata": {
                "collection_source": "LIVE_API_COLLECTION",
            },
            "collection_completeness": "COMPLETE_FOR_SELECTED_SCOPE",
        }

        self.repository._insert_network_configuration_snapshot(
            cursor,
            "public_data",
            report,
            "report-id",
            "tenant-id",
            "account-id",
        )

        self.assertEqual(len(cursor.calls), 1)
        query, parameters = cursor.calls[0]
        self.assertIn("public_data.network_configuration_snapshots", query)
        self.assertIn("'REPORT_GENERATION'", query)
        self.assertEqual(
            parameters[3],
            datetime(2026, 8, 10, 12, 30, tzinfo=self.repository.KST),
        )
        self.assertEqual(json.loads(parameters[8])[0]["category"], "ROUTE_TABLE")
        metadata = json.loads(parameters[9])
        self.assertEqual(metadata["capture_basis"], "REPORT_GENERATION_TIME")
        self.assertEqual(metadata["category_counts"]["NETWORK_ACL"], 0)
        self.assertEqual(
            metadata["collection_completeness"],
            "COMPLETE_FOR_SELECTED_SCOPE",
        )

    def test_empty_selected_network_snapshot_is_distinct_from_no_selection(self):
        cursor = RecordingCursor()
        report = ReportResult(
            period={"start_dt": "2026-08-10", "end_dt": "2026-08-10"},
            generated_at="2026-08-10T12:30:00+09:00",
        )
        self.repository._insert_network_configuration_snapshot(
            cursor,
            "public_data",
            report,
            "report-id",
            "tenant-id",
            "account-id",
        )
        self.assertEqual(cursor.calls, [])

        report.network_configuration_snapshot = {
            "configuration": [],
            "captured_at": report.generated_at,
            "source": "REPORT_GENERATION",
            "selected_categories": ["NETWORK_ACL"],
            "reused": False,
            "metadata": {"completeness": "PARTIAL"},
        }

        self.repository._insert_network_configuration_snapshot(
            cursor,
            "public_data",
            report,
            "report-id",
            "tenant-id",
            "account-id",
        )

        self.assertEqual(len(cursor.calls), 1)
        _, parameters = cursor.calls[0]
        self.assertEqual(json.loads(parameters[8]), [])
        self.assertEqual(
            json.loads(parameters[9])["selected_categories"],
            ["NETWORK_ACL"],
        )

        cursor.calls.clear()
        report.network_configuration_snapshot["selected_categories"] = []
        self.repository._insert_network_configuration_snapshot(
            cursor,
            "public_data",
            report,
            "report-id",
            "tenant-id",
            "account-id",
        )
        self.assertEqual(cursor.calls, [])

    def test_reused_network_snapshot_is_not_stored_with_a_new_capture_time(self):
        cursor = RecordingCursor()
        report = ReportResult(
            period={"start_dt": "2026-08-10", "end_dt": "2026-08-10"},
        )
        report.network_configuration_snapshot = {
            "configuration": [{"category": "NETWORK_ACL"}],
            "captured_at": "2026-08-08T09:00:00+09:00",
            "source": "STORED_NETWORK_CONFIGURATION_SNAPSHOT",
            "selected_categories": ["NETWORK_ACL"],
            "reused": True,
        }

        self.repository._insert_network_configuration_snapshot(
            cursor,
            "public_data",
            report,
            "report-id",
            "tenant-id",
            "account-id",
        )

        self.assertEqual(cursor.calls, [])

    def test_period_network_snapshot_lookup_returns_capture_time_envelope(self):
        cursor = RecordingCursor()
        captured_at = datetime.fromisoformat("2026-08-08T10:00:00+09:00")
        cursor.fetchone = lambda: (
            [{"category": "ACCESS_CONTROL_GROUP", "resource_id": "acg-1"}],
            "report-run-id",
            captured_at,
            datetime.fromisoformat("2026-08-01T00:00:00+09:00"),
            datetime.fromisoformat("2026-08-11T00:00:00+09:00"),
            True,
            "REPORT_GENERATION",
            "1.0",
            {
                "capture_basis": "REPORT_GENERATION_TIME",
                "selected_categories": ["ACCESS_CONTROL_GROUP", "NETWORK_ACL"],
                "collection_completeness": "COMPLETE_FOR_SELECTED_SCOPE",
            },
        )

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return cursor

        repository = PostgresReportRepository(
            DatabaseSettings(tenant_id="tenant-id")
        )
        fake_psycopg = SimpleNamespace(connect=lambda **_kwargs: Connection())

        with patch.dict(sys.modules, {"psycopg": fake_psycopg}):
            snapshot = repository.load_period_network_configuration_snapshot(
                {
                    "start_dt": "2026-08-08T00:00:00+09:00",
                    "end_dt": "2026-08-09T00:00:00+09:00",
                    "end_exclusive": True,
                },
                {
                    "cloud_account_id": "account-id",
                    "api_type": "public",
                },
                "2026-08-09T12:00:00+09:00",
            )

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["source"], "REPORT_GENERATION")
        self.assertEqual(snapshot["captured_at"], captured_at.isoformat())
        self.assertEqual(
            snapshot["selected_categories"],
            ["ACCESS_CONTROL_GROUP", "NETWORK_ACL"],
        )
        self.assertTrue(snapshot["reused"])
        self.assertEqual(
            snapshot["_snapshot_reference"]["capture_basis"],
            "REPORT_GENERATION_TIME",
        )
        query, parameters = cursor.calls[1]
        self.assertIn("network_configuration_snapshots", query)
        self.assertIn("captured_at >= %s", query)
        self.assertIn("captured_at < %s", query)
        self.assertEqual(parameters[:2], ("tenant-id", "account-id"))


if __name__ == "__main__":
    unittest.main()

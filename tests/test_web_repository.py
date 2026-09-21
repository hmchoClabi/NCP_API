import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.report_branding import validate_customer_logo
from webapp import artifact_cleanup
from webapp.repository import (
    PortalRepository,
    ReportCleanupProtectedError,
    _artifact_storage_usage,
    _artifact_fingerprint,
    _build_dashboard_review,
    _local_report_artifact_paths,
    _preserved_legacy_analysis_policies,
    _remove_queued_artifact,
    _validate_msp_status_change,
    _validate_user_deletion,
    normalize_report_retention_policies,
    validate_report_retention_policies,
)


class ArtifactStorageUsageTests(unittest.TestCase):
    def test_usage_thresholds(self):
        with tempfile.TemporaryDirectory() as directory:
            for used, free, expected_status, expected_percent in (
                (799, 201, "NORMAL", 79.9),
                (800, 200, "WARNING", 80.0),
                (900, 100, "CRITICAL", 90.0),
                (800, 100, "WARNING", 88.9),
            ):
                with self.subTest(used=used, free=free), patch.dict(
                    os.environ, {"REPORT_OUTPUT_DIR": directory}
                ), patch(
                    "webapp.repository.disk_usage",
                    return_value=(1000, used, free),
                ):
                    usage = _artifact_storage_usage()

                self.assertEqual(usage["status"], expected_status)
                self.assertEqual(usage["total_bytes"], 1000)
                self.assertEqual(usage["used_bytes"], used)
                self.assertEqual(usage["free_bytes"], free)
                self.assertEqual(usage["used_percent"], expected_percent)

    def test_unavailable_does_not_expose_path_or_error(self):
        with patch.dict(
            os.environ, {"REPORT_OUTPUT_DIR": "missing-artifact-directory"}
        ):
            usage = _artifact_storage_usage()

        self.assertEqual(
            usage,
            {
                "status": "UNAVAILABLE",
                "total_bytes": None,
                "used_bytes": None,
                "free_bytes": None,
                "used_percent": None,
            },
        )


class DashboardReviewTests(unittest.TestCase):
    def test_history_search_is_parameterized_and_scope_is_preserved(self):
        repository = PortalRepository(MagicMock())
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        repository._connect = MagicMock(return_value=connection)
        repository.report_history(["tenant-1"], query="50%_\\' OR 1=1", status="FAILED", limit=51, offset=50)
        query, parameters = cursor.execute.call_args.args
        self.assertIn("history.tenant_id = ANY(%s::uuid[])", query)
        self.assertIn("LIMIT %s OFFSET %s", query)
        self.assertNotIn("OR 1=1", query)
        self.assertEqual(parameters, [["tenant-1"], "%50\\%\\_\\\\' OR 1=1%", "FAILED", 51, 50])

    def test_findings_are_deduplicated_and_successful_changes_stay_reviewable(self):
        window = datetime(
            2026, 8, 23, tzinfo=timezone(timedelta(hours=9))
        )
        finding = {
            "fingerprint": "same-finding",
            "rule_id": "CPU_HIGH",
            "severity": "CRITICAL",
            "category": "METRIC",
            "status": "OPEN",
            "title": "CPU 사용률이 높습니다.",
            "resource": {"id": "server-1", "name": "web-1"},
            "evidence": [{"label": "최대", "value": 95, "unit": "%"}],
            "impact": "응답 지연 가능성이 있습니다.",
            "recommendation": "프로세스별 부하를 확인하세요.",
        }
        reports = []
        for report_id, completed_at in (
            ("report-new", datetime(2026, 8, 24, tzinfo=timezone.utc)),
            ("report-old", datetime(2026, 8, 23, tzinfo=timezone.utc)),
        ):
            reports.append({
                "id": report_id,
                "tenant_id": "tenant-1",
                "cloud_account_id": "account-1",
                "customer_code": "customer",
                "customer_name": "Customer",
                "environment": "public",
                "account_name": "Primary",
                "report_type": "DAILY",
                "status": "SUCCESS",
                "period_start": completed_at - timedelta(days=1),
                "period_end": completed_at,
                "end_exclusive": True,
                "error_count": 0,
                "completed_at": completed_at,
                "analysis": {
                    "findings": [finding],
                    "changes": {
                        "created_success_count": 1,
                        "deleted_success_count": 0,
                    },
                },
            })

        review = _build_dashboard_review(reports, window)

        self.assertEqual(review["report_count"], 2)
        self.assertEqual(review["customer_count"], 1)
        self.assertEqual(review["analyzed_report_count"], 2)
        self.assertEqual(review["critical_count"], 1)
        self.assertEqual(review["review_count"], 2)
        finding_item = next(
            item for item in review["items"]
            if item["severity"] == "CRITICAL"
        )
        self.assertEqual(finding_item["report_id"], "report-new")
        self.assertEqual(finding_item["report_count"], 2)

    def test_missing_analysis_and_unexplained_partial_collection_are_visible(self):
        window = datetime(
            2026, 8, 23, tzinfo=timezone(timedelta(hours=9))
        )
        common = {
            "tenant_id": "tenant-1",
            "cloud_account_id": "account-1",
            "customer_code": "customer",
            "customer_name": "Customer",
            "environment": "public",
            "account_name": "Primary",
            "report_type": "DAILY",
            "period_start": datetime(2026, 8, 22, tzinfo=timezone.utc),
            "period_end": datetime(2026, 8, 23, tzinfo=timezone.utc),
            "end_exclusive": True,
            "completed_at": datetime(2026, 8, 23, tzinfo=timezone.utc),
        }
        review = _build_dashboard_review([
            {
                **common,
                "id": "missing-analysis",
                "status": "SUCCESS",
                "error_count": 0,
                "analysis": {},
            },
            {
                **common,
                "id": "partial",
                "status": "PARTIAL_SUCCESS",
                "error_count": 2,
                "analysis": {
                    "findings": [],
                    "changes": {"created_success_count": "invalid"},
                },
            },
        ], window)

        self.assertEqual(review["analyzed_report_count"], 1)
        self.assertEqual(review["warning_count"], 2)
        self.assertEqual(
            {item["title"] for item in review["items"]},
            {
                "최근 보고서의 운영 분석 결과를 확인할 수 없습니다.",
                "보고서 수집이 완전하지 않습니다.",
            },
        )

    def test_dashboard_query_scopes_recent_snapshots_by_environment(self):
        repository = PortalRepository(MagicMock())
        connection = MagicMock()
        cursor = MagicMock()
        repository._connect = MagicMock(return_value=connection)
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = {
            "customer_count": 1,
            "public_count": 0,
            "gov_count": 1,
        }
        cursor.fetchall.return_value = []

        with patch(
            "webapp.repository._artifact_storage_usage",
            return_value={"status": "UNAVAILABLE"},
        ):
            dashboard = repository.dashboard({"gov"})

        self.assertEqual(dashboard["summary"]["issue_count"], 0)
        self.assertEqual(dashboard["recent_review"]["report_count"], 0)
        self.assertEqual(cursor.execute.call_count, 2)
        query, parameters = cursor.execute.call_args_list[1].args
        self.assertIn("report.completed_at >= %s", query)
        self.assertIn("report.environment = ANY(%s)", query)
        self.assertIn("public_snapshot.normalized_data -> 'analysis'", query)
        self.assertIn("tenant.status <> 'OFFBOARDED'", query)
        self.assertEqual(parameters[1], ["gov"])
        self.assertEqual(
            parameters[0].utcoffset(), timedelta(hours=9)
        )
        self.assertEqual(
            (parameters[0].hour, parameters[0].minute), (0, 0)
        )


class ReportRetentionPolicyTests(unittest.TestCase):
    def test_missing_policy_defaults_to_forever_without_accepting_bad_days(self):
        self.assertEqual(
            normalize_report_retention_policies({
                "DAILY": {"mode": "DAYS", "days": 30},
                "WEEKLY": {"mode": "DAYS", "days": "0"},
            }),
            {
                "DAILY": {"mode": "DAYS", "days": 30},
                "WEEKLY": {"mode": "FOREVER", "days": None},
                "MONTHLY": {"mode": "FOREVER", "days": None},
            },
        )

    def test_explicit_policy_requires_every_type_and_bounded_days(self):
        valid = {
            "DAILY": {"mode": "DAYS", "days": "7"},
            "WEEKLY": {"mode": "FOREVER", "days": "ignored"},
            "MONTHLY": {"mode": "DAYS", "days": 3650},
        }

        self.assertEqual(
            validate_report_retention_policies(valid)["DAILY"],
            {"mode": "DAYS", "days": 7},
        )
        for invalid in (
            {"DAILY": {"mode": "FOREVER"}},
            {**valid, "DAILY": {"mode": "DAYS", "days": 0}},
            {**valid, "DAILY": {"mode": "DAYS", "days": 3651}},
            {**valid, "CUSTOM": {"mode": "DAYS", "days": 1}},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_report_retention_policies(invalid)

    def test_report_option_update_preserves_existing_retention(self):
        repository = PortalRepository(MagicMock())
        connection = MagicMock()
        cursor = MagicMock()
        repository._connect = MagicMock(return_value=connection)
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        cursor.__enter__.return_value = cursor
        retention = {
            "DAILY": {"mode": "DAYS", "days": 30},
            "WEEKLY": {"mode": "FOREVER", "days": None},
            "MONTHLY": {"mode": "FOREVER", "days": None},
        }
        cursor.fetchone.side_effect = [
            {"id": "11111111-1111-1111-1111-111111111111"},
            {"settings": {"retention_policies": retention}},
        ]

        repository.update_tenant_report_settings(
            "11111111-1111-1111-1111-111111111111",
            {
                "sections": ["billing"],
                "resource_categories": [],
                "monitoring_categories": [],
            },
            "22222222-2222-2222-2222-222222222222",
        )

        upsert = next(
            call for call in cursor.execute.call_args_list
            if "ON CONFLICT (tenant_id) DO UPDATE SET" in call.args[0]
        )
        stored = json.loads(upsert.args[1][1])
        self.assertEqual(stored["retention_policies"], retention)
        self.assertEqual(stored["sections"], ["billing"])

    def test_bulk_retention_update_rechecks_active_scoped_tenants(self):
        repository = PortalRepository(MagicMock())
        connection = MagicMock()
        cursor = MagicMock()
        repository._connect = MagicMock(return_value=connection)
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        cursor.__enter__.return_value = cursor
        tenant_ids = [
            "11111111-1111-1111-1111-111111111111",
            "22222222-2222-2222-2222-222222222222",
        ]
        cursor.fetchall.return_value = [
            {"id": tenant_id} for tenant_id in tenant_ids
        ]
        policies = {
            report_type: {"mode": "DAYS", "days": 30}
            for report_type in ("DAILY", "WEEKLY", "MONTHLY")
        }

        updated = repository.bulk_update_report_retention(
            tenant_ids,
            policies,
            "33333333-3333-3333-3333-333333333333",
            allowed_environments={"public"},
        )

        self.assertEqual(updated, 2)
        tenant_select = cursor.execute.call_args_list[0]
        self.assertIn("status = 'ACTIVE'", tenant_select.args[0])
        self.assertIn("environment = ANY(%s)", tenant_select.args[0])
        settings_updates = [
            call for call in cursor.execute.call_args_list
            if "UPDATE control.tenant_report_settings" in call.args[0]
        ]
        self.assertEqual(len(settings_updates), 1)
        self.assertIn("jsonb_build_object", settings_updates[0].args[0])
        self.assertEqual(json.loads(settings_updates[0].args[1][0]), policies)


class ReportArtifactCleanupTests(unittest.TestCase):
    def test_candidate_selection_stays_below_output_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_root = root / "output"
            output_root.mkdir()
            report_file = output_root / "ncp_report_20260801_20260831.html"
            legacy_file = output_root / "billing_raw_20260801_20260831.json"
            unrelated_file = output_root / "billing_raw_other-period.json"
            outside_file = root / "outside.html"
            report_file.write_text("report", encoding="utf-8")
            legacy_file.write_text("sensitive", encoding="utf-8")
            unrelated_file.write_text("unrelated", encoding="utf-8")
            outside_file.write_text("outside", encoding="utf-8")

            with patch.dict(os.environ, {"REPORT_OUTPUT_DIR": str(output_root)}):
                candidates, failed = _local_report_artifact_paths([
                    report_file.as_uri(),
                    outside_file.as_uri(),
                    "s3://archive/report.html",
                ])

            self.assertEqual(failed, 0)
            self.assertIn(report_file.resolve(), candidates)
            self.assertIn(legacy_file.resolve(), candidates)
            self.assertNotIn(unrelated_file.resolve(), candidates)
            self.assertNotIn(outside_file.resolve(), candidates)

    def test_candidate_selection_reports_malformed_local_uri(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"REPORT_OUTPUT_DIR": directory}):
                candidates, failed = _local_report_artifact_paths([
                    Path(directory).as_uri() + "/%00",
                ])

            self.assertEqual(candidates, set())
            self.assertEqual(failed, 1)

    def test_queued_cleanup_preserves_content_that_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "report.html"
            artifact.write_text("original", encoding="utf-8")
            checksum, byte_size = _artifact_fingerprint(artifact)
            artifact.write_text("replacement", encoding="utf-8")

            with patch.dict(os.environ, {"REPORT_OUTPUT_DIR": directory}):
                completed, result_code = _remove_queued_artifact(
                    artifact.as_uri(),
                    checksum,
                    byte_size,
                )

            self.assertFalse(completed)
            self.assertEqual(result_code, "CONTENT_CHANGED")
            self.assertTrue(artifact.exists())

    def test_queued_cleanup_treats_missing_file_as_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.html"
            with patch.dict(os.environ, {"REPORT_OUTPUT_DIR": directory}):
                self.assertEqual(
                    _remove_queued_artifact(
                        missing.as_uri(),
                        "0" * 64,
                        0,
                    ),
                    (True, "MISSING"),
                )


class TenantDeletionArtifactCleanupTests(unittest.TestCase):
    def test_queue_rejects_local_file_outside_report_root(self):
        repository = PortalRepository(MagicMock())
        cursor = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            output.mkdir()
            outside = root / "outside.html"
            outside.write_text("outside", encoding="utf-8")

            with patch.dict(os.environ, {"REPORT_OUTPUT_DIR": str(output)}):
                with self.assertRaisesRegex(ValueError, "경로 1건"):
                    repository._queue_artifact_cleanup(
                        cursor,
                        tenant_id="tenant-1",
                        storage_uris=[outside.as_uri()],
                        owner_column="report_run_id",
                        owner_id="report-1",
                    )

        cursor.execute.assert_not_called()

    def test_queue_fingerprints_owned_file_and_skips_shared_file(self):
        repository = PortalRepository(MagicMock())
        cursor = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            owned = Path(directory) / "owned.html"
            shared = Path(directory) / "ncp_report_20260801_20260831.html"
            shared_legacy = Path(directory) / "billing_raw_20260801_20260831.json"
            owned.write_text("owned", encoding="utf-8")
            shared.write_text("shared", encoding="utf-8")
            shared_legacy.write_text("shared legacy", encoding="utf-8")
            repository._other_artifact_storage_uris = MagicMock(
                return_value=[shared.as_uri()]
            )

            with patch.dict(os.environ, {"REPORT_OUTPUT_DIR": directory}):
                operation_id, queued, shared_count = (
                    repository._queue_artifact_cleanup(
                        cursor,
                        tenant_id="tenant-1",
                        storage_uris=[owned.as_uri(), shared.as_uri()],
                        owner_column="report_run_id",
                        owner_id="report-1",
                    )
                )

        self.assertIsNotNone(operation_id)
        self.assertEqual((queued, shared_count), (1, 11))
        insert = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO control.artifact_cleanup_outbox" in call.args[0]
        )
        self.assertEqual(insert.args[1][2], owned.as_uri())
        self.assertEqual(insert.args[1][4], 5)

    def test_permanent_delete_commits_before_cleanup_drain(self):
        repository = PortalRepository(MagicMock())
        connection = MagicMock()
        cursor = MagicMock()
        repository._connect = MagicMock(return_value=connection)
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = {
            "customer_name": "Customer",
            "customer_code": "customer",
            "environment": "public",
            "status": "OFFBOARDED",
            "report_count": 1,
            "has_running_job": False,
        }
        cursor.fetchall.side_effect = [
            [{"storage_uri": "file:///output/report.html"}],
            [{"storage_uri": "file:///output/raw.json"}],
            [{"artifact_uri": "file:///output/metrics.json"}],
        ]
        repository._queue_artifact_cleanup = MagicMock(
            return_value=("00000000-0000-0000-0000-000000000001", 3, 0)
        )

        def finish_after_commit(operation_id, queued_count):
            self.assertTrue(connection.__exit__.called)
            return 3, 0

        repository._finish_artifact_cleanup = MagicMock(
            side_effect=finish_after_commit
        )

        result = repository.permanently_delete_tenant(
            "tenant-1",
            "admin-1",
            "archive://customer/reports",
        )

        self.assertEqual(result, ("Customer", 1))
        repository._finish_artifact_cleanup.assert_called_once()
        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertLess(
            next(i for i, sql in enumerate(statements) if "report_artifacts" in sql),
            next(i for i, sql in enumerate(statements) if "DELETE FROM control.report_runs" in sql),
        )

    def test_commit_failure_does_not_start_tenant_file_cleanup(self):
        repository = PortalRepository(MagicMock())
        connection = MagicMock()
        cursor = MagicMock()
        repository._connect = MagicMock(return_value=connection)
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = {
            "customer_name": "Customer",
            "customer_code": "customer",
            "environment": "public",
            "status": "OFFBOARDED",
            "report_count": 1,
            "has_running_job": False,
        }
        cursor.fetchall.side_effect = [
            [{"storage_uri": "file:///output/report.html"}],
            [],
            [],
        ]
        repository._queue_artifact_cleanup = MagicMock(
            return_value=("00000000-0000-0000-0000-000000000001", 1, 0)
        )
        repository._finish_artifact_cleanup = MagicMock()
        connection.__exit__.side_effect = RuntimeError("commit failed")

        with self.assertRaisesRegex(RuntimeError, "commit failed"):
            repository.permanently_delete_tenant(
                "tenant-1",
                "admin-1",
                "archive://customer/reports",
            )

        repository._finish_artifact_cleanup.assert_not_called()


class DurableReportCleanupQueueTests(unittest.TestCase):
    REPORT_ID = "11111111-1111-1111-1111-111111111111"
    TENANT_ID = "22222222-2222-2222-2222-222222222222"
    ACTOR_ID = "33333333-3333-3333-3333-333333333333"

    def _repository_with_cursor(self):
        repository = PortalRepository(MagicMock())
        connection = MagicMock()
        cursor = MagicMock()
        repository._connect = MagicMock(return_value=connection)
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        cursor.__enter__.return_value = cursor
        return repository, cursor

    def test_manual_request_queues_only_currently_eligible_rows(self):
        repository, cursor = self._repository_with_cursor()
        protected_id = "44444444-4444-4444-4444-444444444444"
        queued_id = "55555555-5555-5555-5555-555555555555"
        cursor.fetchall.side_effect = [
            [
                {
                    "id": self.REPORT_ID,
                    "cleanup_requested_at": None,
                    "protection_reason": None,
                },
                {
                    "id": protected_id,
                    "cleanup_requested_at": None,
                    "protection_reason": "LATEST",
                },
                {
                    "id": queued_id,
                    "cleanup_requested_at": datetime.now(timezone.utc),
                    "protection_reason": "CLEANUP_QUEUED",
                },
            ],
            [{"id": self.REPORT_ID, "tenant_id": self.TENANT_ID}],
        ]

        result = repository.request_report_cleanup(
            [self.REPORT_ID, protected_id, queued_id],
            self.ACTOR_ID,
            allowed_environments={"public"},
        )

        self.assertEqual(result, {
            "queued_count": 1,
            "already_queued_count": 1,
            "protected_count": 1,
        })
        update = next(
            call for call in cursor.execute.call_args_list
            if "SET cleanup_requested_at" in call.args[0]
        )
        self.assertIn("retention_policies", update.args[0])
        self.assertIn("retention_until >= CURRENT_DATE", update.args[0])
        self.assertIn("latest.status IN", update.args[0])
        self.assertEqual(update.args[1], (self.ACTOR_ID, [self.REPORT_ID]))

    def test_all_request_only_queues_eligible_preview_rows(self):
        repository, cursor = self._repository_with_cursor()
        repository.report_cleanup_candidates = MagicMock(return_value=[
            {"id": self.REPORT_ID, "eligible": True},
            {"id": "44444444-4444-4444-4444-444444444444", "eligible": False},
        ])
        cursor.fetchall.side_effect = [
            [{
                "id": self.REPORT_ID,
                "cleanup_requested_at": None,
                "protection_reason": None,
            }],
            [{"id": self.REPORT_ID, "tenant_id": self.TENANT_ID}],
        ]

        result = repository.request_report_cleanup(
            None,
            self.ACTOR_ID,
            allowed_environments={"public"},
            all_eligible=True,
        )

        self.assertEqual(result["queued_count"], 1)
        repository.report_cleanup_candidates.assert_called_once_with({"public"})
        preview_recheck = cursor.execute.call_args_list[0]
        self.assertIn("report.id = ANY(%s::uuid[])", preview_recheck.args[0])
        self.assertEqual(
            preview_recheck.args[1],
            (["public"], [self.REPORT_ID]),
        )

    def test_retention_enqueue_is_bounded_and_malformed_json_is_fail_closed(self):
        repository, cursor = self._repository_with_cursor()
        cursor.fetchall.return_value = [
            {"id": self.REPORT_ID, "tenant_id": self.TENANT_ID}
        ]

        self.assertEqual(repository.enqueue_expired_report_cleanup(limit=25), 1)

        enqueue = cursor.execute.call_args_list[0]
        sql = enqueue.args[0]
        self.assertIn("jsonb_typeof(policy.value -> 'days') = 'number'", sql)
        self.assertIn("~ '^[1-9][0-9]{0,3}$'", sql)
        self.assertIn("parsed.retention_days BETWEEN 1 AND 3650", sql)
        self.assertIn("COALESCE(report.completed_at, report.created_at)", sql)
        self.assertIn("FOR UPDATE OF report SKIP LOCKED", sql)
        self.assertIn("retention_until >= CURRENT_DATE", sql)
        self.assertNotIn("latest", sql.casefold())
        self.assertEqual(enqueue.args[1], (25,))

    def test_processor_isolates_protected_and_failed_requests(self):
        repository, cursor = self._repository_with_cursor()
        protected_id = "44444444-4444-4444-4444-444444444444"
        failed_id = "55555555-5555-5555-5555-555555555555"
        cursor.fetchall.return_value = [
            {
                "id": self.REPORT_ID,
                "cleanup_requested_by": None,
                "cleanup_reason": "RETENTION_POLICY",
            },
            {
                "id": protected_id,
                "cleanup_requested_by": self.ACTOR_ID,
                "cleanup_reason": "MANUAL",
            },
            {
                "id": failed_id,
                "cleanup_requested_by": self.ACTOR_ID,
                "cleanup_reason": "MANUAL",
            },
        ]
        repository.delete_report = MagicMock(side_effect=[
            {
                "removed_artifact_files": 2,
                "failed_artifact_files": 1,
            },
            ReportCleanupProtectedError("protected"),
            RuntimeError("temporary failure"),
        ])
        repository._record_report_cleanup_failure = MagicMock()

        result = repository.process_requested_report_cleanup(limit=3)

        self.assertEqual(result, {
            "claimed_count": 3,
            "deleted_count": 1,
            "protected_count": 1,
            "failed_count": 1,
            "removed_artifact_files": 2,
            "pending_artifact_files": 1,
        })
        self.assertEqual(
            repository.delete_report.call_args_list[0].kwargs,
            {"protect_latest": False, "automated_retention": True},
        )
        self.assertEqual(
            repository.delete_report.call_args_list[1].kwargs,
            {"protect_latest": True, "automated_retention": False},
        )
        repository._record_report_cleanup_failure.assert_any_call(
            protected_id,
            "PROTECTED_AT_EXECUTION",
            terminal=True,
        )
        repository._record_report_cleanup_failure.assert_any_call(
            failed_id,
            "DELETE_FAILED",
            terminal=False,
        )

    @patch("webapp.artifact_cleanup.PortalRepository")
    @patch("webapp.artifact_cleanup.DatabaseSettings.from_env")
    def test_cleanup_consumer_enqueues_expires_processes_and_drains_outbox(
        self,
        settings_from_env,
        repository_class,
    ):
        repository = repository_class.return_value
        repository.enqueue_expired_report_cleanup.return_value = 2
        repository.process_requested_report_cleanup.return_value = {
            "deleted_count": 1,
            "protected_count": 1,
            "failed_count": 0,
            "removed_artifact_files": 1,
        }
        repository.retry_artifact_cleanup.return_value = (2, 0)

        with patch("sys.argv", ["artifact-cleanup", "--limit", "25"]):
            artifact_cleanup.main()

        settings_from_env.assert_called_once_with()
        repository.enqueue_expired_report_cleanup.assert_called_once_with(
            limit=25
        )
        repository.process_requested_report_cleanup.assert_called_once_with(
            limit=25
        )
        repository.retry_artifact_cleanup.assert_called_once_with(limit=25)


class ReportDeletionArtifactCleanupTests(unittest.TestCase):
    def test_cleanup_preview_marks_latest_and_scopes_environments(self):
        repository = PortalRepository(MagicMock())
        connection = MagicMock()
        cursor = MagicMock()
        repository._connect = MagicMock(return_value=connection)
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        cursor.__enter__.return_value = cursor
        cursor.fetchall.return_value = [
            {"id": "old", "protection_reason": None},
            {"id": "latest", "protection_reason": "LATEST"},
        ]

        reports = repository.report_cleanup_candidates({"gov", "public"})

        self.assertEqual(
            [(item["id"], item["eligible"]) for item in reports],
            [("old", True), ("latest", False)],
        )
        sql, parameters = cursor.execute.call_args.args
        self.assertIn("DISTINCT ON", sql)
        self.assertIn("retention_until >= CURRENT_DATE", sql)
        self.assertIn("OR COALESCE", sql)
        self.assertEqual(parameters, (["gov", "public"],))

    def test_delete_report_rechecks_latest_and_retention_protection(self):
        for protection in ("is_latest", "retention_protected"):
            with self.subTest(protection=protection):
                repository = PortalRepository(MagicMock())
                connection = MagicMock()
                cursor = MagicMock()
                repository._connect = MagicMock(return_value=connection)
                connection.__enter__.return_value = connection
                connection.cursor.return_value = cursor
                cursor.__enter__.return_value = cursor
                cursor.fetchone.return_value = {
                    "id": "report-1",
                    "tenant_id": "tenant-1",
                    "environment": "public",
                    "status": "SUCCESS",
                    "report_type": "DAILY",
                    "customer_name": "Customer",
                    "is_latest": protection == "is_latest",
                    "retention_protected": protection == "retention_protected",
                }
                repository._queue_artifact_cleanup = MagicMock()

                with self.assertRaisesRegex(ValueError, "정리할 수 없습니다"):
                    repository.delete_report(
                        "report-1",
                        "admin-1",
                        protect_latest=True,
                    )

                repository._queue_artifact_cleanup.assert_not_called()

    def test_regular_delete_keeps_existing_latest_report_contract(self):
        repository = PortalRepository(MagicMock())
        connection = MagicMock()
        cursor = MagicMock()
        repository._connect = MagicMock(return_value=connection)
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = {
            "id": "report-1",
            "tenant_id": "tenant-1",
            "environment": "public",
            "status": "SUCCESS",
            "report_type": "DAILY",
            "customer_name": "Customer",
            "is_latest": True,
            "retention_protected": False,
        }
        cursor.fetchall.side_effect = [[], [], []]
        repository._queue_artifact_cleanup = MagicMock(
            return_value=(None, 0, 0)
        )

        deleted = repository.delete_report("report-1", "admin-1")

        self.assertEqual(deleted["tenant_id"], "tenant-1")

    def test_explicit_forever_policy_blocks_regular_manual_delete(self):
        repository = PortalRepository(MagicMock())
        connection = MagicMock()
        cursor = MagicMock()
        repository._connect = MagicMock(return_value=connection)
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        cursor.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [
            {
                "id": "report-1",
                "tenant_id": "tenant-1",
                "environment": "public",
                "status": "SUCCESS",
                "report_type": "DAILY",
                "customer_name": "Customer",
                "is_latest": False,
                "retention_protected": False,
            },
            {
                "settings": {
                    "retention_policies": {
                        "DAILY": {"mode": "FOREVER", "days": None}
                    }
                },
                "evaluated_at": datetime.now(timezone.utc),
            },
        ]
        repository._queue_artifact_cleanup = MagicMock()

        with self.assertRaisesRegex(
            ReportCleanupProtectedError,
            "영구 보존",
        ):
            repository.delete_report("report-1", "admin-1")

        repository._queue_artifact_cleanup.assert_not_called()

    def test_automated_delete_rechecks_policy_under_lock_and_audits_basis(self):
        repository = PortalRepository(MagicMock())
        connection = MagicMock()
        cursor = MagicMock()
        repository._connect = MagicMock(return_value=connection)
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        cursor.__enter__.return_value = cursor
        completed_at = datetime.now(timezone.utc) - timedelta(days=31)
        cursor.fetchone.side_effect = [
            {
                "id": "report-1",
                "tenant_id": "tenant-1",
                "environment": "public",
                "status": "SUCCESS",
                "report_type": "DAILY",
                "completed_at": completed_at,
                "created_at": completed_at - timedelta(minutes=5),
                "cleanup_reason": "RETENTION_POLICY",
                "customer_name": "Customer",
                "is_latest": True,
                "retention_protected": False,
            },
            {
                "settings": {
                    "retention_policies": {
                        "DAILY": {"mode": "DAYS", "days": 30}
                    }
                },
                "evaluated_at": datetime.now(timezone.utc),
            },
        ]
        cursor.fetchall.side_effect = [[], [], []]
        repository._queue_artifact_cleanup = MagicMock(
            return_value=(None, 0, 0)
        )

        repository.delete_report(
            "report-1",
            None,
            protect_latest=False,
            automated_retention=True,
        )

        settings_lock = cursor.execute.call_args_list[1]
        self.assertIn("FOR UPDATE", settings_lock.args[0])
        audit = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO audit.data_change_logs" in call.args[0]
        )
        changed_fields = json.loads(audit.args[1][3])
        self.assertTrue(changed_fields["automated"])
        self.assertEqual(
            changed_fields["cleanup_reason"],
            "RETENTION_POLICY_EXPIRED",
        )
        self.assertEqual(
            changed_fields["retention_policy"],
            {"mode": "DAYS", "days": 30},
        )
        self.assertEqual(changed_fields["retention_basis"], "completed_at")

    def test_commit_failure_does_not_start_report_file_cleanup(self):
        repository = PortalRepository(MagicMock())
        connection = MagicMock()
        cursor = MagicMock()
        repository._connect = MagicMock(return_value=connection)
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = {
            "id": "report-1",
            "tenant_id": "tenant-1",
            "environment": "public",
            "status": "SUCCESS",
            "report_type": "MONTHLY",
            "customer_name": "Customer",
        }
        cursor.fetchall.side_effect = [
            [{"storage_uri": "file:///output/report.html"}],
            [],
            [],
        ]
        repository._queue_artifact_cleanup = MagicMock(
            return_value=("00000000-0000-0000-0000-000000000001", 1, 0)
        )
        repository._finish_artifact_cleanup = MagicMock()
        connection.__exit__.side_effect = RuntimeError("commit failed")

        with self.assertRaisesRegex(RuntimeError, "commit failed"):
            repository.delete_report("report-1", "admin-1")

        repository._finish_artifact_cleanup.assert_not_called()

    @patch("webapp.repository._remove_queued_artifact")
    def test_retry_deletes_completed_row_and_keeps_failed_row(self, remove):
        repository = PortalRepository(MagicMock())
        connection = MagicMock()
        cursor = MagicMock()
        repository._connect = MagicMock(return_value=connection)
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        cursor.__enter__.return_value = cursor
        rows = [
            {
                "id": "cleanup-1",
                "storage_uri": "file:///output/one.html",
                "expected_sha256": "1" * 64,
                "expected_byte_size": 1,
            },
            {
                "id": "cleanup-2",
                "storage_uri": "file:///output/two.html",
                "expected_sha256": "2" * 64,
                "expected_byte_size": 2,
            },
        ]
        cursor.fetchall.side_effect = [rows, []]
        cursor.fetchone.return_value = {"count": 1}
        remove.side_effect = [(True, "REMOVED"), (False, "REMOVE_FAILED")]

        self.assertEqual(
            repository.retry_artifact_cleanup(limit=10),
            (1, 1),
        )

        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertIn(
            "ORDER BY next_attempt_at, created_at, id",
            statements[0],
        )
        self.assertTrue(any(
            "DELETE FROM control.artifact_cleanup_outbox" in sql
            for sql in statements
        ))
        retry_update = next(
            sql for sql in statements
            if "UPDATE control.artifact_cleanup_outbox" in sql
        )
        self.assertIn(
            "1 << LEAST(attempt_count, 8)",
            retry_update,
        )

    @patch("webapp.repository._remove_queued_artifact")
    def test_retry_preserves_file_that_gained_a_new_database_reference(
        self,
        remove,
    ):
        repository = PortalRepository(MagicMock())
        connection = MagicMock()
        cursor = MagicMock()
        repository._connect = MagicMock(return_value=connection)
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        cursor.__enter__.return_value = cursor
        row = {
            "id": "cleanup-1",
            "storage_uri": "file:///output/report.html",
            "expected_sha256": "1" * 64,
            "expected_byte_size": 1,
        }
        cursor.fetchall.side_effect = [
            [row],
            [{"storage_uri": row["storage_uri"]}],
        ]
        cursor.fetchone.return_value = {"count": 1}

        self.assertEqual(repository.retry_artifact_cleanup(), (0, 1))

        remove.assert_not_called()
        update = next(
            call for call in cursor.execute.call_args_list
            if "UPDATE control.artifact_cleanup_outbox" in call.args[0]
        )
        self.assertEqual(update.args[1][0], "STILL_REFERENCED")


class LegacyReportPolicyCompatibilityTests(unittest.TestCase):
    def test_only_known_boolean_policy_values_are_preserved(self):
        settings = {
            "operational_analysis": {
                "policies": {
                    "require_block_storage_encryption": False,
                    "require_backup": True,
                    "unknown_policy": True,
                    "flag_public_ip": "true",
                }
            }
        }

        self.assertEqual(
            _preserved_legacy_analysis_policies(settings),
            {
                "require_block_storage_encryption": False,
                "require_backup": True,
            },
        )

    def test_json_settings_are_supported_without_reactivating_policies(self):
        settings = json.dumps({
            "operational_analysis": {
                "policies": {"flag_public_ip": False}
            }
        })

        self.assertEqual(
            _preserved_legacy_analysis_policies(settings),
            {"flag_public_ip": False},
        )


class ReportDetailRepositoryTests(unittest.TestCase):
    def test_report_detail_replays_dedicated_network_snapshot(self):
        repository = PortalRepository(MagicMock())
        connection = MagicMock()
        cursor = MagicMock()
        repository._connect = MagicMock(return_value=connection)
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        cursor.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [
            {
                "id": "report-1",
                "tenant_id": "tenant-1",
                "environment": "public",
            },
            {
                "normalized_data": {
                    "infrastructure": [
                        {"category": "SERVER", "resource_name": "server-1"},
                        {"category": "ROUTE_TABLE", "resource_name": "stale"},
                    ]
                }
            },
            {
                "configuration": [
                    {"category": "ROUTE_TABLE", "resource_name": "route-1"}
                ]
            },
        ]

        report = repository.report_detail("report-1", ["tenant-1"])

        self.assertEqual(
            report["snapshot"]["infrastructure"],
            [
                {"category": "SERVER", "resource_name": "server-1"},
                {"category": "ROUTE_TABLE", "resource_name": "route-1"},
            ],
        )
        self.assertIn(
            "public_data.network_configuration_snapshots",
            cursor.execute.call_args_list[-1].args[0],
        )


class TenantBrandingRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.content = (
            b"\x89PNG\r\n\x1a\n"
            + (13).to_bytes(4, "big")
            + b"IHDR"
            + (320).to_bytes(4, "big")
            + (120).to_bytes(4, "big")
            + b"\x08\x06\x00\x00\x00\x00\x00\x00\x00"
        )
        self.logo = validate_customer_logo(self.content, "image/png")

    def test_branding_view_returns_only_validated_data_uri_and_metadata(self):
        branding = PortalRepository._branding_view({
            "logo_content": memoryview(self.content),
            "logo_content_type": "image/png",
            "logo_width": 320,
            "logo_height": 120,
            "logo_sha256": self.logo.sha256,
            "updated_at": "2026-08-10T00:00:00Z",
        })

        self.assertEqual(branding["logo_data_uri"], self.logo.data_uri)
        self.assertNotIn("logo_content", branding)

    def test_logo_audit_record_contains_metadata_but_not_image_bytes(self):
        cursor = MagicMock()

        PortalRepository._record_logo_change(
            cursor,
            "tenant-1",
            "actor-1",
            self.logo,
        )

        parameters = cursor.execute.call_args.args[1]
        changed_fields = parameters[-1]
        self.assertIn(self.logo.sha256, changed_fields)
        self.assertNotIn(self.logo.data_uri, changed_fields)

    def test_branding_view_rejects_metadata_integrity_mismatch(self):
        with self.assertRaisesRegex(ValueError, "무결성"):
            PortalRepository._branding_view({
                "logo_content": self.content,
                "logo_content_type": "image/png",
                "logo_width": 321,
                "logo_height": 120,
                "logo_sha256": self.logo.sha256,
                "updated_at": "2026-08-10T00:00:00Z",
            })

    def test_anonymization_removes_current_branding_record(self):
        cursor = MagicMock()

        PortalRepository._anonymize_tenant_contacts_and_accounts(
            cursor,
            "tenant-1",
        )

        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertTrue(any(
            "DELETE FROM control.tenant_branding" in statement
            for statement in statements
        ))


class MspAccountStatusSafetyTests(unittest.TestCase):
    def test_rejects_self_deactivation(self):
        with self.assertRaisesRegex(ValueError, "자신의 MSP 계정"):
            _validate_msp_status_change(
                target_user_id="admin-1",
                actor_id="admin-1",
                current_status="ACTIVE",
                enabled=False,
                is_admin=True,
                active_admin_count=2,
            )

    def test_rejects_last_active_admin_deactivation(self):
        with self.assertRaisesRegex(ValueError, "마지막 활성 MSP 관리자"):
            _validate_msp_status_change(
                target_user_id="admin-2",
                actor_id="admin-1",
                current_status="ACTIVE",
                enabled=False,
                is_admin=True,
                active_admin_count=1,
            )

    def test_allows_other_admin_when_another_active_admin_remains(self):
        _validate_msp_status_change(
            target_user_id="admin-2",
            actor_id="admin-1",
            current_status="ACTIVE",
            enabled=False,
            is_admin=True,
            active_admin_count=2,
        )

    def test_rejects_unlocking_security_locked_account(self):
        with self.assertRaisesRegex(ValueError, "잠김 또는 초대"):
            _validate_msp_status_change(
                target_user_id="operator-1",
                actor_id="admin-1",
                current_status="LOCKED",
                enabled=True,
                is_admin=False,
                active_admin_count=None,
            )


class UserDeletionSafetyTests(unittest.TestCase):
    BASE = {
        "target_user_id": "user-2",
        "actor_id": "admin-1",
        "target_email": "user@example.com",
        "confirmation_email": "user@example.com",
        "target_status": "ACTIVE",
        "platform_roles": set(),
        "platform_environment_scopes": set(),
        "membership_environments": {"public"},
        "allowed_environments": {"public"},
        "active_admin_count": None,
    }

    def test_accepts_customer_user_inside_actor_scope(self):
        self.assertEqual(
            _validate_user_deletion(**self.BASE),
            "CUSTOMER",
        )

    def test_rejects_wrong_email_and_self_deletion(self):
        with self.assertRaisesRegex(ValueError, "이메일"):
            _validate_user_deletion(
                **{**self.BASE, "confirmation_email": "other@example.com"}
            )
        with self.assertRaisesRegex(ValueError, "자신의 계정"):
            _validate_user_deletion(
                **{**self.BASE, "target_user_id": "admin-1"}
            )

    def test_rejects_last_msp_and_customer_admin(self):
        with self.assertRaisesRegex(ValueError, "마지막 활성 MSP 관리자"):
            _validate_user_deletion(**{
                **self.BASE,
                "platform_roles": {"MSP_ADMIN"},
                "active_admin_count": 1,
            })
        with self.assertRaisesRegex(ValueError, "다른 활성 고객 관리자"):
            _validate_user_deletion(**{
                **self.BASE,
                "blocked_customer_names": ("고객사 A",),
            })

    def test_rejects_mixed_or_global_scope_and_protected_roles(self):
        with self.assertRaises(PermissionError):
            _validate_user_deletion(**{
                **self.BASE,
                "membership_environments": {"public", "gov"},
            })
        with self.assertRaises(PermissionError):
            _validate_user_deletion(**{
                **self.BASE,
                "platform_roles": {"MSP_OPERATOR"},
                "platform_environment_scopes": {None},
                "membership_environments": set(),
            })
        with self.assertRaises(PermissionError):
            _validate_user_deletion(**{
                **self.BASE,
                "platform_roles": {"MSP_OPERATOR"},
                "platform_environment_scopes": {"public"},
                "membership_environments": {"gov"},
            })
        with self.assertRaisesRegex(PermissionError, "시스템 권한"):
            _validate_user_deletion(**{
                **self.BASE,
                "platform_roles": {"SYSTEM_ADMIN"},
            })

if __name__ == "__main__":
    unittest.main()

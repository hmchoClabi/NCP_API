import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.report_branding import validate_customer_logo
from webapp.repository import (
    PortalRepository,
    _artifact_fingerprint,
    _local_report_artifact_paths,
    _preserved_legacy_analysis_policies,
    _remove_queued_artifact,
    _validate_msp_status_change,
)


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


if __name__ == "__main__":
    unittest.main()

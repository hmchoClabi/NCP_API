import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.report_branding import validate_customer_logo
from webapp.repository import (
    PortalRepository,
    _parse_kst_form_datetime,
    _remove_local_report_artifacts,
    _validate_msp_status_change,
)


class KstFormDatetimeTests(unittest.TestCase):
    def test_naive_datetime_local_is_interpreted_as_kst_and_normalized_to_utc(self):
        parsed = _parse_kst_form_datetime(
            "2026-08-20T18:00",
            "invalid",
        )

        self.assertEqual(
            parsed,
            datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc),
        )

    def test_explicit_timezone_is_preserved_as_the_same_instant(self):
        parsed = _parse_kst_form_datetime(
            "2026-08-20T18:00+09:00",
            "invalid",
        )

        self.assertEqual(
            parsed,
            datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc),
        )

    def test_invalid_datetime_uses_caller_message(self):
        with self.assertRaisesRegex(ValueError, "마감 시각 오류"):
            _parse_kst_form_datetime("not-a-date", "마감 시각 오류")


class ReportArtifactCleanupTests(unittest.TestCase):
    def test_cleanup_only_removes_local_files_below_output_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_root = root / "output"
            output_root.mkdir()
            report_file = output_root / "report.html"
            outside_file = root / "outside.html"
            report_file.write_text("report", encoding="utf-8")
            outside_file.write_text("outside", encoding="utf-8")

            with patch.dict(os.environ, {"REPORT_OUTPUT_DIR": str(output_root)}):
                removed, failed = _remove_local_report_artifacts([
                    report_file.as_uri(),
                    outside_file.as_uri(),
                    "s3://archive/report.html",
                ])

            self.assertEqual((removed, failed), (1, 0))
            self.assertFalse(report_file.exists())
            self.assertTrue(outside_file.exists())


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


class OperationalControlRepositoryTests(unittest.TestCase):
    account_id = "11111111-1111-4111-8111-111111111111"
    exception_id = "22222222-2222-4222-8222-222222222222"

    @staticmethod
    def repository_with_cursor(cursor):
        repository = PortalRepository(MagicMock())
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        connection.cursor.return_value = cursor_context
        repository._connect = MagicMock(return_value=connection)
        return repository

    @staticmethod
    def executed_statements(cursor):
        return [call.args[0] for call in cursor.execute.call_args_list]

    def assert_rls_scope_was_set(self, cursor):
        calls = cursor.execute.call_args_list
        self.assertTrue(any(
            "set_config('app.tenant_id'" in call.args[0]
            and call.args[1] == ("tenant-1",)
            for call in calls
        ))
        self.assertTrue(any(
            "set_config('app.environment_scope'" in call.args[0]
            and call.args[1] == ("public",)
            for call in calls
        ))

    def test_policy_exception_validates_and_persists_account_scope(self):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            {"environment": "public"},
            {"id": self.account_id},
        ]
        repository = self.repository_with_cursor(cursor)

        repository.create_policy_exception(
            "tenant-1",
            cloud_account_id=self.account_id,
            rule_id="SECURITY_PUBLIC_IP",
            resource_id="public-ip-1",
            reason="고객 승인",
            expires_at="2099-08-20T18:00",
            actor_id="actor-1",
        )

        self.assert_rls_scope_was_set(cursor)
        account_lookup = next(
            call for call in cursor.execute.call_args_list
            if "FROM control.cloud_accounts" in call.args[0]
        )
        self.assertEqual(account_lookup.args[1], (self.account_id, "tenant-1"))
        insert = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO control.policy_exceptions" in call.args[0]
        )
        self.assertEqual(insert.args[1][0:3], (
            "tenant-1", self.account_id, "public",
        ))

    def test_policy_exception_rejects_account_from_another_customer(self):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            {"environment": "public"},
            None,
        ]
        repository = self.repository_with_cursor(cursor)

        with self.assertRaisesRegex(ValueError, "이 고객에 속한 NCP 계정"):
            repository.create_policy_exception(
                "tenant-1",
                cloud_account_id=self.account_id,
                rule_id="SECURITY_PUBLIC_IP",
                resource_id=None,
                reason="고객 승인",
                expires_at="2099-08-20T18:00",
                actor_id="actor-1",
            )

        self.assertFalse(any(
            "INSERT INTO control.policy_exceptions" in statement
            for statement in self.executed_statements(cursor)
        ))

    def test_policy_exception_list_exposes_account_display_name(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = {"environment": "public"}
        cursor.fetchall.return_value = []
        repository = self.repository_with_cursor(cursor)

        self.assertEqual(repository.policy_exceptions("tenant-1"), [])

        self.assert_rls_scope_was_set(cursor)
        query = next(
            statement for statement in self.executed_statements(cursor)
            if "FROM control.policy_exceptions" in statement
        )
        self.assertIn("AS account_display_name", query)
        self.assertIn("LEFT JOIN control.cloud_accounts", query)

    def test_action_and_exception_mutations_set_transaction_rls_scope(self):
        list_cursor = MagicMock()
        list_cursor.fetchone.return_value = {"environment": "public"}
        list_cursor.fetchall.return_value = []
        list_repository = self.repository_with_cursor(list_cursor)
        self.assertEqual(list_repository.action_cases("tenant-1"), [])
        self.assert_rls_scope_was_set(list_cursor)

        action_cursor = MagicMock()
        action_cursor.fetchone.return_value = {"environment": "public"}
        action_cursor.rowcount = 1
        action_repository = self.repository_with_cursor(action_cursor)
        action_repository.update_action_case(
            "tenant-1",
            "case-1",
            status="IN_PROGRESS",
            assigned_to=None,
            due_at=None,
            actor_id="actor-1",
        )
        self.assert_rls_scope_was_set(action_cursor)

        exception_cursor = MagicMock()
        exception_cursor.fetchone.side_effect = [
            {"environment": "public"},
            {"rule_id": "SECURITY_PUBLIC_IP"},
        ]
        exception_repository = self.repository_with_cursor(exception_cursor)
        exception_repository.deactivate_policy_exception(
            "tenant-1",
            self.exception_id,
            "actor-1",
        )
        self.assert_rls_scope_was_set(exception_cursor)


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

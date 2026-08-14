import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.report_branding import validate_customer_logo
from webapp.repository import (
    PortalRepository,
    _preserved_legacy_analysis_policies,
    _remove_local_report_artifacts,
    _validate_msp_status_change,
)


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

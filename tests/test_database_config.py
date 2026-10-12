import tempfile
import unittest
from pathlib import Path

from database.config import DatabaseSettings


class DatabaseSettingsTests(unittest.TestCase):
    def test_disabled_database_does_not_require_password(self):
        settings = DatabaseSettings.from_env(
            environ={"REPORT_DB_ENABLED": "false"},
            project_root=Path(tempfile.gettempdir()),
        )

        self.assertFalse(settings.enabled)

    def test_process_environment_overrides_local_database_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env.db").write_text(
                "DB_HOST=localhost\nDB_MSP_APP_PASSWORD=file-password\n",
                encoding="utf-8",
            )
            settings = DatabaseSettings.from_env(
                environ={
                    "REPORT_DB_ENABLED": "true",
                    "REPORT_DB_PASSWORD": "process-password",
                    "REPORT_DB_HOST": "db.internal",
                },
                project_root=root,
            )

        self.assertEqual(settings.host, "db.internal")
        self.assertEqual(settings.password, "process-password")
        self.assertNotIn("process-password", repr(settings))
        self.assertNotIn("file-password", repr(settings))

    def test_cloud_database_url_takes_connection_precedence(self):
        url = "postgresql://app:secret@db.internal:5432/ncp_report?sslmode=require"
        settings = DatabaseSettings.from_env(
            environ={
                "REPORT_DB_ENABLED": "true",
                "REPORT_DATABASE_URL": url,
                "REPORT_DB_SSLMODE": "require",
            },
            project_root=Path(tempfile.gettempdir()),
        )

        self.assertEqual(settings.connection_kwargs()["conninfo"], url)
        self.assertNotIn("secret", repr(settings))

    def test_queue_worker_role_can_claim_jobs_without_fixed_tenant(self):
        settings = DatabaseSettings.from_env(
            environ={
                "REPORT_DB_ENABLED": "true",
                "REPORT_DB_ROLE": "public_worker",
                "REPORT_DB_PASSWORD": "not-a-real-secret",
            },
            project_root=Path(tempfile.gettempdir()),
        )

        self.assertEqual(settings.role, "public_worker")
        self.assertIsNone(settings.tenant_id)

    def test_customer_control_role_still_requires_tenant(self):
        with self.assertRaisesRegex(ValueError, "REPORT_DB_TENANT_ID"):
            DatabaseSettings.from_env(
                environ={
                    "REPORT_DB_ENABLED": "true",
                    "REPORT_DB_ROLE": "control",
                    "REPORT_DB_PASSWORD": "not-a-real-secret",
                },
                project_root=Path(tempfile.gettempdir()),
            )


if __name__ == "__main__":
    unittest.main()

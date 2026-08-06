import base64
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

from database.config import DatabaseSettings
from webapp.repository import PortalRepository
from webapp.jobs import ReportJobRepository
from webapp.security import (
    CredentialCipher,
    LocalKeyEncryptionProvider,
    verify_password,
)


@unittest.skipUnless(
    os.getenv("REPORT_DB_INTEGRATION_TEST") == "1",
    "Set REPORT_DB_INTEGRATION_TEST=1 to run against local PostgreSQL.",
)
class PortalIntegrationTests(unittest.TestCase):
    TENANT_CODE = "portal-integration"
    ADMIN_EMAIL = "portal-admin-integration@example.invalid"
    USER_EMAIL = "portal-user-integration@example.invalid"

    def setUp(self):
        self.settings = DatabaseSettings.from_env()
        self.repository = PortalRepository(self.settings)
        self.created_user_ids = []
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        import psycopg

        admin_user = os.getenv("DB_ADMIN_USER")
        admin_password = os.getenv("DB_ADMIN_PASSWORD")
        if not admin_user or not admin_password or self.settings.database_url:
            self.fail("DB admin credentials are required for integration cleanup.")
        admin_kwargs = self.settings.connection_kwargs()
        admin_kwargs.update(user=admin_user, password=admin_password)
        with psycopg.connect(**admin_kwargs) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT tenant_id
                    FROM control.report_runs
                    WHERE idempotency_key = 'portal-lifecycle-test'
                    UNION
                    SELECT id FROM control.tenants WHERE customer_code = %s
                    """,
                    (self.TENANT_CODE,),
                )
                tenant_ids = [str(row[0]) for row in cursor.fetchall()]
                if tenant_ids:
                    cursor.execute(
                        "DELETE FROM control.email_deliveries "
                        "WHERE tenant_id = ANY(%s::uuid[])",
                        (tenant_ids,),
                    )
                    cursor.execute(
                        "DELETE FROM control.report_runs "
                        "WHERE tenant_id = ANY(%s::uuid[])",
                        (tenant_ids,),
                    )
                    cursor.execute(
                        "DELETE FROM control.tenants WHERE id = ANY(%s::uuid[])",
                        (tenant_ids,),
                    )
                if self.created_user_ids:
                    cursor.execute(
                        "DELETE FROM control.users WHERE id = ANY(%s::uuid[])",
                        (self.created_user_ids,),
                    )
                cursor.execute(
                    "DELETE FROM control.users WHERE email IN (%s, %s)",
                    (self.ADMIN_EMAIL, self.USER_EMAIL),
                )
                cursor.execute(
                    "DELETE FROM control.customer_deletion_tombstones "
                    "WHERE archive_reference = 'TEST-ARCHIVE-001' "
                    "OR customer_code_hash = %s",
                    (
                        sha256(
                            self.TENANT_CODE.casefold().encode("utf-8")
                        ).hexdigest(),
                    ),
                )

    def test_users_multi_account_and_encrypted_credentials(self):
        tenant_id = self.repository.create_tenant(
            self.TENANT_CODE, "Portal Integration", "public", "KR"
        )
        admin_id = self.repository.bootstrap_msp_admin(
            self.ADMIN_EMAIL, "integration admin password", "Portal Admin"
        )
        customer_user_id = self.repository.create_customer_user(
            self.USER_EMAIL,
            "integration customer password",
            "Portal Customer",
            self.TENANT_CODE,
        )
        self.created_user_ids.extend([admin_id, customer_user_id])
        tenant_users = self.repository.users_for_tenant(tenant_id)
        self.assertEqual([str(item["id"]) for item in tenant_users], [customer_user_id])
        self.assertEqual(tenant_users[0]["role"], "CUSTOMER_VIEWER")
        self.repository.assign_customer_membership(
            customer_user_id, tenant_id, "CUSTOMER_ADMIN"
        )
        tenant_users = self.repository.users_for_tenant(tenant_id)
        self.assertEqual(tenant_users[0]["role"], "CUSTOMER_ADMIN")
        global_users = self.repository.customer_users()
        customer_user = next(
            item for item in global_users if str(item["id"]) == customer_user_id
        )
        self.assertEqual(customer_user["memberships"][0]["customer_name"], "Portal Integration")
        authenticated = self.repository.authenticate(self.ADMIN_EMAIL)
        self.assertTrue(
            verify_password(authenticated["password_hash"], "integration admin password")
        )

        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "master.key"
            key_path.write_text(
                base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
                encoding="ascii",
            )
            cipher = CredentialCipher(LocalKeyEncryptionProvider(key_path))
            account_id = self.repository.register_account_credential(
                tenant_id,
                "primary",
                "Primary account",
                "PORTAL-ACCESS-KEY",
                "PORTAL-SECRET-KEY",
                cipher,
                admin_id,
            )
            customer, credentials = self.repository.account_credentials(
                account_id, cipher
            )

        self.assertEqual(customer.customer_id, self.TENANT_CODE)
        self.assertEqual(customer.cloud_account_id, account_id)
        self.assertEqual(credentials.access_key, "PORTAL-ACCESS-KEY")
        self.assertEqual(credentials.secret_key, "PORTAL-SECRET-KEY")

        import psycopg

        with psycopg.connect(**self.settings.connection_kwargs()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT ciphertext, access_key_hint
                    FROM control.encrypted_credentials
                    WHERE cloud_account_id = %s
                    """,
                    (account_id,),
                )
                ciphertext, hint = cursor.fetchone()
        self.assertNotIn(b"PORTAL-SECRET-KEY", ciphertext)
        self.assertEqual(hint, "***-KEY")

        job_id = ReportJobRepository(self.settings).enqueue(
            account_id, "DAILY", "2026-08-01", admin_id
        )
        events = self.repository.notification_events(
            [tenant_id], datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        self.assertTrue(any(
            str(event["id"]) == job_id and event["status"] == "QUEUED"
            for event in events
        ))

        deleted_name = self.repository.delete_account_credential(
            tenant_id, account_id, admin_id
        )
        self.assertEqual(deleted_name, "Primary account")
        detail = self.repository.tenant_detail(tenant_id)
        self.assertEqual(detail["accounts"][0]["status"], "DISABLED")
        self.assertIsNone(detail["accounts"][0]["credential_status"])
        cancelled = self.repository.jobs_for_tenants([tenant_id])
        self.assertEqual(cancelled[0]["status"], "CANCELLED")

        offboarded_name = self.repository.offboard_tenant(tenant_id, admin_id)
        self.assertEqual(offboarded_name, "Portal Integration")
        self.assertEqual(self.repository.tenant_detail(tenant_id)["status"], "OFFBOARDED")

        reactivated_name = self.repository.reactivate_tenant(tenant_id, admin_id)
        self.assertEqual(reactivated_name, "Portal Integration")
        self.assertEqual(self.repository.tenant_detail(tenant_id)["status"], "ACTIVE")
        self.repository.assign_customer_membership(
            customer_user_id, tenant_id, "CUSTOMER_VIEWER"
        )
        self.repository.offboard_tenant(tenant_id, admin_id)

        with psycopg.connect(**self.settings.connection_kwargs()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO control.report_runs (
                        tenant_id, environment, report_type, period_start,
                        period_end, status, trigger_type, idempotency_key,
                        cloud_account_id
                    ) VALUES (
                        %s, 'public', 'DAILY', %s, %s, 'SUCCESS', 'MANUAL',
                        'portal-lifecycle-test', %s
                    ) RETURNING id
                    """,
                    (
                        tenant_id,
                        datetime(2026, 8, 1, tzinfo=timezone.utc),
                        datetime(2026, 8, 2, tzinfo=timezone.utc),
                        account_id,
                    ),
                )
                report_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO public_data.report_snapshots (
                        report_run_id, tenant_id, schema_version, normalized_data
                    ) VALUES (%s, %s, '1.0', %s::jsonb)
                    """,
                    (
                        report_id,
                        tenant_id,
                        json.dumps({
                            "period": {"file_suffix": "test"},
                            "customer": {
                                "id": self.TENANT_CODE,
                                "name": "Portal Integration",
                            },
                            "activity_events": [{
                                "user_name": "customer-person",
                                "action": "Login",
                            }],
                        }),
                    ),
                )

        anonymous_name = self.repository.anonymize_tenant(tenant_id, admin_id)
        detail = self.repository.tenant_detail(tenant_id)
        self.assertEqual(detail["customer_name"], anonymous_name)
        self.assertTrue(detail["metadata"]["irreversible"])
        self.assertEqual(detail["accounts"][0]["display_name"], "익명 계정 1")
        self.assertEqual(self.repository.users_for_tenant(tenant_id), [])
        with psycopg.connect(**self.settings.connection_kwargs()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT normalized_data FROM public_data.report_snapshots "
                    "WHERE report_run_id = %s",
                    (report_id,),
                )
                snapshot = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT email, display_name, status FROM control.users WHERE id = %s",
                    (customer_user_id,),
                )
                anonymized_user = cursor.fetchone()
        self.assertEqual(snapshot["customer"]["name"], anonymous_name)
        self.assertEqual(
            snapshot["activity_events"][0]["user_name"], "[익명화됨]"
        )
        self.assertTrue(anonymized_user[0].endswith("@deleted.invalid"))
        self.assertEqual(anonymized_user[1:], ("익명 사용자", "DISABLED"))

        with self.assertRaisesRegex(ValueError, "외부 보관 참조"):
            self.repository.permanently_delete_tenant(tenant_id, admin_id)
        deleted_name, report_count = self.repository.permanently_delete_tenant(
            tenant_id, admin_id, force=True
        )
        self.assertEqual(deleted_name, anonymous_name)
        self.assertEqual(report_count, 1)
        self.assertIsNone(self.repository.tenant_detail(tenant_id))
        with psycopg.connect(**self.settings.connection_kwargs()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT report_count, forced, archive_reference "
                    "FROM control.customer_deletion_tombstones "
                    "WHERE customer_code_hash = %s",
                    (
                        sha256(
                            self.TENANT_CODE.casefold().encode("utf-8")
                        ).hexdigest(),
                    ),
                )
                self.assertEqual(cursor.fetchone(), (1, True, None))


if __name__ == "__main__":
    unittest.main()

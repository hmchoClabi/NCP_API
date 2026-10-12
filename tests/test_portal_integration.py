import base64
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from app.report_branding import validate_customer_logo
from database.config import DatabaseSettings
from webapp.repository import PortalRepository
from webapp.jobs import ReportJobRepository
from webapp.security import (
    CredentialCipher,
    LocalKeyEncryptionProvider,
    verify_password,
)


@pytest.mark.integration
class PortalIntegrationTests(unittest.TestCase):
    TENANT_CODE = "portal-integration"
    ADMIN_EMAIL = "portal-admin-integration@example.invalid"
    SECOND_ADMIN_EMAIL = "portal-admin-2-integration@example.invalid"
    OPERATOR_EMAIL = "portal-operator-integration@example.invalid"
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
                        "DELETE FROM control.email_deliveries WHERE tenant_id = ANY(%s::uuid[])",
                        (tenant_ids,),
                    )
                    cursor.execute(
                        "DELETE FROM control.report_runs WHERE tenant_id = ANY(%s::uuid[])",
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
                    "DELETE FROM control.users WHERE email = ANY(%s)",
                    (
                        [
                            self.ADMIN_EMAIL,
                            self.SECOND_ADMIN_EMAIL,
                            self.OPERATOR_EMAIL,
                            self.USER_EMAIL,
                        ],
                    ),
                )
                cursor.execute(
                    "DELETE FROM control.customer_deletion_tombstones "
                    "WHERE archive_reference = 'TEST-ARCHIVE-001' "
                    "OR customer_code_hash = %s",
                    (sha256(self.TENANT_CODE.casefold().encode("utf-8")).hexdigest(),),
                )

    def test_msp_accounts_are_created_listed_and_independently_disabled(self):
        admin_id = self.repository.bootstrap_msp_admin(
            self.ADMIN_EMAIL,
            "integration admin password",
            "Portal Admin",
        )
        second_admin_id = self.repository.create_msp_user(
            self.SECOND_ADMIN_EMAIL,
            "integration second admin password",
            "Second Admin",
            "MSP_ADMIN",
            actor_id=admin_id,
        )
        operator_id = self.repository.create_msp_user(
            self.OPERATOR_EMAIL,
            "integration operator password",
            "Portal Operator",
            "MSP_OPERATOR",
            actor_id=admin_id,
        )
        self.created_user_ids.extend([admin_id, second_admin_id, operator_id])

        users = self.repository.msp_users()
        managed_ids = {
            str(user["id"])
            for user in users
            if user["email"]
            in {
                self.ADMIN_EMAIL,
                self.SECOND_ADMIN_EMAIL,
                self.OPERATOR_EMAIL,
            }
        }
        self.assertEqual(
            managed_ids,
            {admin_id, second_admin_id, operator_id},
        )

        session_token, _ = self.repository.create_session(operator_id)
        self.assertIsNotNone(self.repository.session_user(session_token))
        self.repository.set_msp_user_enabled(operator_id, admin_id, False)
        self.assertIsNone(self.repository.session_user(session_token))
        self.assertEqual(
            self.repository.authenticate(self.OPERATOR_EMAIL)["status"],
            "DISABLED",
        )
        self.repository.set_msp_user_enabled(operator_id, admin_id, True)
        self.assertEqual(
            self.repository.authenticate(self.OPERATOR_EMAIL)["status"],
            "ACTIVE",
        )
        with self.assertRaisesRegex(ValueError, "자신의 MSP 계정"):
            self.repository.set_msp_user_enabled(admin_id, admin_id, False)

    def test_msp_and_customer_user_deletion_revokes_access_and_reuses_email(self):
        tenant_id = self.repository.create_tenant(
            self.TENANT_CODE, "Portal Integration", "public", "KR"
        )
        admin_id = self.repository.bootstrap_msp_admin(
            self.ADMIN_EMAIL,
            "integration admin password",
            "Portal Admin",
        )
        second_admin_id = self.repository.create_msp_user(
            self.SECOND_ADMIN_EMAIL,
            "integration second admin password",
            "Second Admin",
            "MSP_ADMIN",
            actor_id=admin_id,
        )
        operator_id = self.repository.create_msp_user(
            self.OPERATOR_EMAIL,
            "integration operator password",
            "Portal Operator",
            "MSP_OPERATOR",
            actor_id=admin_id,
        )
        customer_user_id = self.repository.create_customer_user(
            self.USER_EMAIL,
            "integration customer password",
            "Portal Customer",
            self.TENANT_CODE,
        )
        self.created_user_ids.extend(
            [
                admin_id,
                second_admin_id,
                operator_id,
                customer_user_id,
            ]
        )
        operator_session, _ = self.repository.create_session(operator_id)
        customer_session, _ = self.repository.create_session(customer_user_id)
        self.repository.log_authentication(
            self.USER_EMAIL,
            "DENIED",
            failure_reason="INVALID_CREDENTIALS",
        )
        self.repository.set_msp_user_enabled(admin_id, second_admin_id, False)
        with self.assertRaises(PermissionError):
            self.repository.delete_user_account(operator_id, admin_id, self.OPERATOR_EMAIL)
        self.repository.set_msp_user_enabled(admin_id, second_admin_id, True)

        self.assertEqual(
            self.repository.delete_user_account(operator_id, admin_id, self.OPERATOR_EMAIL),
            ("Portal Operator", "MSP"),
        )
        self.assertEqual(
            self.repository.delete_user_account(customer_user_id, admin_id, self.USER_EMAIL),
            ("Portal Customer", "CUSTOMER"),
        )

        self.assertIsNone(self.repository.session_user(operator_session))
        self.assertIsNone(self.repository.session_user(customer_session))
        self.assertIsNone(self.repository.authenticate(self.OPERATOR_EMAIL))
        self.assertIsNone(self.repository.authenticate(self.USER_EMAIL))
        self.assertNotIn(
            operator_id,
            {str(item["id"]) for item in self.repository.msp_users()},
        )
        self.assertNotIn(
            customer_user_id,
            {str(item["id"]) for item in self.repository.customer_users()},
        )

        with self.repository._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, email, display_name, status, password_hash,
                       mfa_enabled
                FROM control.users
                WHERE id = ANY(%s::uuid[])
                ORDER BY id
                """,
                ([operator_id, customer_user_id],),
            )
            deleted_users = cursor.fetchall()
            self.assertEqual(len(deleted_users), 2)
            for user in deleted_users:
                self.assertTrue(user["email"].endswith("@deleted.invalid"))
                self.assertEqual(user["display_name"], "익명 사용자")
                self.assertEqual(user["status"], "DISABLED")
                self.assertEqual(user["password_hash"], "!anonymized!")
                self.assertFalse(user["mfa_enabled"])
            cursor.execute(
                """
                SELECT count(*) AS access_count
                FROM (
                    SELECT user_id FROM control.platform_roles
                    WHERE user_id = ANY(%s::uuid[])
                    UNION ALL
                    SELECT user_id FROM control.memberships
                    WHERE user_id = ANY(%s::uuid[])
                    UNION ALL
                    SELECT user_id FROM control.user_sessions
                    WHERE user_id = ANY(%s::uuid[])
                ) removed_access
                """,
                (
                    [operator_id, customer_user_id],
                    [operator_id, customer_user_id],
                    [operator_id, customer_user_id],
                ),
            )
            self.assertEqual(cursor.fetchone()["access_count"], 0)
            cursor.execute(
                """
                SELECT count(*) AS deletion_count
                FROM audit.data_change_logs
                WHERE table_name = 'control.users'
                  AND operation = 'DELETE'
                  AND record_id = ANY(%s)
                """,
                ([operator_id, customer_user_id],),
            )
            self.assertEqual(cursor.fetchone()["deletion_count"], 2)
            cursor.execute(
                """
                SELECT count(*) AS redacted_count
                FROM audit.authentication_logs
                WHERE email_attempted = 'redacted@deleted.invalid'
                  AND failure_reason IS NULL
                """
            )
            self.assertGreaterEqual(cursor.fetchone()["redacted_count"], 1)

        replacement_operator_id = self.repository.create_msp_user(
            self.OPERATOR_EMAIL,
            "replacement operator password",
            "Replacement Operator",
            "MSP_OPERATOR",
            actor_id=admin_id,
        )
        replacement_customer_id = self.repository.create_customer_user(
            self.USER_EMAIL,
            "replacement customer password",
            "Replacement Customer",
            self.TENANT_CODE,
        )
        self.created_user_ids.extend(
            [
                replacement_operator_id,
                replacement_customer_id,
            ]
        )
        self.assertNotEqual(replacement_operator_id, operator_id)
        self.assertNotEqual(replacement_customer_id, customer_user_id)

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
        self.repository.assign_customer_membership(customer_user_id, tenant_id, "CUSTOMER_ADMIN")
        tenant_users = self.repository.users_for_tenant(tenant_id)
        self.assertEqual(tenant_users[0]["role"], "CUSTOMER_ADMIN")
        with self.assertRaisesRegex(ValueError, "다른 활성 고객 관리자"):
            self.repository.assign_customer_membership(
                customer_user_id, tenant_id, "CUSTOMER_VIEWER"
            )
        global_users = self.repository.customer_users()
        customer_user = next(item for item in global_users if str(item["id"]) == customer_user_id)
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
            self.repository.update_tenant_report_settings(
                tenant_id,
                {
                    "sections": ["billing"],
                    "resource_categories": ["SERVER"],
                    "monitoring_categories": [],
                },
                admin_id,
            )
            logo = validate_customer_logo(
                b"\x89PNG\r\n\x1a\n"
                + (13).to_bytes(4, "big")
                + b"IHDR"
                + (320).to_bytes(4, "big")
                + (120).to_bytes(4, "big")
                + b"\x08\x06\x00\x00\x00\x00\x00\x00\x00",
                "image/png",
            )
            self.repository.update_tenant_logo(tenant_id, logo, admin_id)
            customer, credentials = self.repository.account_credentials(account_id, cipher)

        self.assertEqual(customer.customer_id, self.TENANT_CODE)
        self.assertEqual(customer.cloud_account_id, account_id)
        self.assertTrue(customer.report_options.section_enabled("billing"))
        self.assertFalse(customer.report_options.section_enabled("activity_history"))
        self.assertEqual(customer.logo_data_uri, logo.data_uri)
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
        self.assertTrue(
            any(str(event["id"]) == job_id and event["status"] == "QUEUED" for event in events)
        )

        deleted_name = self.repository.delete_account_credential(tenant_id, account_id, admin_id)
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
        self.repository.assign_customer_membership(customer_user_id, tenant_id, "CUSTOMER_VIEWER")
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
                        json.dumps(
                            {
                                "period": {"file_suffix": "test"},
                                "customer": {
                                    "id": self.TENANT_CODE,
                                    "name": "Portal Integration",
                                },
                                "activity_events": [
                                    {
                                        "user_name": "customer-person",
                                        "action": "Login",
                                    }
                                ],
                            }
                        ),
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
        self.assertEqual(snapshot["activity_events"][0]["user_name"], "[익명화됨]")
        self.assertTrue(anonymized_user[0].endswith("@deleted.invalid"))
        self.assertEqual(anonymized_user[1:], ("익명 사용자", "DISABLED"))

        with self.assertRaisesRegex(ValueError, "외부 보관 참조"):
            self.repository.permanently_delete_tenant(tenant_id, admin_id)
        deleted_name, report_count = self.repository.permanently_delete_tenant(
            tenant_id, admin_id, "archive://portal-integration/report"
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
                    (sha256(self.TENANT_CODE.casefold().encode("utf-8")).hexdigest(),),
                )
                self.assertEqual(
                    cursor.fetchone(),
                    (1, False, "archive://portal-integration/report"),
                )


if __name__ == "__main__":
    unittest.main()

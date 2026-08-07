from __future__ import annotations

import json
import re
import secrets
from hashlib import sha256
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from psycopg.rows import dict_row

from database.config import DatabaseSettings
from webapp.security import CredentialCipher, hash_password, token_hash
from utils.credentials import NCPCredentials
from app.customer import CustomerProfile


_ANONYMIZED_VALUE = "[익명화됨]"
_PERSONAL_DATA_KEYS = {
    "account_name", "actor", "actor_id", "email", "email_address",
    "member_no", "member_number", "user", "user_id", "user_name",
}


def _anonymize_report_payload(value: Any, customer: dict[str, Any]) -> Any:
    if isinstance(value, list):
        return [_anonymize_report_payload(item, customer) for item in value]
    if not isinstance(value, dict):
        return value
    anonymized: dict[str, Any] = {}
    for key, item in value.items():
        normalized_key = str(key).casefold()
        if normalized_key == "customer":
            anonymized[key] = customer
        elif normalized_key in _PERSONAL_DATA_KEYS:
            anonymized[key] = _ANONYMIZED_VALUE
        else:
            anonymized[key] = _anonymize_report_payload(item, customer)
    return anonymized


def _validate_user_fields(email: str, display_name: str) -> tuple[str, str]:
    email = email.strip().casefold()
    display_name = display_name.strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 320:
        raise ValueError("A valid email address is required.")
    if not display_name or len(display_name) > 200:
        raise ValueError("Display name must contain 1-200 characters.")
    return email, display_name


class PortalRepository:
    def __init__(self, settings: DatabaseSettings):
        self.settings = settings

    def _connect(self):
        import psycopg

        return psycopg.connect(
            **self.settings.connection_kwargs(),
            row_factory=dict_row,
        )

    def authenticate(self, email: str) -> Optional[dict[str, Any]]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, email, password_hash, display_name, status
                FROM control.users
                WHERE lower(email) = lower(%s)
                """,
                (email.strip(),),
            )
            return cursor.fetchone()

    def user_context(self, user_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, email, display_name, status
                FROM control.users WHERE id = %s
                """,
                (user_id,),
            )
            user = cursor.fetchone()
            if not user or user["status"] != "ACTIVE":
                return None
            cursor.execute(
                "SELECT role FROM control.platform_roles WHERE user_id = %s",
                (user_id,),
            )
            user["platform_roles"] = [row["role"] for row in cursor.fetchall()]
            cursor.execute(
                """
                SELECT membership.tenant_id, membership.role,
                       tenant.customer_code, tenant.customer_name,
                       tenant.environment
                FROM control.memberships membership
                JOIN control.tenants tenant ON tenant.id = membership.tenant_id
                WHERE membership.user_id = %s AND membership.status = 'ACTIVE'
                ORDER BY tenant.customer_name
                """,
                (user_id,),
            )
            user["memberships"] = cursor.fetchall()
            return user

    def create_session(self, user_id: str, hours: int = 12) -> tuple[str, str]:
        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM control.user_sessions WHERE expires_at <= clock_timestamp()"
            )
            cursor.execute(
                """
                INSERT INTO control.user_sessions (
                    user_id, token_hash, csrf_token_hash, expires_at
                ) VALUES (%s, %s, %s, %s)
                """,
                (user_id, token_hash(session_token), token_hash(csrf_token), expires_at),
            )
        return session_token, csrf_token

    def session_user(self, session_token: str) -> Optional[dict[str, Any]]:
        if not session_token:
            return None
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id, csrf_token_hash
                FROM control.user_sessions
                WHERE token_hash = %s AND expires_at > clock_timestamp()
                """,
                (token_hash(session_token),),
            )
            session = cursor.fetchone()
            if not session:
                return None
            cursor.execute(
                """
                UPDATE control.user_sessions
                SET last_seen_at = clock_timestamp()
                WHERE token_hash = %s
                """,
                (token_hash(session_token),),
            )
        user = self.user_context(str(session["user_id"]))
        if user:
            user["csrf_token_hash"] = session["csrf_token_hash"]
        return user

    def revoke_session(self, session_token: str) -> None:
        if not session_token:
            return
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM control.user_sessions WHERE token_hash = %s",
                (token_hash(session_token),),
            )

    def log_authentication(
        self,
        email: str,
        result: str,
        user_id: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO audit.authentication_logs (
                    user_id, email_attempted, event_type, result, failure_reason
                ) VALUES (%s, %s, 'LOGIN', %s, %s)
                """,
                (user_id, email[:320], result, failure_reason),
            )

    def bootstrap_msp_admin(self, email: str, password: str, display_name: str) -> str:
        password_hash = hash_password(password)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO control.users (
                    email, password_hash, display_name, status
                ) VALUES (%s, %s, %s, 'ACTIVE')
                ON CONFLICT ((lower(email))) DO UPDATE SET
                    password_hash = EXCLUDED.password_hash,
                    display_name = EXCLUDED.display_name,
                    status = 'ACTIVE'
                RETURNING id
                """,
                (email.strip().casefold(), password_hash, display_name.strip()),
            )
            user_id = cursor.fetchone()["id"]
            cursor.execute(
                """
                INSERT INTO control.platform_roles (user_id, role)
                VALUES (%s, 'MSP_ADMIN')
                ON CONFLICT DO NOTHING
                """,
                (user_id,),
            )
        return str(user_id)

    def create_customer_user(
        self,
        email: str,
        password: str,
        display_name: str,
        tenant_code: str,
        role: str = "CUSTOMER_VIEWER",
    ) -> str:
        if role not in {"CUSTOMER_VIEWER", "CUSTOMER_ADMIN"}:
            raise ValueError("Unsupported customer role.")
        email = email.strip().casefold()
        display_name = display_name.strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 320:
            raise ValueError("A valid email address is required.")
        if not display_name or len(display_name) > 200:
            raise ValueError("Display name must contain 1-200 characters.")
        password_hash = hash_password(password)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM control.tenants WHERE customer_code = %s",
                (tenant_code,),
            )
            tenant = cursor.fetchone()
            if not tenant:
                raise ValueError("Customer code was not found.")
            cursor.execute(
                """
                INSERT INTO control.users (email, password_hash, display_name, status)
                VALUES (%s, %s, %s, 'ACTIVE')
                ON CONFLICT ((lower(email))) DO UPDATE SET
                    password_hash = EXCLUDED.password_hash,
                    display_name = EXCLUDED.display_name,
                    status = 'ACTIVE'
                RETURNING id
                """,
                (email, password_hash, display_name),
            )
            user_id = cursor.fetchone()["id"]
            cursor.execute(
                """
                INSERT INTO control.memberships (tenant_id, user_id, role, status)
                VALUES (%s, %s, %s, 'ACTIVE')
                ON CONFLICT (tenant_id, user_id) DO UPDATE SET
                    role = EXCLUDED.role, status = 'ACTIVE'
                """,
                (tenant["id"], user_id, role),
            )
            cursor.execute(
                "DELETE FROM control.user_sessions WHERE user_id = %s",
                (user_id,),
            )
        return str(user_id)

    def create_portal_user(
        self, email: str, password: str, display_name: str
    ) -> str:
        email, display_name = _validate_user_fields(email, display_name)
        password_hash = hash_password(password)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM control.users WHERE lower(email) = lower(%s)",
                (email,),
            )
            if cursor.fetchone():
                raise ValueError("이미 등록된 이메일입니다.")
            cursor.execute(
                """
                INSERT INTO control.users (
                    email, password_hash, display_name, status
                ) VALUES (%s, %s, %s, 'INVITED')
                RETURNING id
                """,
                (email, password_hash, display_name),
            )
            return str(cursor.fetchone()["id"])

    def assign_customer_membership(
        self, user_id: str, tenant_id: str, role: str
    ) -> None:
        if role not in {"CUSTOMER_VIEWER", "CUSTOMER_ADMIN"}:
            raise ValueError("지원하지 않는 고객 권한입니다.")
        try:
            user_id = str(UUID(user_id))
            tenant_id = str(UUID(tenant_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("사용자 또는 고객 식별자가 올바르지 않습니다.") from exc
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT users.id
                FROM control.users users
                WHERE users.id = %s
                  AND NOT EXISTS (
                      SELECT 1 FROM control.platform_roles role
                      WHERE role.user_id = users.id
                  )
                """,
                (user_id,),
            )
            if not cursor.fetchone():
                raise ValueError("연결할 고객 사용자를 찾을 수 없습니다.")
            cursor.execute(
                "SELECT id FROM control.tenants WHERE id = %s AND status <> 'OFFBOARDED'",
                (tenant_id,),
            )
            if not cursor.fetchone():
                raise ValueError("연결할 고객사를 찾을 수 없습니다.")
            cursor.execute(
                """
                INSERT INTO control.memberships (tenant_id, user_id, role, status)
                VALUES (%s, %s, %s, 'ACTIVE')
                ON CONFLICT (tenant_id, user_id) DO UPDATE SET
                    role = EXCLUDED.role, status = 'ACTIVE'
                """,
                (tenant_id, user_id, role),
            )
            cursor.execute(
                """
                UPDATE control.users SET status = 'ACTIVE'
                WHERE id = %s AND status = 'INVITED'
                """,
                (user_id,),
            )

    def customer_users(self) -> list[dict[str, Any]]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT users.id, users.email, users.display_name,
                       users.status AS user_status, users.last_login_at,
                       users.created_at, membership.tenant_id, membership.role,
                       membership.status AS membership_status,
                       tenant.customer_name, tenant.environment
                FROM control.users users
                LEFT JOIN control.memberships membership
                    ON membership.user_id = users.id
                LEFT JOIN control.tenants tenant
                    ON tenant.id = membership.tenant_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM control.platform_roles role
                    WHERE role.user_id = users.id
                )
                ORDER BY users.display_name, users.email, tenant.customer_name
                """
            )
            users_by_id: dict[str, dict[str, Any]] = {}
            for row in cursor.fetchall():
                user_id = str(row["id"])
                user = users_by_id.setdefault(user_id, {
                    "id": row["id"],
                    "email": row["email"],
                    "display_name": row["display_name"],
                    "user_status": row["user_status"],
                    "last_login_at": row["last_login_at"],
                    "created_at": row["created_at"],
                    "memberships": [],
                })
                if row["tenant_id"]:
                    user["memberships"].append({
                        "tenant_id": row["tenant_id"],
                        "customer_name": row["customer_name"],
                        "environment": row["environment"],
                        "role": row["role"],
                        "status": row["membership_status"],
                    })
            return list(users_by_id.values())

    def users_for_tenant(self, tenant_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT users.id, users.email, users.display_name,
                       users.status AS user_status, membership.role,
                       membership.status AS membership_status,
                       membership.created_at
                FROM control.memberships membership
                JOIN control.users users ON users.id = membership.user_id
                WHERE membership.tenant_id = %s
                ORDER BY users.display_name, users.email
                """,
                (tenant_id,),
            )
            return cursor.fetchall()

    def create_tenant(
        self, customer_code: str, customer_name: str, environment: str, region: str
    ) -> str:
        customer_code = customer_code.strip().casefold()
        customer_name = customer_name.strip()
        environment = environment.strip().casefold()
        region = region.strip().upper()
        if environment not in {"public", "gov"}:
            raise ValueError("Environment must be public or gov.")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,78}[a-z0-9]", customer_code):
            raise ValueError("Customer code must use 3-80 lowercase letters, numbers, _ or -.")
        if not customer_name:
            raise ValueError("Customer name is required.")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO control.tenants (
                    customer_code, customer_name, environment, region
                ) VALUES (%s, %s, %s, %s)
                ON CONFLICT (customer_code) DO UPDATE SET
                    customer_name = EXCLUDED.customer_name,
                    region = EXCLUDED.region,
                    status = 'ACTIVE'
                WHERE control.tenants.environment = EXCLUDED.environment
                RETURNING id
                """,
                (customer_code, customer_name, environment, region),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("Customer code already belongs to another environment.")
            return str(row["id"])

    def dashboard(self) -> dict[str, Any]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*) AS customer_count,
                       count(*) FILTER (WHERE environment = 'public') AS public_count,
                       count(*) FILTER (WHERE environment = 'gov') AS gov_count
                FROM control.tenants WHERE status <> 'OFFBOARDED'
                """
            )
            summary = cursor.fetchone()
            cursor.execute(
                """
                SELECT DISTINCT ON (tenant_id)
                       tenant_id, customer_code, customer_name, environment,
                       fact_date, collection_status, critical_count, warning_count,
                       activity_failure_count, collection_error_count, updated_at
                FROM control.v_msp_customer_daily_status
                ORDER BY tenant_id, fact_date DESC NULLS LAST
                """
            )
            customers = cursor.fetchall()
        issue_customers = [
            row for row in customers
            if row["collection_status"] not in (None, "SUCCESS")
            or (row["critical_count"] or 0) > 0
            or (row["warning_count"] or 0) > 0
            or (row["activity_failure_count"] or 0) > 0
            or (row["collection_error_count"] or 0) > 0
            or row["fact_date"] is None
        ]
        summary["issue_count"] = len(issue_customers)
        return {"summary": summary, "issue_customers": issue_customers}

    def tenants(self, environment: Optional[str] = None) -> list[dict[str, Any]]:
        parameters: tuple[Any, ...] = ()
        condition = ""
        if environment in {"public", "gov"}:
            condition = "WHERE tenant.environment = %s"
            parameters = (environment,)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT tenant.id, tenant.customer_code, tenant.customer_name,
                       tenant.environment, tenant.region, tenant.status,
                       count(DISTINCT account.id) AS account_count,
                       count(DISTINCT report.id) AS report_count
                FROM control.tenants tenant
                LEFT JOIN control.cloud_accounts account ON account.tenant_id = tenant.id
                LEFT JOIN control.report_runs report ON report.tenant_id = tenant.id
                {condition}
                GROUP BY tenant.id
                ORDER BY tenant.customer_name
                """,
                parameters,
            )
            return cursor.fetchall()

    def tenant_detail(self, tenant_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM control.tenants WHERE id = %s", (tenant_id,))
            tenant = cursor.fetchone()
            if not tenant:
                return None
            cursor.execute(
                """
                SELECT account.*,
                       credential.status AS credential_status,
                       credential.access_key_hint,
                       credential.credential_version,
                       credential.rotated_at
                FROM control.cloud_accounts account
                LEFT JOIN control.encrypted_credentials credential
                    ON credential.cloud_account_id = account.id
                WHERE account.tenant_id = %s
                ORDER BY account.display_name
                """,
                (tenant_id,),
            )
            tenant["accounts"] = cursor.fetchall()
            cursor.execute(
                """
                SELECT *, (next_run_at AT TIME ZONE timezone) AS next_run_local
                FROM control.account_report_schedules
                WHERE tenant_id = %s ORDER BY cloud_account_id, report_type
                """,
                (tenant_id,),
            )
            schedules = cursor.fetchall()
            schedules_by_account: dict[str, list[dict[str, Any]]] = {}
            for schedule in schedules:
                schedules_by_account.setdefault(
                    str(schedule["cloud_account_id"]), []
                ).append(schedule)
            for account in tenant["accounts"]:
                account["schedules"] = schedules_by_account.get(
                    str(account["id"]), []
                )
            tenant["reports"] = self._report_rows(cursor, tenant_id)
            return tenant

    def account_tenant(self, account_id: str) -> Optional[str]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT tenant_id FROM control.cloud_accounts WHERE id = %s",
                (account_id,),
            )
            row = cursor.fetchone()
            return str(row["tenant_id"]) if row else None

    def accounts_for_tenants(self, tenant_ids: list[str]) -> list[dict[str, Any]]:
        if not tenant_ids:
            return []
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT account.id, account.tenant_id, account.account_code,
                       account.display_name, account.environment,
                       tenant.customer_name, credential.status AS credential_status
                FROM control.cloud_accounts account
                JOIN control.tenants tenant ON tenant.id = account.tenant_id
                LEFT JOIN control.encrypted_credentials credential
                    ON credential.cloud_account_id = account.id
                WHERE account.tenant_id = ANY(%s::uuid[])
                ORDER BY tenant.customer_name, account.display_name
                """,
                (tenant_ids,),
            )
            accounts = cursor.fetchall()
            cursor.execute(
                """
                SELECT *, (next_run_at AT TIME ZONE timezone) AS next_run_local
                FROM control.account_report_schedules
                WHERE tenant_id = ANY(%s::uuid[])
                ORDER BY cloud_account_id, report_type
                """,
                (tenant_ids,),
            )
            schedules_by_account: dict[str, list[dict[str, Any]]] = {}
            for schedule in cursor.fetchall():
                schedules_by_account.setdefault(
                    str(schedule["cloud_account_id"]), []
                ).append(schedule)
            for account in accounts:
                account["schedules"] = schedules_by_account.get(
                    str(account["id"]), []
                )
            return accounts

    def reports_for_tenants(self, tenant_ids: list[str]) -> list[dict[str, Any]]:
        if not tenant_ids:
            return []
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT report.id, report.tenant_id, tenant.customer_name,
                       account.display_name AS account_name,
                       report.report_type, report.period_start, report.period_end,
                       report.end_exclusive,
                       report.status, report.error_count, report.created_at,
                       report.completed_at,
                       CASE
                           WHEN report.started_at IS NULL THEN NULL
                           ELSE GREATEST(EXTRACT(EPOCH FROM (
                               COALESCE(report.completed_at, clock_timestamp())
                               - report.started_at
                           )), 0)::bigint
                       END AS execution_seconds
                FROM control.report_runs report
                JOIN control.tenants tenant ON tenant.id = report.tenant_id
                LEFT JOIN control.cloud_accounts account
                    ON account.id = report.cloud_account_id
                WHERE report.tenant_id = ANY(%s::uuid[])
                ORDER BY report.created_at DESC, report.id DESC
                LIMIT 100
                """,
                (tenant_ids,),
            )
            return cursor.fetchall()

    def report_detail(self, report_id: str, allowed_tenants: Optional[list[str]]) -> Optional[dict[str, Any]]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT report.*, tenant.customer_name, tenant.environment,
                       account.display_name AS account_name
                FROM control.report_runs report
                JOIN control.tenants tenant ON tenant.id = report.tenant_id
                LEFT JOIN control.cloud_accounts account ON account.id = report.cloud_account_id
                WHERE report.id = %s
                """,
                (report_id,),
            )
            report = cursor.fetchone()
            if not report:
                return None
            if allowed_tenants is not None and str(report["tenant_id"]) not in allowed_tenants:
                return None
            schema = "public_data" if report["environment"] == "public" else "gov_data"
            cursor.execute(
                f"SELECT normalized_data FROM {schema}.report_snapshots WHERE report_run_id = %s",
                (report_id,),
            )
            snapshot = cursor.fetchone()
            report["snapshot"] = snapshot["normalized_data"] if snapshot else {}
            return report

    def jobs_for_tenants(self, tenant_ids: list[str]) -> list[dict[str, Any]]:
        if not tenant_ids:
            return []
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT job.id, job.tenant_id, job.report_type, job.target_value,
                       job.trigger_type, job.status, job.attempt_count,
                       job.created_at AS requested_at, job.completed_at,
                       job.last_error,
                       account.display_name AS account_name,
                       tenant.customer_name
                FROM control.report_jobs job
                JOIN control.cloud_accounts account
                    ON account.id = job.cloud_account_id
                JOIN control.tenants tenant ON tenant.id = job.tenant_id
                WHERE job.tenant_id = ANY(%s::uuid[])
                ORDER BY job.created_at DESC
                LIMIT 100
                """,
                (tenant_ids,),
            )
            return cursor.fetchall()

    def notification_events(
        self, tenant_ids: Optional[list[str]], after: datetime
    ) -> list[dict[str, Any]]:
        if tenant_ids == []:
            return []
        tenant_condition = ""
        parameters: list[Any] = [after]
        if tenant_ids is not None:
            tenant_condition = "AND job.tenant_id = ANY(%s::uuid[])"
            parameters.append(tenant_ids)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT job.id, event.status, event.occurred_at,
                       job.report_type, tenant.customer_name,
                       account.display_name AS account_name
                FROM control.report_jobs job
                JOIN control.tenants tenant ON tenant.id = job.tenant_id
                JOIN control.cloud_accounts account
                    ON account.id = job.cloud_account_id
                CROSS JOIN LATERAL (
                    SELECT 'QUEUED'::text AS status, job.created_at AS occurred_at
                    UNION ALL
                    SELECT 'RUNNING', job.started_at
                    WHERE job.started_at IS NOT NULL
                    UNION ALL
                    SELECT job.status, job.completed_at
                    WHERE job.completed_at IS NOT NULL
                      AND job.status IN ('SUCCESS', 'FAILED', 'CANCELLED')
                ) event
                WHERE event.occurred_at > %s
                  {tenant_condition}
                ORDER BY event.occurred_at
                LIMIT 100
                """,
                tuple(parameters),
            )
            return cursor.fetchall()

    def schedules(self) -> list[dict[str, Any]]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT schedule.*, tenant.customer_code, tenant.customer_name,
                       tenant.environment, account.display_name AS account_name,
                       account.account_code,
                       (schedule.next_run_at AT TIME ZONE schedule.timezone)
                           AS next_run_local,
                       creator.display_name AS created_by_name
                FROM control.account_report_schedules schedule
                JOIN control.tenants tenant ON tenant.id = schedule.tenant_id
                JOIN control.cloud_accounts account
                    ON account.id = schedule.cloud_account_id
                LEFT JOIN control.users creator ON creator.id = schedule.created_by
                ORDER BY tenant.environment, tenant.customer_name,
                         account.display_name, schedule.report_type
                """
            )
            return cursor.fetchall()

    def report_history(
        self, tenant_ids: Optional[list[str]] = None
    ) -> list[dict[str, Any]]:
        if tenant_ids == []:
            return []
        condition = ""
        parameters: tuple[Any, ...] = ()
        if tenant_ids is not None:
            condition = "WHERE history.tenant_id = ANY(%s::uuid[])"
            parameters = (tenant_ids,)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                WITH history AS (
                    SELECT job.id AS history_id, job.tenant_id,
                           tenant.customer_name, tenant.environment,
                           account.display_name AS account_name,
                           account.account_code, job.report_type,
                           job.target_value, job.trigger_type,
                           job.status AS job_status,
                           report.status AS report_status,
                           report.id AS report_id,
                           COALESCE(report.period_start, job.period_start)
                               AS period_start,
                           COALESCE(report.period_end, job.period_end)
                               AS period_end,
                           COALESCE(report.end_exclusive, true)
                               AS end_exclusive,
                           job.created_at AS requested_at,
                           job.started_at, job.completed_at,
                           COALESCE(report.error_count, 0) AS error_count,
                           requester.display_name AS requested_by_name
                    FROM control.report_jobs job
                    JOIN control.tenants tenant ON tenant.id = job.tenant_id
                    JOIN control.cloud_accounts account
                        ON account.id = job.cloud_account_id
                    LEFT JOIN control.report_runs report
                        ON report.id = job.report_run_id
                    LEFT JOIN control.users requester
                        ON requester.id = job.requested_by
                    UNION ALL
                    SELECT report.id, report.tenant_id,
                           tenant.customer_name, tenant.environment,
                           account.display_name, account.account_code,
                           report.report_type, NULL, report.trigger_type,
                           report.status, report.status, report.id,
                           report.period_start, report.period_end,
                           report.end_exclusive,
                           report.queued_at, report.started_at,
                           report.completed_at, report.error_count,
                           requester.display_name
                    FROM control.report_runs report
                    JOIN control.tenants tenant ON tenant.id = report.tenant_id
                    LEFT JOIN control.cloud_accounts account
                        ON account.id = report.cloud_account_id
                    LEFT JOIN control.users requester
                        ON requester.id = report.requested_by
                    WHERE NOT EXISTS (
                        SELECT 1 FROM control.report_jobs job
                        WHERE job.report_run_id = report.id
                    )
                )
                SELECT * FROM history
                {condition}
                ORDER BY requested_at DESC
                LIMIT 500
                """,
                parameters,
            )
            return cursor.fetchall()

    def register_account_credential(
        self,
        tenant_id: str,
        account_code: str,
        display_name: str,
        access_key: str,
        secret_key: str,
        cipher: CredentialCipher,
        actor_id: str,
    ) -> str:
        account_code = account_code.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", account_code):
            raise ValueError("Account code contains unsupported characters.")
        if not display_name.strip():
            raise ValueError("Account display name is required.")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT environment, region, status FROM control.tenants WHERE id = %s",
                (tenant_id,),
            )
            tenant = cursor.fetchone()
            if not tenant:
                raise ValueError("Customer was not found.")
            if tenant["status"] == "OFFBOARDED":
                raise ValueError("삭제된 고객에는 API 키를 등록할 수 없습니다.")
            cursor.execute(
                """
                INSERT INTO control.cloud_accounts (
                    tenant_id, account_code, display_name, environment, region
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, account_code) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    status = 'ACTIVE'
                RETURNING id
                """,
                (
                    tenant_id, account_code, display_name.strip(),
                    tenant["environment"], tenant["region"],
                ),
            )
            account_id = cursor.fetchone()["id"]
            encrypted = cipher.encrypt(str(account_id), access_key, secret_key)
            cursor.execute(
                """
                INSERT INTO control.encrypted_credentials (
                    tenant_id, cloud_account_id, provider, key_reference,
                    encrypted_dek, dek_nonce, ciphertext, credential_nonce,
                    access_key_hint
                ) VALUES (%s, %s, 'LOCAL_ENVELOPE', %s, %s, %s, %s, %s, %s)
                ON CONFLICT (cloud_account_id) DO UPDATE SET
                    provider = EXCLUDED.provider,
                    key_reference = EXCLUDED.key_reference,
                    encrypted_dek = EXCLUDED.encrypted_dek,
                    dek_nonce = EXCLUDED.dek_nonce,
                    ciphertext = EXCLUDED.ciphertext,
                    credential_nonce = EXCLUDED.credential_nonce,
                    access_key_hint = EXCLUDED.access_key_hint,
                    credential_version = control.encrypted_credentials.credential_version + 1,
                    status = 'VALID',
                    rotated_at = clock_timestamp()
                """,
                (
                    tenant_id, account_id, encrypted.key_reference,
                    encrypted.encrypted_dek, encrypted.dek_nonce,
                    encrypted.ciphertext, encrypted.credential_nonce,
                    encrypted.access_key_hint,
                ),
            )
            cursor.execute(
                """
                INSERT INTO audit.data_change_logs (
                    tenant_id, actor_id, table_name, record_id, operation, changed_fields
                ) VALUES (%s, %s, 'control.encrypted_credentials', %s, 'UPDATE', %s::jsonb)
                """,
                (
                    tenant_id, actor_id, str(account_id),
                    json.dumps({"credential": "rotated", "account_code": account_code}),
                ),
            )
        return str(account_id)

    def delete_account_credential(
        self, tenant_id: str, account_id: str, actor_id: str
    ) -> str:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT account.account_code, account.display_name,
                       EXISTS (
                           SELECT 1 FROM control.report_jobs job
                           WHERE job.cloud_account_id = account.id
                             AND job.status = 'RUNNING'
                       ) AS has_running_job
                FROM control.cloud_accounts account
                WHERE account.id = %s AND account.tenant_id = %s
                FOR UPDATE
                """,
                (account_id, tenant_id),
            )
            account = cursor.fetchone()
            if not account:
                raise ValueError("NCP 계정을 찾을 수 없습니다.")
            if account["has_running_job"]:
                raise ValueError("실행 중인 보고서가 있어 API 키를 삭제할 수 없습니다.")
            cursor.execute(
                "DELETE FROM control.encrypted_credentials "
                "WHERE cloud_account_id = %s AND tenant_id = %s",
                (account_id, tenant_id),
            )
            if cursor.rowcount == 0:
                raise ValueError("삭제할 API 키가 등록되어 있지 않습니다.")
            cursor.execute(
                "UPDATE control.cloud_accounts SET status = 'DISABLED' "
                "WHERE id = %s AND tenant_id = %s",
                (account_id, tenant_id),
            )
            cursor.execute(
                "UPDATE control.account_report_schedules SET enabled = false "
                "WHERE cloud_account_id = %s AND tenant_id = %s",
                (account_id, tenant_id),
            )
            cursor.execute(
                """
                UPDATE control.report_jobs
                SET status = 'CANCELLED', completed_at = clock_timestamp(),
                    last_error = 'Credential removed by MSP administrator.'
                WHERE cloud_account_id = %s AND tenant_id = %s
                  AND status = 'QUEUED'
                """,
                (account_id, tenant_id),
            )
            cursor.execute(
                """
                INSERT INTO audit.data_change_logs (
                    tenant_id, actor_id, table_name, record_id,
                    operation, changed_fields
                ) VALUES (%s, %s, 'control.encrypted_credentials', %s,
                          'DELETE', %s::jsonb)
                """,
                (
                    tenant_id, actor_id, account_id,
                    json.dumps({
                        "credential": "removed",
                        "account_code": account["account_code"],
                    }),
                ),
            )
            return account["display_name"]

    def offboard_tenant(self, tenant_id: str, actor_id: str) -> str:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT customer_name, customer_code,
                       EXISTS (
                           SELECT 1 FROM control.report_jobs job
                           WHERE job.tenant_id = tenant.id
                             AND job.status = 'RUNNING'
                       ) AS has_running_job
                FROM control.tenants tenant
                WHERE id = %s
                FOR UPDATE
                """,
                (tenant_id,),
            )
            tenant = cursor.fetchone()
            if not tenant:
                raise ValueError("고객사를 찾을 수 없습니다.")
            if tenant["has_running_job"]:
                raise ValueError("실행 중인 보고서가 있어 고객을 삭제할 수 없습니다.")
            cursor.execute(
                "DELETE FROM control.encrypted_credentials WHERE tenant_id = %s",
                (tenant_id,),
            )
            cursor.execute(
                "UPDATE control.cloud_accounts SET status = 'DISABLED' "
                "WHERE tenant_id = %s",
                (tenant_id,),
            )
            cursor.execute(
                "UPDATE control.account_report_schedules SET enabled = false "
                "WHERE tenant_id = %s",
                (tenant_id,),
            )
            cursor.execute(
                """
                UPDATE control.report_jobs
                SET status = 'CANCELLED', completed_at = clock_timestamp(),
                    last_error = 'Customer offboarded by MSP administrator.'
                WHERE tenant_id = %s AND status = 'QUEUED'
                """,
                (tenant_id,),
            )
            cursor.execute(
                "UPDATE control.memberships SET status = 'SUSPENDED' "
                "WHERE tenant_id = %s",
                (tenant_id,),
            )
            cursor.execute(
                """
                DELETE FROM control.user_sessions
                WHERE user_id IN (
                    SELECT user_id FROM control.memberships
                    WHERE tenant_id = %s
                )
                """,
                (tenant_id,),
            )
            cursor.execute(
                "UPDATE control.tenants SET status = 'OFFBOARDED' WHERE id = %s",
                (tenant_id,),
            )
            cursor.execute(
                """
                INSERT INTO audit.data_change_logs (
                    tenant_id, actor_id, table_name, record_id,
                    operation, changed_fields
                ) VALUES (%s, %s, 'control.tenants', %s,
                          'DELETE', %s::jsonb)
                """,
                (
                    tenant_id, actor_id, tenant_id,
                    json.dumps({
                        "status": "OFFBOARDED",
                        "customer_code": tenant["customer_code"],
                        "credentials": "removed",
                    }),
                ),
            )
            return tenant["customer_name"]

    def reactivate_tenant(self, tenant_id: str, actor_id: str) -> str:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT customer_name, status, metadata FROM control.tenants "
                "WHERE id = %s FOR UPDATE",
                (tenant_id,),
            )
            tenant = cursor.fetchone()
            if not tenant:
                raise ValueError("고객사를 찾을 수 없습니다.")
            if tenant["status"] != "OFFBOARDED":
                raise ValueError("OFFBOARDED 고객만 재활성화할 수 있습니다.")
            if (tenant.get("metadata") or {}).get("anonymized_at"):
                raise ValueError("익명화된 고객은 재활성화할 수 없습니다.")
            cursor.execute(
                "UPDATE control.tenants SET status = 'ACTIVE' WHERE id = %s",
                (tenant_id,),
            )
            cursor.execute(
                """
                INSERT INTO audit.data_change_logs (
                    tenant_id, actor_id, table_name, record_id,
                    operation, changed_fields
                ) VALUES (%s, %s, 'control.tenants', %s,
                          'UPDATE', '{"status":"ACTIVE"}'::jsonb)
                """,
                (tenant_id, actor_id, tenant_id),
            )
            return tenant["customer_name"]

    def anonymize_tenant(self, tenant_id: str, actor_id: str) -> str:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT customer_name, environment, region, status, metadata,
                       EXISTS (
                           SELECT 1 FROM control.report_jobs job
                           WHERE job.tenant_id = tenant.id
                             AND job.status = 'RUNNING'
                       ) AS has_running_job
                FROM control.tenants tenant
                WHERE id = %s FOR UPDATE
                """,
                (tenant_id,),
            )
            tenant = cursor.fetchone()
            if not tenant:
                raise ValueError("고객사를 찾을 수 없습니다.")
            if tenant["status"] != "OFFBOARDED":
                raise ValueError("OFFBOARDED 고객만 익명화할 수 있습니다.")
            if (tenant.get("metadata") or {}).get("anonymized_at"):
                raise ValueError("이미 익명화된 고객입니다.")
            if tenant["has_running_job"]:
                raise ValueError("실행 중인 보고서가 있어 익명화할 수 없습니다.")

            token = str(tenant_id).replace("-", "")
            anonymous_code = f"anon-{token}"
            anonymous_name = f"익명 고객 {token[:8]}"
            anonymous_customer = {
                "id": anonymous_code,
                "name": anonymous_name,
                "api_type": tenant["environment"],
                "region": tenant["region"],
                "credential_ref": None,
                "cloud_account_id": None,
                "cloud_account_code": None,
            }

            cursor.execute(
                "SELECT user_id FROM control.memberships WHERE tenant_id = %s",
                (tenant_id,),
            )
            member_ids = [str(row["user_id"]) for row in cursor.fetchall()]
            cursor.execute(
                "DELETE FROM control.memberships WHERE tenant_id = %s",
                (tenant_id,),
            )
            orphan_ids: list[str] = []
            if member_ids:
                cursor.execute(
                    """
                    SELECT users.id
                    FROM control.users users
                    WHERE users.id = ANY(%s::uuid[])
                      AND NOT EXISTS (
                          SELECT 1 FROM control.memberships membership
                          WHERE membership.user_id = users.id
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM control.platform_roles role
                          WHERE role.user_id = users.id
                      )
                    """,
                    (member_ids,),
                )
                orphan_ids = [str(row["id"]) for row in cursor.fetchall()]
            if orphan_ids:
                cursor.execute(
                    "DELETE FROM control.user_sessions "
                    "WHERE user_id = ANY(%s::uuid[])",
                    (orphan_ids,),
                )
                cursor.execute(
                    """
                    UPDATE control.users
                    SET email = 'anon-' || replace(id::text, '-', '') || '@deleted.invalid',
                        display_name = '익명 사용자', status = 'DISABLED',
                        password_hash = '!anonymized!', last_login_at = NULL,
                        external_identity_provider = NULL,
                        external_subject = NULL
                    WHERE id = ANY(%s::uuid[])
                    """,
                    (orphan_ids,),
                )
                cursor.execute(
                    """
                    UPDATE audit.authentication_logs
                    SET email_attempted = 'redacted@deleted.invalid',
                        source_ip = NULL, user_agent = NULL,
                        failure_reason = NULL
                    WHERE user_id = ANY(%s::uuid[])
                    """,
                    (orphan_ids,),
                )
                cursor.execute(
                    """
                    UPDATE audit.access_logs
                    SET source_ip = NULL, user_agent = NULL,
                        details = '{"anonymized":true}'::jsonb
                    WHERE actor_id = ANY(%s::uuid[])
                    """,
                    (orphan_ids,),
                )

            cursor.execute(
                """
                UPDATE control.email_deliveries
                SET recipient_email = 'redacted@deleted.invalid',
                    provider_message_id = NULL, last_error = NULL
                WHERE tenant_id = %s
                """,
                (tenant_id,),
            )
            cursor.execute(
                "DELETE FROM control.email_recipients WHERE tenant_id = %s",
                (tenant_id,),
            )
            cursor.execute(
                """
                WITH ranked AS (
                    SELECT id, row_number() OVER (ORDER BY id) AS sequence
                    FROM control.cloud_accounts WHERE tenant_id = %s
                )
                UPDATE control.cloud_accounts account
                SET account_code = 'anonymous-' || ranked.sequence,
                    display_name = '익명 계정 ' || ranked.sequence,
                    status = 'DISABLED'
                FROM ranked WHERE account.id = ranked.id
                """,
                (tenant_id,),
            )

            for schema in ("public_data", "gov_data"):
                cursor.execute(
                    f"SELECT id, normalized_data FROM {schema}.report_snapshots "
                    "WHERE tenant_id = %s",
                    (tenant_id,),
                )
                for snapshot in cursor.fetchall():
                    anonymized = _anonymize_report_payload(
                        snapshot["normalized_data"], anonymous_customer
                    )
                    cursor.execute(
                        f"UPDATE {schema}.report_snapshots "
                        "SET normalized_data = %s::jsonb WHERE id = %s",
                        (json.dumps(anonymized, ensure_ascii=False), snapshot["id"]),
                    )
                cursor.execute(
                    f"UPDATE {schema}.activity_events "
                    "SET account_name = %s WHERE tenant_id = %s",
                    (_ANONYMIZED_VALUE, tenant_id),
                )

            cursor.execute(
                """
                UPDATE audit.data_change_logs
                SET changed_fields = '{"anonymized":true}'::jsonb
                WHERE tenant_id = %s
                """,
                (tenant_id,),
            )
            cursor.execute(
                """
                UPDATE control.tenants
                SET customer_code = %s, customer_name = %s,
                    primary_contact_email = NULL,
                    metadata = jsonb_build_object(
                        'anonymized_at', clock_timestamp(),
                        'irreversible', true
                    )
                WHERE id = %s
                """,
                (anonymous_code, anonymous_name, tenant_id),
            )
            cursor.execute(
                """
                INSERT INTO audit.data_change_logs (
                    tenant_id, actor_id, table_name, record_id,
                    operation, changed_fields
                ) VALUES (%s, %s, 'control.tenants', %s, 'UPDATE',
                          '{"anonymized":true,"irreversible":true}'::jsonb)
                """,
                (tenant_id, actor_id, tenant_id),
            )
            return anonymous_name

    def permanently_delete_tenant(
        self,
        tenant_id: str,
        actor_id: str,
        archive_reference: str = "",
        *,
        force: bool = False,
    ) -> tuple[str, int]:
        archive_reference = archive_reference.strip()
        if len(archive_reference) > 500:
            raise ValueError("외부 보관 참조는 500자 이하여야 합니다.")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT customer_name, customer_code, environment, status,
                       (SELECT count(*) FROM control.report_runs report
                        WHERE report.tenant_id = tenant.id) AS report_count,
                       EXISTS (
                           SELECT 1 FROM control.report_jobs job
                           WHERE job.tenant_id = tenant.id
                             AND job.status = 'RUNNING'
                       ) AS has_running_job
                FROM control.tenants tenant
                WHERE id = %s FOR UPDATE
                """,
                (tenant_id,),
            )
            tenant = cursor.fetchone()
            if not tenant:
                raise ValueError("고객사를 찾을 수 없습니다.")
            if tenant["status"] != "OFFBOARDED":
                raise ValueError("OFFBOARDED 고객만 영구 삭제할 수 있습니다.")
            if tenant["has_running_job"]:
                raise ValueError("실행 중인 보고서가 있어 영구 삭제할 수 없습니다.")
            report_count = int(tenant["report_count"] or 0)
            if report_count and not archive_reference and not force:
                raise ValueError("보고서가 있는 고객은 외부 보관 참조가 필요합니다.")

            code_hash = sha256(
                tenant["customer_code"].casefold().encode("utf-8")
            ).hexdigest()
            cursor.execute(
                """
                INSERT INTO control.customer_deletion_tombstones (
                    customer_code_hash, environment, report_count,
                    archive_reference, forced, deleted_by
                ) VALUES (%s, %s, %s, NULLIF(%s, ''), %s, %s)
                """,
                (
                    code_hash, tenant["environment"], report_count,
                    archive_reference, force, actor_id,
                ),
            )
            cursor.execute(
                """
                INSERT INTO audit.data_change_logs (
                    tenant_id, actor_id, table_name, record_id,
                    operation, changed_fields
                ) VALUES (%s, %s, 'control.tenants', %s, 'DELETE', %s::jsonb)
                """,
                (
                    tenant_id, actor_id, tenant_id,
                    json.dumps({
                        "permanent": True,
                        "report_count": report_count,
                        "archive_reference": archive_reference or None,
                        "forced": force,
                    }),
                ),
            )
            cursor.execute(
                "DELETE FROM control.email_deliveries WHERE tenant_id = %s",
                (tenant_id,),
            )
            cursor.execute(
                "DELETE FROM control.report_runs WHERE tenant_id = %s",
                (tenant_id,),
            )
            cursor.execute("DELETE FROM control.tenants WHERE id = %s", (tenant_id,))
            return tenant["customer_name"], report_count

    def account_credentials(
        self, account_id: str, cipher: CredentialCipher
    ) -> tuple[CustomerProfile, NCPCredentials]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT account.id, account.account_code, account.display_name,
                       account.environment, account.region,
                       tenant.customer_code, tenant.customer_name,
                       credential.encrypted_dek, credential.dek_nonce,
                       credential.ciphertext, credential.credential_nonce,
                       credential.status
                FROM control.cloud_accounts account
                JOIN control.tenants tenant ON tenant.id = account.tenant_id
                JOIN control.encrypted_credentials credential
                    ON credential.cloud_account_id = account.id
                WHERE account.id = %s AND account.status = 'ACTIVE'
                """,
                (account_id,),
            )
            row = cursor.fetchone()
        if not row or row["status"] != "VALID":
            raise ValueError("Active credentials were not found for the account.")
        plaintext = cipher.decrypt(
            str(row["id"]), row["encrypted_dek"], row["dek_nonce"],
            row["ciphertext"], row["credential_nonce"],
        )
        customer = CustomerProfile(
            customer_id=row["customer_code"],
            customer_name=row["customer_name"],
            api_type=row["environment"],
            region=row["region"],
            credential_ref=f"encrypted-db://{row['id']}",
            cloud_account_id=str(row["id"]),
            cloud_account_code=row["account_code"],
        )
        credentials = NCPCredentials(
            access_key=plaintext["access_key"],
            secret_key=plaintext["secret_key"],
            api_type=row["environment"],
            region=row["region"],
            account_name=row["display_name"],
        )
        return customer, credentials

    def _report_rows(self, cursor: Any, tenant_id: str) -> list[dict[str, Any]]:
        cursor.execute(
            """
            SELECT report.id, report.report_type, report.period_start,
                   report.period_end, report.end_exclusive,
                   report.status, report.error_count,
                   report.created_at, report.completed_at,
                   CASE
                       WHEN report.started_at IS NULL THEN NULL
                       ELSE GREATEST(EXTRACT(EPOCH FROM (
                           COALESCE(report.completed_at, clock_timestamp())
                           - report.started_at
                       )), 0)::bigint
                   END AS execution_seconds,
                   account.display_name AS account_name
            FROM control.report_runs report
            LEFT JOIN control.cloud_accounts account ON account.id = report.cloud_account_id
            WHERE report.tenant_id = %s
            ORDER BY report.created_at DESC, report.id DESC LIMIT 50
            """,
            (tenant_id,),
        )
        return cursor.fetchall()

from __future__ import annotations

import json
import os
import re
import secrets
from collections.abc import Mapping
from hashlib import sha256
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urlparse
from uuid import UUID

from psycopg.rows import dict_row

from database.config import DatabaseSettings
from webapp.security import CredentialCipher, hash_password, token_hash
from utils.credentials import NCPCredentials
from app.customer import CustomerProfile
from app.report_branding import CustomerLogo, validate_customer_logo
from app.report_options import (
    normalize_report_options,
    validate_report_options,
)


_ANONYMIZED_VALUE = "[익명화됨]"
_PERSONAL_DATA_KEYS = {
    "account_name", "actor", "actor_id", "email", "email_address",
    "member_no", "member_number", "user", "user_id", "user_name",
}
_ACTIVE_REPORT_STATUSES = {"QUEUED", "RUNNING", "RETRYING"}
_MSP_ACCOUNT_MANAGEMENT_LOCK_ID = 1_311_787_345
_LEGACY_ANALYSIS_POLICY_KEYS = (
    "require_block_storage_encryption",
    "require_kubernetes_termination_protection",
    "flag_public_ip",
    "require_owner_tag",
    "require_backup",
)


def _preserved_legacy_analysis_policies(value: Any) -> dict[str, bool]:
    """기능은 비활성화하되 구버전 원복용 정책 선택값은 보존한다."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return {}
    if not isinstance(value, Mapping):
        return {}
    analysis = value.get("operational_analysis")
    if not isinstance(analysis, Mapping):
        return {}
    policies = analysis.get("policies")
    if not isinstance(policies, Mapping):
        return {}
    return {
        key: policies[key]
        for key in _LEGACY_ANALYSIS_POLICY_KEYS
        if isinstance(policies.get(key), bool)
    }


def _remove_local_report_artifacts(storage_uris: list[str]) -> tuple[int, int]:
    output_root = Path(
        os.environ.get("REPORT_OUTPUT_DIR", "/app/output/report")
    ).resolve()
    removed = 0
    failed = 0
    for storage_uri in set(storage_uris):
        parsed = urlparse(storage_uri)
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            continue
        local_path = unquote(parsed.path)
        if os.name == "nt" and re.match(r"^/[A-Za-z]:", local_path):
            local_path = local_path[1:]
        candidate = Path(local_path).resolve()
        try:
            candidate.relative_to(output_root)
        except ValueError:
            continue
        try:
            candidate.unlink(missing_ok=True)
            removed += 1
        except OSError:
            failed += 1
    return removed, failed


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


def _validate_msp_status_change(
    *,
    target_user_id: str,
    actor_id: str,
    current_status: str,
    enabled: bool,
    is_admin: bool,
    active_admin_count: int | None,
) -> None:
    """MSP 계정 상태 변경으로 관리 접근이 끊기지 않도록 검증한다."""

    if target_user_id == actor_id:
        raise ValueError("현재 로그인한 자신의 MSP 계정 상태는 변경할 수 없습니다.")
    if current_status not in {"ACTIVE", "DISABLED"}:
        raise ValueError(
            "잠김 또는 초대 상태의 계정은 이 화면에서 활성화·비활성화할 수 없습니다."
        )
    if (
        not enabled
        and current_status == "ACTIVE"
        and is_admin
        and (active_admin_count or 0) <= 1
    ):
        raise ValueError("마지막 활성 MSP 관리자는 비활성화할 수 없습니다.")


class PortalRepository:
    def __init__(self, settings: DatabaseSettings):
        self.settings = settings

    def _connect(self):
        import psycopg

        return psycopg.connect(
            **self.settings.connection_kwargs(),
            row_factory=dict_row,
        )

    @staticmethod
    def _set_tenant_rls_scope(cursor: Any, tenant_id: str) -> str:
        """대상 고객과 환경을 현재 트랜잭션의 RLS 범위로 설정한다."""

        cursor.execute(
            "SELECT environment FROM control.tenants WHERE id = %s",
            (tenant_id,),
        )
        tenant = cursor.fetchone()
        if not tenant:
            raise ValueError("고객을 찾을 수 없습니다.")
        environment = str(tenant["environment"])
        if environment not in {"public", "gov"}:
            raise ValueError("고객 환경이 올바르지 않습니다.")
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)",
            (tenant_id,),
        )
        cursor.execute(
            "SELECT set_config('app.environment_scope', %s, true)",
            (environment,),
        )
        return environment

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
                """
                SELECT role, environment_scope
                FROM control.platform_roles
                WHERE user_id = %s
                ORDER BY role, environment_scope NULLS FIRST
                """,
                (user_id,),
            )
            role_bindings = cursor.fetchall()
            user["platform_role_bindings"] = role_bindings
            user["platform_roles"] = list(dict.fromkeys(
                row["role"] for row in role_bindings
            ))
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

    def create_msp_user(
        self,
        email: str,
        password: str,
        display_name: str,
        role: str,
        environment_scope: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> str:
        if role not in {"MSP_ADMIN", "MSP_OPERATOR"}:
            raise ValueError("지원하지 않는 MSP 권한입니다.")
        if environment_scope not in {None, "public", "gov"}:
            raise ValueError("지원하지 않는 MSP 접근 범위입니다.")
        email, display_name = _validate_user_fields(email, display_name)
        password_hash = hash_password(password)
        with self._connect() as connection, connection.cursor() as cursor:
            if actor_id is not None:
                try:
                    actor_id = str(UUID(actor_id))
                except (TypeError, ValueError) as exc:
                    raise ValueError("MSP 계정 등록 요청자가 올바르지 않습니다.") from exc
            # 계정 생성과 상태 변경을 직렬화해 관리자 수 안전장치의 경쟁 조건을 막는다.
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s::bigint)",
                (_MSP_ACCOUNT_MANAGEMENT_LOCK_ID,),
            )
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
                ) VALUES (%s, %s, %s, 'ACTIVE')
                RETURNING id
                """,
                (email, password_hash, display_name),
            )
            user_id = cursor.fetchone()["id"]
            cursor.execute(
                """
                INSERT INTO control.platform_roles (
                    user_id, role, environment_scope
                ) VALUES (%s, %s, %s)
                """,
                (user_id, role, environment_scope),
            )
            cursor.execute(
                """
                INSERT INTO audit.data_change_logs (
                    actor_id, table_name, record_id, operation, changed_fields
                ) VALUES (%s, 'control.users', %s, 'INSERT', %s::jsonb)
                """,
                (
                    actor_id,
                    str(user_id),
                    json.dumps(
                        {
                            "status": "ACTIVE",
                            "platform_role": role,
                            "environment_scope": environment_scope,
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            return str(user_id)

    def msp_users(
        self, allowed_environments: Optional[set[str]] = None
    ) -> list[dict[str, Any]]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT users.id, users.email, users.display_name,
                       users.status AS user_status, users.last_login_at,
                       users.created_at,
                       CASE
                           WHEN bool_or(role.role = 'MSP_ADMIN')
                           THEN 'MSP_ADMIN'
                           ELSE 'MSP_OPERATOR'
                       END AS role,
                       CASE
                           WHEN bool_or(role.environment_scope IS NULL)
                                OR count(DISTINCT role.environment_scope) > 1
                           THEN NULL
                           ELSE min(role.environment_scope)
                       END AS environment_scope
                FROM control.users users
                JOIN control.platform_roles role ON role.user_id = users.id
                WHERE role.role IN ('MSP_ADMIN', 'MSP_OPERATOR')
                GROUP BY users.id
                ORDER BY users.display_name, users.email
                """
            )
            users = cursor.fetchall()
        if allowed_environments is None:
            return users
        return [
            user for user in users
            if user["environment_scope"] in allowed_environments
        ]

    def set_msp_user_enabled(
        self,
        user_id: str,
        actor_id: str,
        enabled: bool,
    ) -> str:
        """다른 MSP 계정을 활성화하거나 비활성화하고 세션을 회수한다."""

        try:
            user_id = str(UUID(user_id))
            actor_id = str(UUID(actor_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("MSP 사용자 식별자가 올바르지 않습니다.") from exc
        desired_status = "ACTIVE" if enabled else "DISABLED"
        with self._connect() as connection, connection.cursor() as cursor:
            # 두 관리자가 동시에 서로를 비활성화해 관리자 0명이 되는 상황을 방지한다.
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s::bigint)",
                (_MSP_ACCOUNT_MANAGEMENT_LOCK_ID,),
            )
            cursor.execute(
                """
                SELECT users.id, users.display_name, users.status,
                       EXISTS (
                           SELECT 1
                           FROM control.platform_roles admin_role
                           WHERE admin_role.user_id = users.id
                             AND admin_role.role = 'MSP_ADMIN'
                       ) AS is_admin
                FROM control.users users
                WHERE users.id = %s
                  AND EXISTS (
                      SELECT 1
                      FROM control.platform_roles msp_role
                      WHERE msp_role.user_id = users.id
                        AND msp_role.role IN ('MSP_ADMIN', 'MSP_OPERATOR')
                  )
                FOR UPDATE
                """,
                (user_id,),
            )
            target = cursor.fetchone()
            if not target:
                raise ValueError("변경할 MSP 계정을 찾을 수 없습니다.")

            active_admin_count: int | None = None
            if not enabled and target["is_admin"]:
                cursor.execute(
                    """
                    SELECT count(DISTINCT users.id) AS active_admin_count
                    FROM control.users users
                    JOIN control.platform_roles role ON role.user_id = users.id
                    WHERE users.status = 'ACTIVE'
                      AND role.role = 'MSP_ADMIN'
                    """
                )
                active_admin_count = int(
                    cursor.fetchone()["active_admin_count"]
                )
            _validate_msp_status_change(
                target_user_id=user_id,
                actor_id=actor_id,
                current_status=target["status"],
                enabled=enabled,
                is_admin=bool(target["is_admin"]),
                active_admin_count=active_admin_count,
            )
            if target["status"] == desired_status:
                return str(target["display_name"])

            cursor.execute(
                """
                UPDATE control.users
                SET status = %s, updated_at = clock_timestamp()
                WHERE id = %s
                """,
                (desired_status, user_id),
            )
            if not enabled:
                cursor.execute(
                    "DELETE FROM control.user_sessions WHERE user_id = %s",
                    (user_id,),
                )
            cursor.execute(
                """
                INSERT INTO audit.data_change_logs (
                    actor_id, table_name, record_id, operation, changed_fields
                ) VALUES (%s, 'control.users', %s, 'UPDATE', %s::jsonb)
                """,
                (
                    actor_id,
                    user_id,
                    json.dumps(
                        {
                            "status": {
                                "from": target["status"],
                                "to": desired_status,
                            }
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            return str(target["display_name"])

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

    def customer_users(
        self, allowed_environments: Optional[set[str]] = None
    ) -> list[dict[str, Any]]:
        tenant_join_condition = ""
        parameters: tuple[Any, ...] = ()
        if allowed_environments is not None:
            if not allowed_environments:
                return []
            tenant_join_condition = "AND tenant.environment = ANY(%s)"
            parameters = (sorted(allowed_environments),)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
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
                  {tenant_join_condition}
                ORDER BY users.display_name, users.email, tenant.customer_name
                """,
                parameters,
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

    def customer_user_accessible_in_environments(
        self, user_id: str, allowed_environments: set[str]
    ) -> bool:
        """고객 사용자가 관리자의 환경 범위 안에 이미 속하는지 확인한다."""

        if not allowed_environments:
            return False
        try:
            user_id = str(UUID(user_id))
        except (TypeError, ValueError):
            return False
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM control.memberships membership
                    JOIN control.tenants tenant
                      ON tenant.id = membership.tenant_id
                    WHERE membership.user_id = %s
                      AND tenant.environment = ANY(%s)
                ) AS accessible
                """,
                (user_id, sorted(allowed_environments)),
            )
            return bool(cursor.fetchone()["accessible"])

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
            cursor.execute(
                """
                INSERT INTO control.tenant_report_settings (tenant_id)
                VALUES (%s)
                ON CONFLICT (tenant_id) DO NOTHING
                """,
                (row["id"],),
            )
            return str(row["id"])

    def dashboard(
        self, allowed_environments: Optional[set[str]] = None
    ) -> dict[str, Any]:
        if allowed_environments is not None and not allowed_environments:
            return {
                "summary": {
                    "customer_count": 0,
                    "public_count": 0,
                    "gov_count": 0,
                    "issue_count": 0,
                },
                "issue_customers": [],
            }
        tenant_filter = ""
        status_filter = ""
        parameters: tuple[Any, ...] = ()
        if allowed_environments is not None:
            tenant_filter = "AND environment = ANY(%s)"
            status_filter = "WHERE environment = ANY(%s)"
            parameters = (sorted(allowed_environments),)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT count(*) AS customer_count,
                       count(*) FILTER (WHERE environment = 'public') AS public_count,
                       count(*) FILTER (WHERE environment = 'gov') AS gov_count
                FROM control.tenants
                WHERE status <> 'OFFBOARDED' {tenant_filter}
                """,
                parameters,
            )
            summary = cursor.fetchone()
            cursor.execute(
                f"""
                SELECT DISTINCT ON (tenant_id)
                       tenant_id, customer_code, customer_name, environment,
                       fact_date, collection_status, critical_count, warning_count,
                       activity_failure_count, collection_error_count, updated_at
                FROM control.v_msp_customer_daily_status
                {status_filter}
                ORDER BY tenant_id, fact_date DESC NULLS LAST
                """,
                parameters,
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

    def tenants(
        self,
        environment: Optional[str] = None,
        allowed_environments: Optional[set[str]] = None,
    ) -> list[dict[str, Any]]:
        if (
            allowed_environments is not None
            and environment is not None
            and environment not in allowed_environments
        ):
            return []
        if allowed_environments is not None and not allowed_environments:
            return []
        parameters: tuple[Any, ...] = ()
        condition = ""
        if environment in {"public", "gov"}:
            condition = "WHERE tenant.environment = %s"
            parameters = (environment,)
        elif allowed_environments is not None:
            condition = "WHERE tenant.environment = ANY(%s)"
            parameters = (sorted(allowed_environments),)
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

    def tenant_ids_for_environments(
        self, allowed_environments: set[str]
    ) -> list[str]:
        """MSP 환경 범위에 포함되는 tenant ID만 반환한다."""

        if not allowed_environments:
            return []
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM control.tenants
                WHERE environment = ANY(%s)
                ORDER BY id
                """,
                (sorted(allowed_environments),),
            )
            return [str(row["id"]) for row in cursor.fetchall()]

    def tenant_detail(self, tenant_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM control.tenants WHERE id = %s", (tenant_id,))
            tenant = cursor.fetchone()
            if not tenant:
                return None
            cursor.execute(
                """
                SELECT settings
                FROM control.tenant_report_settings
                WHERE tenant_id = %s
                """,
                (tenant_id,),
            )
            report_settings = cursor.fetchone()
            tenant["report_options"] = normalize_report_options(
                report_settings["settings"] if report_settings else None
            )
            cursor.execute(
                """
                SELECT logo_content, logo_content_type, logo_width,
                       logo_height, logo_sha256, updated_at
                FROM control.tenant_branding
                WHERE tenant_id = %s
                """,
                (tenant_id,),
            )
            branding = cursor.fetchone()
            tenant["branding"] = self._branding_view(branding)
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

    def update_tenant_report_settings(
        self,
        tenant_id: str,
        options: dict[str, Any],
        actor_id: str,
    ) -> dict[str, Any]:
        normalized = validate_report_options(options)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tenant.id, report_settings.settings
                FROM control.tenants tenant
                LEFT JOIN control.tenant_report_settings report_settings
                  ON report_settings.tenant_id = tenant.id
                WHERE tenant.id = %s AND tenant.status <> 'OFFBOARDED'
                """,
                (tenant_id,),
            )
            tenant = cursor.fetchone()
            if not tenant:
                raise ValueError("활성 고객을 찾을 수 없습니다.")
            legacy_policies = _preserved_legacy_analysis_policies(
                tenant.get("settings")
            )
            if legacy_policies:
                normalized["operational_analysis"]["policies"] = (
                    legacy_policies
                )
            cursor.execute(
                """
                INSERT INTO control.tenant_report_settings (
                    tenant_id, settings, updated_by
                ) VALUES (%s, %s::jsonb, %s)
                ON CONFLICT (tenant_id) DO UPDATE SET
                    settings = EXCLUDED.settings,
                    updated_by = EXCLUDED.updated_by
                """,
                (
                    tenant_id,
                    json.dumps(normalized, ensure_ascii=False),
                    actor_id,
                ),
            )
            cursor.execute(
                """
                INSERT INTO audit.data_change_logs (
                    tenant_id, actor_id, table_name, record_id,
                    operation, changed_fields
                ) VALUES (%s, %s, 'control.tenant_report_settings', %s,
                          'UPDATE', %s::jsonb)
                """,
                (
                    tenant_id,
                    actor_id,
                    tenant_id,
                    json.dumps({"report_options": normalized}, ensure_ascii=False),
                ),
            )
        return normalized

    def update_tenant_logo(
        self,
        tenant_id: str,
        logo: CustomerLogo,
        actor_id: str,
    ) -> None:
        """검증된 로고를 저장하고 이미지 원문은 감사 로그에서 제외한다."""
        if not isinstance(logo, CustomerLogo):
            raise ValueError("검증된 고객사 로고가 필요합니다.")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM control.tenants "
                "WHERE id = %s AND status <> 'OFFBOARDED'",
                (tenant_id,),
            )
            if not cursor.fetchone():
                raise ValueError("활성 고객을 찾을 수 없습니다.")
            cursor.execute(
                """
                INSERT INTO control.tenant_branding (
                    tenant_id, logo_content, logo_content_type,
                    logo_width, logo_height, logo_sha256, updated_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id) DO UPDATE SET
                    logo_content = EXCLUDED.logo_content,
                    logo_content_type = EXCLUDED.logo_content_type,
                    logo_width = EXCLUDED.logo_width,
                    logo_height = EXCLUDED.logo_height,
                    logo_sha256 = EXCLUDED.logo_sha256,
                    updated_by = EXCLUDED.updated_by
                """,
                (
                    tenant_id,
                    logo.content,
                    logo.content_type,
                    logo.width,
                    logo.height,
                    logo.sha256,
                    actor_id,
                ),
            )
            self._record_logo_change(cursor, tenant_id, actor_id, logo)

    def delete_tenant_logo(self, tenant_id: str, actor_id: str) -> None:
        """새 보고서에서 로고를 제거하되 기존 보고서 스냅샷은 유지한다."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM control.tenants "
                "WHERE id = %s AND status <> 'OFFBOARDED'",
                (tenant_id,),
            )
            if not cursor.fetchone():
                raise ValueError("활성 고객을 찾을 수 없습니다.")
            cursor.execute(
                "DELETE FROM control.tenant_branding WHERE tenant_id = %s",
                (tenant_id,),
            )
            if cursor.rowcount == 0:
                raise ValueError("삭제할 고객사 로고가 없습니다.")
            cursor.execute(
                """
                INSERT INTO audit.data_change_logs (
                    tenant_id, actor_id, table_name, record_id,
                    operation, changed_fields
                ) VALUES (%s, %s, 'control.tenant_branding', %s,
                          'DELETE', '{"logo":"removed"}'::jsonb)
                """,
                (tenant_id, actor_id, tenant_id),
            )

    @staticmethod
    def _record_logo_change(
        cursor: Any,
        tenant_id: str,
        actor_id: str,
        logo: CustomerLogo,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO audit.data_change_logs (
                tenant_id, actor_id, table_name, record_id,
                operation, changed_fields
            ) VALUES (%s, %s, 'control.tenant_branding', %s,
                      'UPDATE', %s::jsonb)
            """,
            (
                tenant_id,
                actor_id,
                tenant_id,
                json.dumps(
                    {
                        "logo": "updated",
                        "content_type": logo.content_type,
                        "width": logo.width,
                        "height": logo.height,
                        "size_bytes": len(logo.content),
                        "sha256": logo.sha256,
                    },
                    ensure_ascii=False,
                ),
            ),
        )

    @staticmethod
    def _branding_view(branding: Optional[dict[str, Any]]) -> dict[str, Any]:
        if not branding:
            return {}
        content = bytes(branding["logo_content"])
        logo = validate_customer_logo(content, branding["logo_content_type"])
        if (
            logo.width != branding["logo_width"]
            or logo.height != branding["logo_height"]
            or logo.sha256 != str(branding["logo_sha256"]).strip()
        ):
            raise ValueError("저장된 고객사 로고의 무결성 검증에 실패했습니다.")
        return {
            "logo_data_uri": logo.data_uri,
            "content_type": logo.content_type,
            "width": logo.width,
            "height": logo.height,
            "sha256": logo.sha256,
            "updated_at": branding["updated_at"],
        }

    def account_tenant(self, account_id: str) -> Optional[str]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT tenant_id FROM control.cloud_accounts WHERE id = %s",
                (account_id,),
            )
            row = cursor.fetchone()
            return str(row["tenant_id"]) if row else None

    def schedule_environment(self, schedule_id: str) -> Optional[str]:
        """일정 변경 전에 해당 고객 환경을 확인한다."""

        try:
            schedule_id = str(UUID(schedule_id))
        except (TypeError, ValueError):
            return None
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tenant.environment
                FROM control.account_report_schedules schedule
                JOIN control.tenants tenant ON tenant.id = schedule.tenant_id
                WHERE schedule.id = %s
                """,
                (schedule_id,),
            )
            row = cursor.fetchone()
            return str(row["environment"]) if row else None

    def msp_user_environment_scopes(
        self, user_id: str
    ) -> Optional[set[str]]:
        """대상 MSP 계정의 환경 범위를 반환한다. ``None``은 전체 범위다."""

        try:
            user_id = str(UUID(user_id))
        except (TypeError, ValueError):
            return set()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT environment_scope
                FROM control.platform_roles
                WHERE user_id = %s
                  AND role IN ('MSP_ADMIN', 'MSP_OPERATOR', 'SYSTEM_ADMIN')
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
        if not rows:
            return set()
        if any(row["environment_scope"] is None for row in rows):
            return None
        return {str(row["environment_scope"]) for row in rows}

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

    def delete_report(self, report_id: str, actor_id: str) -> dict[str, Any]:
        storage_uris: list[str] = []
        result: dict[str, Any]
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT report.id, report.tenant_id, report.environment,
                       report.status, report.report_type,
                       tenant.customer_name
                FROM control.report_runs report
                JOIN control.tenants tenant ON tenant.id = report.tenant_id
                WHERE report.id = %s
                FOR UPDATE OF report
                """,
                (report_id,),
            )
            report = cursor.fetchone()
            if not report:
                raise ValueError("보고서를 찾을 수 없습니다.")
            if report["status"] in _ACTIVE_REPORT_STATUSES:
                raise ValueError("실행 중인 보고서는 삭제할 수 없습니다.")

            schema = (
                "public_data" if report["environment"] == "public"
                else "gov_data"
            )
            cursor.execute(
                "SELECT storage_uri FROM control.report_artifacts "
                "WHERE report_run_id = %s",
                (report_id,),
            )
            storage_uris.extend(
                str(row["storage_uri"]) for row in cursor.fetchall()
                if row.get("storage_uri")
            )
            cursor.execute(
                f"SELECT storage_uri FROM {schema}.raw_payload_refs "
                "WHERE report_run_id = %s",
                (report_id,),
            )
            storage_uris.extend(
                str(row["storage_uri"]) for row in cursor.fetchall()
                if row.get("storage_uri")
            )
            cursor.execute(
                f"SELECT artifact_uri FROM {schema}.metric_series "
                "WHERE report_run_id = %s AND artifact_uri IS NOT NULL",
                (report_id,),
            )
            storage_uris.extend(
                str(row["artifact_uri"]) for row in cursor.fetchall()
                if row.get("artifact_uri")
            )

            cursor.execute(
                """
                INSERT INTO audit.data_change_logs (
                    tenant_id, actor_id, table_name, record_id,
                    operation, changed_fields
                ) VALUES (%s, %s, 'control.report_runs', %s, 'DELETE', %s::jsonb)
                """,
                (
                    report["tenant_id"], actor_id, report_id,
                    json.dumps({
                        "report_type": report["report_type"],
                        "status": report["status"],
                        "artifact_reference_count": len(set(storage_uris)),
                    }),
                ),
            )
            cursor.execute(
                "DELETE FROM control.report_runs WHERE id = %s",
                (report_id,),
            )
            result = {
                "tenant_id": str(report["tenant_id"]),
                "customer_name": report["customer_name"],
            }

        removed, failed = _remove_local_report_artifacts(storage_uris)
        result["removed_artifact_files"] = removed
        result["failed_artifact_files"] = failed
        return result

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
                ORDER BY job.created_at DESC, job.id DESC
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

    def schedules(
        self, allowed_environments: Optional[set[str]] = None
    ) -> list[dict[str, Any]]:
        if allowed_environments is not None and not allowed_environments:
            return []
        environment_filter = ""
        parameters: tuple[Any, ...] = ()
        if allowed_environments is not None:
            environment_filter = "WHERE tenant.environment = ANY(%s)"
            parameters = (sorted(allowed_environments),)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
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
                {environment_filter}
                ORDER BY tenant.environment, tenant.customer_name,
                         account.display_name, schedule.report_type
                """,
                parameters,
            )
            return cursor.fetchall()

    def schedulable_accounts(
        self, allowed_environments: Optional[set[str]] = None
    ) -> list[dict[str, Any]]:
        if allowed_environments is not None and not allowed_environments:
            return []
        environment_filter = ""
        parameters: tuple[Any, ...] = ()
        if allowed_environments is not None:
            environment_filter = "AND tenant.environment = ANY(%s)"
            parameters = (sorted(allowed_environments),)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT account.id, account.tenant_id, account.account_code,
                       account.display_name AS account_name,
                       tenant.customer_code, tenant.customer_name,
                       tenant.environment
                FROM control.cloud_accounts account
                JOIN control.tenants tenant ON tenant.id = account.tenant_id
                JOIN control.encrypted_credentials credential
                    ON credential.cloud_account_id = account.id
                   AND credential.tenant_id = account.tenant_id
                WHERE tenant.status = 'ACTIVE'
                  AND account.status = 'ACTIVE'
                  {environment_filter}
                ORDER BY tenant.environment, tenant.customer_name,
                         account.display_name
                """,
                parameters,
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
        """고객과 연관 개인정보를 하나의 트랜잭션에서 익명화한다.

        일부 테이블만 익명화된 중간 상태는 개인정보 제거와 보고서 재현 계약을
        모두 깨뜨리므로 모든 단계에 같은 cursor를 전달해 함께 commit/rollback한다.
        """
        with self._connect() as connection, connection.cursor() as cursor:
            tenant = self._tenant_for_anonymization(cursor, tenant_id)
            anonymous_code, anonymous_name, anonymous_customer = (
                self._anonymous_tenant_identity(tenant_id, tenant)
            )
            self._anonymize_tenant_members(cursor, tenant_id)
            self._anonymize_tenant_contacts_and_accounts(cursor, tenant_id)
            self._anonymize_tenant_report_data(
                cursor,
                tenant_id,
                anonymous_customer,
            )
            self._record_tenant_anonymization(
                cursor,
                tenant_id,
                actor_id,
                anonymous_code,
                anonymous_name,
            )
            return anonymous_name

    @staticmethod
    def _tenant_for_anonymization(cursor: Any, tenant_id: str) -> dict[str, Any]:
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
        return tenant

    @staticmethod
    def _anonymous_tenant_identity(
        tenant_id: str,
        tenant: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
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
        return anonymous_code, anonymous_name, anonymous_customer

    def _anonymize_tenant_members(self, cursor: Any, tenant_id: str) -> None:
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
            self._anonymize_orphan_users(cursor, orphan_ids)

    @staticmethod
    def _anonymize_orphan_users(cursor: Any, orphan_ids: list[str]) -> None:
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

    @staticmethod
    def _anonymize_tenant_contacts_and_accounts(
        cursor: Any,
        tenant_id: str,
    ) -> None:
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
            "DELETE FROM control.tenant_branding WHERE tenant_id = %s",
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

    @staticmethod
    def _anonymize_tenant_report_data(
        cursor: Any,
        tenant_id: str,
        anonymous_customer: dict[str, Any],
    ) -> None:
        for schema in ("public_data", "gov_data"):
            cursor.execute(
                f"SELECT id, normalized_data FROM {schema}.report_snapshots "
                "WHERE tenant_id = %s",
                (tenant_id,),
            )
            for snapshot in cursor.fetchall():
                anonymized = _anonymize_report_payload(
                    snapshot["normalized_data"],
                    anonymous_customer,
                )
                cursor.execute(
                    f"UPDATE {schema}.report_snapshots "
                    "SET normalized_data = %s::jsonb WHERE id = %s",
                    (
                        json.dumps(anonymized, ensure_ascii=False),
                        snapshot["id"],
                    ),
                )
            cursor.execute(
                f"UPDATE {schema}.activity_events "
                "SET account_name = %s WHERE tenant_id = %s",
                (_ANONYMIZED_VALUE, tenant_id),
            )

    @staticmethod
    def _record_tenant_anonymization(
        cursor: Any,
        tenant_id: str,
        actor_id: str,
        anonymous_code: str,
        anonymous_name: str,
    ) -> None:
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
                       report_settings.settings AS report_options,
                       branding.logo_content, branding.logo_content_type,
                       branding.logo_width, branding.logo_height,
                       branding.logo_sha256, branding.updated_at,
                       credential.encrypted_dek, credential.dek_nonce,
                       credential.ciphertext, credential.credential_nonce,
                       credential.status
                FROM control.cloud_accounts account
                JOIN control.tenants tenant ON tenant.id = account.tenant_id
                JOIN control.encrypted_credentials credential
                    ON credential.cloud_account_id = account.id
                LEFT JOIN control.tenant_report_settings report_settings
                    ON report_settings.tenant_id = account.tenant_id
                LEFT JOIN control.tenant_branding branding
                    ON branding.tenant_id = account.tenant_id
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
        branding = (
            self._branding_view(row)
            if row["logo_content"] is not None
            else {}
        )
        customer = CustomerProfile(
            customer_id=row["customer_code"],
            customer_name=row["customer_name"],
            api_type=row["environment"],
            region=row["region"],
            credential_ref=f"encrypted-db://{row['id']}",
            cloud_account_id=str(row["id"]),
            cloud_account_code=row["account_code"],
            report_options=normalize_report_options(row["report_options"]),
            logo_data_uri=branding.get("logo_data_uri"),
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

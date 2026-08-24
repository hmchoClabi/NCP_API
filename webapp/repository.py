from __future__ import annotations

import json
import logging
import os
import re
import secrets
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from shutil import disk_usage
from typing import Any, Optional
from urllib.parse import unquote, urlparse
from uuid import UUID, uuid4

from psycopg.rows import dict_row

from database.config import DatabaseSettings
from webapp.security import CredentialCipher, hash_password, token_hash
from utils.credentials import NCPCredentials
from app.customer import CustomerProfile
from app.network_configuration import replace_configuration_records
from app.report_branding import CustomerLogo, validate_customer_logo
from app.report_options import (
    normalize_report_options,
    validate_report_options,
)


_ANONYMIZED_VALUE = "[익명화됨]"
REPORT_RETENTION_TYPES = ("DAILY", "WEEKLY", "MONTHLY")
REPORT_RETENTION_MIN_DAYS = 1
REPORT_RETENTION_MAX_DAYS = 3_650
REPORT_RETENTION_SETTINGS_KEY = "retention_policies"
_PERSONAL_DATA_KEYS = {
    "account_name", "actor", "actor_id", "email", "email_address",
    "member_no", "member_number", "user", "user_id", "user_name",
}
_ACTIVE_REPORT_STATUSES = {"QUEUED", "RUNNING", "RETRYING"}
_MSP_ACCOUNT_MANAGEMENT_LOCK_ID = 1_311_787_345
_LEGACY_DIAGNOSTIC_PREFIXES = (
    "activity_tracer_errors",
    "activity_tracer_events",
    "billing_raw",
    "billing_result",
    "cloud_insight_errors",
    "cloud_insight_events",
    "collection_errors",
    "infrastructure_inventory",
    "infrastructure_metrics",
    "server_metric_summary",
)
_LEGACY_ANALYSIS_POLICY_KEYS = (
    "require_block_storage_encryption",
    "require_kubernetes_termination_protection",
    "flag_public_ip",
    "require_owner_tag",
    "require_backup",
)
LOGGER = logging.getLogger(__name__)


class ReportCleanupProtectedError(ValueError):
    """보고서가 실행 시점 보호 조건에 걸려 정리할 수 없음을 나타낸다."""


def default_report_retention_policies() -> dict[str, dict[str, Any]]:
    return {
        report_type: {"mode": "FOREVER", "days": None}
        for report_type in REPORT_RETENTION_TYPES
    }


def _retention_days(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        days = value
    elif isinstance(value, str) and re.fullmatch(
        r"[1-9][0-9]{0,3}", value.strip()
    ):
        days = int(value.strip())
    else:
        return None
    if REPORT_RETENTION_MIN_DAYS <= days <= REPORT_RETENTION_MAX_DAYS:
        return days
    return None


def normalize_report_retention_policies(
    value: Any,
) -> dict[str, dict[str, Any]]:
    normalized = default_report_retention_policies()
    if not isinstance(value, Mapping):
        return normalized
    for report_type in REPORT_RETENTION_TYPES:
        policy = value.get(report_type)
        if not isinstance(policy, Mapping):
            continue
        mode = str(policy.get("mode") or "").strip().upper()
        if mode == "FOREVER":
            normalized[report_type] = {"mode": "FOREVER", "days": None}
        elif mode == "DAYS":
            days = _retention_days(policy.get("days"))
            if days is not None:
                normalized[report_type] = {"mode": "DAYS", "days": days}
    return normalized


def validate_report_retention_policies(
    value: Any,
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise ValueError("보고서 보존 정책은 객체 형식이어야 합니다.")
    unknown = set(value) - set(REPORT_RETENTION_TYPES)
    if unknown:
        raise ValueError("지원하지 않는 보고서 유형이 포함되어 있습니다.")
    normalized: dict[str, dict[str, Any]] = {}
    for report_type in REPORT_RETENTION_TYPES:
        policy = value.get(report_type)
        if not isinstance(policy, Mapping):
            raise ValueError(f"{report_type} 보존 정책을 선택하세요.")
        mode = str(policy.get("mode") or "").strip().upper()
        if mode == "FOREVER":
            normalized[report_type] = {"mode": "FOREVER", "days": None}
            continue
        if mode != "DAYS":
            raise ValueError(f"{report_type} 보존 방식을 확인하세요.")
        days = _retention_days(policy.get("days"))
        if days is None:
            raise ValueError(
                f"{report_type} 보존 기간은 {REPORT_RETENTION_MIN_DAYS}~"
                f"{REPORT_RETENTION_MAX_DAYS}일 사이여야 합니다."
            )
        normalized[report_type] = {"mode": "DAYS", "days": days}
    return normalized


def _explicit_report_retention_policy(
    settings: Any,
    report_type: str,
) -> Optional[dict[str, Any]]:
    if not isinstance(settings, Mapping):
        return None
    policies = settings.get(REPORT_RETENTION_SETTINGS_KEY)
    if not isinstance(policies, Mapping):
        return None
    policy = policies.get(report_type)
    if not isinstance(policy, Mapping):
        return None
    mode = str(policy.get("mode") or "").strip().upper()
    if mode == "FOREVER":
        return {"mode": "FOREVER", "days": None}
    if mode != "DAYS":
        return None
    days = _retention_days(policy.get("days"))
    return {"mode": "DAYS", "days": days} if days is not None else None


def _artifact_storage_usage() -> dict[str, Any]:
    unavailable = {
        "status": "UNAVAILABLE",
        "total_bytes": None,
        "used_bytes": None,
        "free_bytes": None,
        "used_percent": None,
    }
    try:
        output_root = Path(
            os.environ.get("REPORT_OUTPUT_DIR", "/app/output/report")
        ).resolve(strict=True)
        if not output_root.is_dir():
            return unavailable
        total, used, free = disk_usage(output_root)
    except (OSError, RuntimeError, ValueError):
        return unavailable
    usable = used + free
    if total <= 0 or usable <= 0:
        return unavailable
    used_percent = round(used / usable * 100, 1)
    if used_percent >= 90:
        status = "CRITICAL"
    elif used_percent >= 80:
        status = "WARNING"
    else:
        status = "NORMAL"
    return {
        "status": status,
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "used_percent": used_percent,
    }


def _local_report_artifact_paths(
    storage_uris: list[str],
    *,
    include_legacy: bool = True,
    reject_outside: bool = False,
) -> tuple[set[Path], int]:
    try:
        output_root = Path(
            os.environ.get("REPORT_OUTPUT_DIR", "/app/output/report")
        ).resolve()
    except (OSError, ValueError):
        return set(), max(1, len(set(storage_uris)))

    candidates: set[Path] = set()
    failed = 0
    for storage_uri in set(storage_uris):
        try:
            parsed = urlparse(storage_uri)
            if parsed.scheme != "file":
                continue
            if parsed.netloc not in {"", "localhost"}:
                if reject_outside:
                    failed += 1
                continue
            local_path = unquote(parsed.path)
            if "\x00" in local_path:
                failed += 1
                continue
            if os.name == "nt" and re.match(r"^/[A-Za-z]:", local_path):
                local_path = local_path[1:]
            candidate = Path(local_path).resolve()
        except (OSError, ValueError):
            failed += 1
            continue
        try:
            candidate.relative_to(output_root)
        except ValueError:
            if reject_outside:
                failed += 1
            continue
        candidates.add(candidate)
        if not include_legacy:
            continue
        report_match = re.fullmatch(
            r"ncp_report_([A-Za-z0-9_-]+)\.(?:html|json)",
            candidate.name,
        )
        if report_match:
            suffix = report_match.group(1)
            candidates.update(
                candidate.with_name(f"{prefix}_{suffix}.json")
                for prefix in _LEGACY_DIAGNOSTIC_PREFIXES
            )
    return candidates, failed


def _artifact_fingerprint(candidate: Path) -> tuple[str, int]:
    digest = sha256()
    with candidate.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest(), candidate.stat().st_size


def _remove_queued_artifact(
    storage_uri: str,
    expected_sha256: str,
    expected_byte_size: int,
) -> tuple[bool, str]:
    candidates, failed = _local_report_artifact_paths(
        [storage_uri],
        include_legacy=False,
    )
    if failed or len(candidates) != 1:
        return False, "UNSAFE_URI"
    candidate = next(iter(candidates))
    try:
        actual_sha256, actual_byte_size = _artifact_fingerprint(candidate)
    except FileNotFoundError:
        return True, "MISSING"
    except (OSError, ValueError):
        return False, "READ_FAILED"
    if (
        actual_byte_size != expected_byte_size
        or not secrets.compare_digest(actual_sha256, expected_sha256)
    ):
        return False, "CONTENT_CHANGED"
    try:
        candidate.unlink()
    except FileNotFoundError:
        return True, "MISSING"
    except (OSError, ValueError):
        return False, "REMOVE_FAILED"
    return True, "REMOVED"


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
        email, display_name = _validate_user_fields(email, display_name)
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
        artifact_storage = _artifact_storage_usage()
        if allowed_environments is not None and not allowed_environments:
            return {
                "summary": {
                    "customer_count": 0,
                    "public_count": 0,
                    "gov_count": 0,
                    "issue_count": 0,
                },
                "issue_customers": [],
                "artifact_storage": artifact_storage,
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
        return {
            "summary": summary,
            "issue_customers": issue_customers,
            "artifact_storage": artifact_storage,
        }

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
            stored_settings = (
                report_settings["settings"] if report_settings else None
            )
            tenant["report_options"] = normalize_report_options(
                stored_settings
            )
            tenant["retention_policies"] = (
                normalize_report_retention_policies(
                    stored_settings.get(REPORT_RETENTION_SETTINGS_KEY)
                    if isinstance(stored_settings, Mapping)
                    else None
                )
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
        *,
        retention_policies: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        normalized = validate_report_options(options)
        normalized_retention = (
            validate_report_retention_policies(retention_policies)
            if retention_policies is not None
            else None
        )
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tenant.id
                FROM control.tenants tenant
                WHERE tenant.id = %s AND tenant.status <> 'OFFBOARDED'
                FOR UPDATE
                """,
                (tenant_id,),
            )
            tenant = cursor.fetchone()
            if not tenant:
                raise ValueError("활성 고객을 찾을 수 없습니다.")
            cursor.execute(
                """
                INSERT INTO control.tenant_report_settings (tenant_id)
                VALUES (%s)
                ON CONFLICT (tenant_id) DO NOTHING
                """,
                (tenant_id,),
            )
            cursor.execute(
                """
                SELECT settings
                FROM control.tenant_report_settings
                WHERE tenant_id = %s
                FOR UPDATE
                """,
                (tenant_id,),
            )
            settings_row = cursor.fetchone()
            stored_settings = (
                settings_row["settings"]
                if settings_row and isinstance(settings_row["settings"], Mapping)
                else {}
            )
            legacy_policies = _preserved_legacy_analysis_policies(
                stored_settings
            )
            if legacy_policies:
                normalized["operational_analysis"]["policies"] = (
                    legacy_policies
                )
            settings = dict(normalized)
            if normalized_retention is not None:
                settings[REPORT_RETENTION_SETTINGS_KEY] = normalized_retention
            elif REPORT_RETENTION_SETTINGS_KEY in stored_settings:
                settings[REPORT_RETENTION_SETTINGS_KEY] = stored_settings[
                    REPORT_RETENTION_SETTINGS_KEY
                ]
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
                    json.dumps(settings, ensure_ascii=False),
                    actor_id,
                ),
            )
            changed_fields: dict[str, Any] = {"report_options": normalized}
            if normalized_retention is not None:
                changed_fields[REPORT_RETENTION_SETTINGS_KEY] = (
                    normalized_retention
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
                    json.dumps(changed_fields, ensure_ascii=False),
                ),
            )
        return normalized

    def update_report_retention(
        self,
        tenant_id: str,
        policies: dict[str, Any],
        actor_id: str,
    ) -> dict[str, dict[str, Any]]:
        normalized = validate_report_retention_policies(policies)
        updated = self.bulk_update_report_retention(
            [tenant_id],
            normalized,
            actor_id,
        )
        if updated != 1:
            raise ValueError("활성 고객을 찾을 수 없습니다.")
        return normalized

    def bulk_update_report_retention(
        self,
        tenant_ids: list[str],
        policies: dict[str, Any],
        actor_id: str,
        *,
        allowed_environments: Optional[set[str]] = None,
    ) -> int:
        normalized = validate_report_retention_policies(policies)
        try:
            normalized_tenant_ids = sorted({
                str(UUID(str(tenant_id))) for tenant_id in tenant_ids
            })
        except (TypeError, ValueError) as exc:
            raise ValueError("고객 선택값이 올바르지 않습니다.") from exc
        if not normalized_tenant_ids:
            raise ValueError("보존 정책을 적용할 고객을 하나 이상 선택하세요.")
        if len(normalized_tenant_ids) > 500:
            raise ValueError("한 번에 최대 500개 고객까지 설정할 수 있습니다.")
        if allowed_environments is not None and not allowed_environments:
            raise ValueError("접근 가능한 고객을 찾을 수 없습니다.")

        environment_filter = ""
        parameters: list[Any] = [normalized_tenant_ids]
        if allowed_environments is not None:
            environment_filter = "AND environment = ANY(%s)"
            parameters.append(sorted(allowed_environments))
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id
                FROM control.tenants
                WHERE id = ANY(%s::uuid[])
                  AND status = 'ACTIVE'
                  {environment_filter}
                ORDER BY id
                FOR UPDATE
                """,
                tuple(parameters),
            )
            matched_ids = [str(row["id"]) for row in cursor.fetchall()]
            if matched_ids != normalized_tenant_ids:
                raise ValueError(
                    "선택 항목에 접근할 수 없거나 비활성 고객이 있습니다."
                )
            cursor.execute(
                """
                INSERT INTO control.tenant_report_settings (tenant_id)
                SELECT unnest(%s::uuid[])
                ON CONFLICT (tenant_id) DO NOTHING
                """,
                (normalized_tenant_ids,),
            )
            cursor.execute(
                """
                UPDATE control.tenant_report_settings
                SET settings = settings || jsonb_build_object(
                        'retention_policies', %s::jsonb
                    ),
                    updated_by = %s
                WHERE tenant_id = ANY(%s::uuid[])
                """,
                (
                    json.dumps(normalized, ensure_ascii=False),
                    actor_id,
                    normalized_tenant_ids,
                ),
            )
            cursor.execute(
                """
                INSERT INTO audit.data_change_logs (
                    tenant_id, actor_id, table_name, record_id,
                    operation, changed_fields
                )
                SELECT tenant.id, %s, 'control.tenant_report_settings',
                       tenant.id::text, 'UPDATE', %s::jsonb
                FROM control.tenants tenant
                WHERE tenant.id = ANY(%s::uuid[])
                """,
                (
                    actor_id,
                    json.dumps({
                        REPORT_RETENTION_SETTINGS_KEY: normalized,
                    }, ensure_ascii=False),
                    normalized_tenant_ids,
                ),
            )
        return len(normalized_tenant_ids)

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
            payload = dict(snapshot["normalized_data"]) if snapshot else {}
            cursor.execute(
                f"SELECT configuration FROM {schema}.network_configuration_snapshots "
                "WHERE report_run_id = %s",
                (report_id,),
            )
            network_snapshot = cursor.fetchone()
            if network_snapshot:
                payload["infrastructure"] = replace_configuration_records(
                    payload.get("infrastructure"),
                    network_snapshot["configuration"],
                )
            report["snapshot"] = payload
            return report

    def report_cleanup_candidates(
        self,
        allowed_environments: Optional[set[str]] = None,
    ) -> list[dict[str, Any]]:
        """Return a dry-run view of reports that may be explicitly deleted."""
        if allowed_environments is not None and not allowed_environments:
            return []
        environment_filter = ""
        parameters: tuple[Any, ...] = ()
        if allowed_environments is not None:
            environment_filter = "WHERE report.environment = ANY(%s)"
            parameters = (sorted(allowed_environments),)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                WITH latest_reports AS (
                    SELECT DISTINCT ON (
                        tenant_id, cloud_account_id, report_type
                    ) id
                    FROM control.report_runs
                    WHERE status IN ('SUCCESS', 'PARTIAL_SUCCESS')
                    ORDER BY tenant_id, cloud_account_id, report_type,
                             completed_at DESC NULLS LAST,
                             created_at DESC, id DESC
                ),
                artifacts AS (
                    SELECT report_run_id,
                           count(*)::integer AS artifact_count,
                           COALESCE(sum(byte_size), 0)::bigint AS artifact_bytes,
                           max(retention_until) AS retention_until
                    FROM control.report_artifacts
                    GROUP BY report_run_id
                )
                SELECT report.id, report.tenant_id, tenant.customer_name,
                       tenant.environment,
                       account.display_name AS account_name,
                       report.report_type, report.status,
                       report.period_start, report.period_end,
                       report.created_at, report.completed_at,
                       COALESCE(artifacts.artifact_count, 0) AS artifact_count,
                       COALESCE(artifacts.artifact_bytes, 0) AS artifact_bytes,
                       artifacts.retention_until,
                       report.cleanup_requested_at,
                       report.cleanup_reason,
                       report.cleanup_attempt_count,
                       report.cleanup_next_attempt_at,
                       report.cleanup_last_error_code,
                       CASE
                           WHEN report.status IN ('QUEUED', 'RUNNING', 'RETRYING')
                               THEN 'ACTIVE'
                           WHEN report.cleanup_requested_at IS NOT NULL
                               THEN 'CLEANUP_QUEUED'
                           WHEN report_settings.settings
                                    -> 'retention_policies'
                                    -> report.report_type
                                    ->> 'mode' = 'FOREVER'
                               THEN 'POLICY_FOREVER'
                           WHEN latest.id IS NOT NULL THEN 'LATEST'
                           WHEN artifacts.retention_until >= CURRENT_DATE
                               THEN 'RETENTION'
                           ELSE NULL
                       END AS protection_reason
                FROM control.report_runs report
                JOIN control.tenants tenant ON tenant.id = report.tenant_id
                LEFT JOIN control.cloud_accounts account
                    ON account.id = report.cloud_account_id
                LEFT JOIN control.tenant_report_settings report_settings
                    ON report_settings.tenant_id = report.tenant_id
                LEFT JOIN latest_reports latest ON latest.id = report.id
                LEFT JOIN artifacts ON artifacts.report_run_id = report.id
                {environment_filter}
                ORDER BY (
                             report.status IN (
                                 'QUEUED', 'RUNNING', 'RETRYING'
                             )
                             OR report.cleanup_requested_at IS NOT NULL
                             OR report_settings.settings
                                    -> 'retention_policies'
                                    -> report.report_type
                                    ->> 'mode' = 'FOREVER'
                             OR latest.id IS NOT NULL
                             OR COALESCE(
                                 artifacts.retention_until >= CURRENT_DATE,
                                 false
                             )
                         ),
                         report.created_at, report.id
                LIMIT 500
                """,
                parameters,
            )
            reports = cursor.fetchall()
        for report in reports:
            report["eligible"] = report.get("protection_reason") is None
        return reports

    def request_report_cleanup(
        self,
        report_ids: Optional[list[str]],
        actor_id: str,
        *,
        allowed_environments: Optional[set[str]] = None,
        all_eligible: bool = False,
    ) -> dict[str, int]:
        if all_eligible and report_ids:
            raise ValueError("전체 정리와 개별 선택을 동시에 요청할 수 없습니다.")
        if allowed_environments is not None and not allowed_environments:
            return {
                "queued_count": 0,
                "already_queued_count": 0,
                "protected_count": 0,
            }
        normalized_ids: list[str] = []
        if all_eligible:
            normalized_ids = [
                str(report["id"])
                for report in self.report_cleanup_candidates(
                    allowed_environments
                )
                if report.get("eligible")
            ]
            if not normalized_ids:
                return {
                    "queued_count": 0,
                    "already_queued_count": 0,
                    "protected_count": 0,
                }
        else:
            try:
                normalized_ids = list(dict.fromkeys(
                    str(UUID(str(report_id))) for report_id in (report_ids or [])
                ))
            except (TypeError, ValueError) as exc:
                raise ValueError("보고서 선택값이 올바르지 않습니다.") from exc
            if not normalized_ids:
                raise ValueError("정리할 보고서를 하나 이상 선택하세요.")
            if len(normalized_ids) > 500:
                raise ValueError("한 번에 최대 500건까지 선택할 수 있습니다.")

        filters: list[str] = []
        parameters: list[Any] = []
        if allowed_environments is not None:
            filters.append("report.environment = ANY(%s)")
            parameters.append(sorted(allowed_environments))
        filters.append("report.id = ANY(%s::uuid[])")
        parameters.append(normalized_ids)
        where_clause = " AND ".join(filters) if filters else "TRUE"

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT report.id, report.cleanup_requested_at,
                       CASE
                           WHEN report.status IN ('QUEUED', 'RUNNING', 'RETRYING')
                               THEN 'ACTIVE'
                           WHEN report.cleanup_requested_at IS NOT NULL
                               THEN 'CLEANUP_QUEUED'
                           WHEN report_settings.settings
                                    -> 'retention_policies'
                                    -> report.report_type
                                    ->> 'mode' = 'FOREVER'
                               THEN 'POLICY_FOREVER'
                           WHEN report.id = (
                               SELECT latest.id
                               FROM control.report_runs latest
                               WHERE latest.tenant_id = report.tenant_id
                                 AND latest.cloud_account_id IS NOT DISTINCT FROM
                                     report.cloud_account_id
                                 AND latest.report_type = report.report_type
                                 AND latest.status IN (
                                     'SUCCESS', 'PARTIAL_SUCCESS'
                                 )
                               ORDER BY latest.completed_at DESC NULLS LAST,
                                        latest.created_at DESC, latest.id DESC
                               LIMIT 1
                           ) THEN 'LATEST'
                           WHEN EXISTS (
                               SELECT 1
                               FROM control.report_artifacts artifact
                               WHERE artifact.report_run_id = report.id
                                 AND artifact.retention_until >= CURRENT_DATE
                           ) THEN 'RETENTION'
                           ELSE NULL
                       END AS protection_reason
                FROM control.report_runs report
                LEFT JOIN control.tenant_report_settings report_settings
                    ON report_settings.tenant_id = report.tenant_id
                WHERE {where_clause}
                ORDER BY report.id
                """,
                tuple(parameters),
            )
            rows = cursor.fetchall()
            if not all_eligible and {
                str(row["id"]) for row in rows
            } != set(normalized_ids):
                raise ValueError(
                    "선택 항목에 접근할 수 없거나 존재하지 않는 보고서가 있습니다."
                )

            already_queued = sum(
                row.get("protection_reason") == "CLEANUP_QUEUED"
                for row in rows
            )
            protected = sum(
                row.get("protection_reason") not in (None, "CLEANUP_QUEUED")
                for row in rows
            )
            eligible_ids = [
                str(row["id"])
                for row in rows
                if row.get("protection_reason") is None
            ]
            queued_rows: list[dict[str, Any]] = []
            if eligible_ids:
                cursor.execute(
                    """
                    UPDATE control.report_runs report
                    SET cleanup_requested_at = clock_timestamp(),
                        cleanup_requested_by = %s,
                        cleanup_reason = 'MANUAL',
                        cleanup_attempt_count = 0,
                        cleanup_next_attempt_at = clock_timestamp(),
                        cleanup_last_error_code = NULL
                    WHERE report.id = ANY(%s::uuid[])
                      AND report.cleanup_requested_at IS NULL
                      AND report.status NOT IN ('QUEUED', 'RUNNING', 'RETRYING')
                      AND NOT EXISTS (
                          SELECT 1
                          FROM control.tenant_report_settings settings
                          WHERE settings.tenant_id = report.tenant_id
                            AND settings.settings
                                  -> 'retention_policies'
                                  -> report.report_type
                                  ->> 'mode' = 'FOREVER'
                      )
                      AND report.id IS DISTINCT FROM (
                          SELECT latest.id
                          FROM control.report_runs latest
                          WHERE latest.tenant_id = report.tenant_id
                            AND latest.cloud_account_id IS NOT DISTINCT FROM
                                report.cloud_account_id
                            AND latest.report_type = report.report_type
                            AND latest.status IN (
                                'SUCCESS', 'PARTIAL_SUCCESS'
                            )
                          ORDER BY latest.completed_at DESC NULLS LAST,
                                   latest.created_at DESC, latest.id DESC
                          LIMIT 1
                      )
                      AND NOT EXISTS (
                          SELECT 1
                          FROM control.report_artifacts artifact
                          WHERE artifact.report_run_id = report.id
                            AND artifact.retention_until >= CURRENT_DATE
                      )
                    RETURNING report.id, report.tenant_id
                    """,
                    (actor_id, eligible_ids),
                )
                queued_rows = cursor.fetchall()
                if queued_rows:
                    cursor.execute(
                        """
                        INSERT INTO audit.data_change_logs (
                            tenant_id, actor_id, table_name, record_id,
                            operation, changed_fields
                        )
                        SELECT report.tenant_id, %s,
                               'control.report_runs', report.id::text,
                               'UPDATE', %s::jsonb
                        FROM control.report_runs report
                        WHERE report.id = ANY(%s::uuid[])
                        """,
                        (
                            actor_id,
                            json.dumps({
                                "cleanup_requested": True,
                                "cleanup_reason": "MANUAL",
                            }),
                            [str(row["id"]) for row in queued_rows],
                        ),
                    )
            protected += len(eligible_ids) - len(queued_rows)
        return {
            "queued_count": len(queued_rows),
            "already_queued_count": int(already_queued),
            "protected_count": int(protected),
        }

    def enqueue_expired_report_cleanup(self, *, limit: int = 100) -> int:
        """만료된 명시적 DAYS 정책 보고서를 durable 정리 큐에 넣는다."""

        limit = max(1, min(int(limit), 1_000))
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                WITH expired AS (
                    SELECT report.id, report.tenant_id,
                           parsed.retention_days,
                           COALESCE(
                               report.completed_at, report.created_at
                           ) AS retention_base_at
                    FROM control.report_runs report
                    JOIN control.tenant_report_settings settings
                      ON settings.tenant_id = report.tenant_id
                    CROSS JOIN LATERAL (
                        SELECT settings.settings
                                   -> 'retention_policies'
                                   -> report.report_type AS value
                    ) policy
                    CROSS JOIN LATERAL (
                        SELECT CASE
                            WHEN jsonb_typeof(policy.value) = 'object'
                             AND policy.value ->> 'mode' = 'DAYS'
                             AND jsonb_typeof(policy.value -> 'days') = 'number'
                             AND policy.value ->> 'days' ~ '^[1-9][0-9]{0,3}$'
                            THEN (policy.value ->> 'days')::integer
                            ELSE NULL
                        END AS retention_days
                    ) parsed
                    WHERE report.cleanup_requested_at IS NULL
                      AND report.status NOT IN ('QUEUED', 'RUNNING', 'RETRYING')
                      AND parsed.retention_days BETWEEN 1 AND 3650
                      AND COALESCE(report.completed_at, report.created_at)
                            + make_interval(days => parsed.retention_days)
                          <= clock_timestamp()
                      AND NOT EXISTS (
                          SELECT 1
                          FROM control.report_artifacts artifact
                          WHERE artifact.report_run_id = report.id
                            AND artifact.retention_until >= CURRENT_DATE
                      )
                    ORDER BY COALESCE(
                                 report.completed_at, report.created_at
                             ), report.id
                    FOR UPDATE OF report SKIP LOCKED
                    LIMIT %s
                )
                UPDATE control.report_runs report
                SET cleanup_requested_at = clock_timestamp(),
                    cleanup_requested_by = NULL,
                    cleanup_reason = 'RETENTION_POLICY',
                    cleanup_attempt_count = 0,
                    cleanup_next_attempt_at = clock_timestamp(),
                    cleanup_last_error_code = NULL
                FROM expired
                WHERE report.id = expired.id
                RETURNING report.id, report.tenant_id
                """,
                (limit,),
            )
            queued_rows = cursor.fetchall()
            if queued_rows:
                cursor.execute(
                    """
                    INSERT INTO audit.data_change_logs (
                        tenant_id, actor_id, table_name, record_id,
                        operation, changed_fields
                    )
                    SELECT report.tenant_id, NULL,
                           'control.report_runs', report.id::text,
                           'UPDATE', %s::jsonb
                    FROM control.report_runs report
                    WHERE report.id = ANY(%s::uuid[])
                    """,
                    (
                        json.dumps({
                            "automated": True,
                            "cleanup_requested": True,
                            "cleanup_reason": "RETENTION_POLICY_EXPIRED",
                        }),
                        [str(row["id"]) for row in queued_rows],
                    ),
                )
        return len(queued_rows)

    def _record_report_cleanup_failure(
        self,
        report_id: str,
        error_code: str,
        *,
        terminal: bool,
    ) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            if terminal:
                cursor.execute(
                    """
                    UPDATE control.report_runs
                    SET cleanup_requested_at = NULL,
                        cleanup_requested_by = NULL,
                        cleanup_reason = NULL,
                        cleanup_next_attempt_at = NULL,
                        cleanup_last_error_code = %s
                    WHERE id = %s
                    """,
                    (error_code, report_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE control.report_runs
                    SET cleanup_last_error_code = %s
                    WHERE id = %s
                    """,
                    (error_code, report_id),
                )

    def process_requested_report_cleanup(
        self,
        *,
        limit: int = 100,
    ) -> dict[str, int]:
        """정리 요청을 짧게 claim한 뒤 보고서별 독립 transaction으로 처리한다."""

        limit = max(1, min(int(limit), 1_000))
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                WITH due AS (
                    SELECT id
                    FROM control.report_runs
                    WHERE cleanup_requested_at IS NOT NULL
                      AND cleanup_next_attempt_at <= clock_timestamp()
                    ORDER BY cleanup_next_attempt_at, cleanup_requested_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT %s
                )
                UPDATE control.report_runs report
                SET cleanup_attempt_count = cleanup_attempt_count + 1,
                    cleanup_next_attempt_at = clock_timestamp()
                        + make_interval(
                            mins => 5 * (
                                1 << LEAST(cleanup_attempt_count, 8)
                            )
                        ),
                    cleanup_last_error_code = NULL
                FROM due
                WHERE report.id = due.id
                RETURNING report.id, report.cleanup_requested_by,
                          report.cleanup_reason
                """,
                (limit,),
            )
            claimed = cursor.fetchall()

        deleted_count = 0
        protected_count = 0
        failed_count = 0
        removed_files = 0
        pending_files = 0
        for request_row in claimed:
            report_id = str(request_row["id"])
            reason = str(request_row.get("cleanup_reason") or "")
            requested_by = request_row.get("cleanup_requested_by")
            if reason not in {"MANUAL", "RETENTION_POLICY"} or (
                reason == "MANUAL" and requested_by is None
            ):
                self._record_report_cleanup_failure(
                    report_id,
                    "INVALID_CLEANUP_REQUEST",
                    terminal=True,
                )
                failed_count += 1
                continue
            try:
                result = self.delete_report(
                    report_id,
                    str(requested_by) if requested_by is not None else None,
                    protect_latest=reason == "MANUAL",
                    automated_retention=reason == "RETENTION_POLICY",
                )
            except ReportCleanupProtectedError:
                self._record_report_cleanup_failure(
                    report_id,
                    "PROTECTED_AT_EXECUTION",
                    terminal=True,
                )
                protected_count += 1
            except Exception as exc:
                self._record_report_cleanup_failure(
                    report_id,
                    "DELETE_FAILED",
                    terminal=False,
                )
                LOGGER.warning(
                    "Report cleanup %s failed with %s and remains queued.",
                    report_id,
                    type(exc).__name__,
                )
                failed_count += 1
            else:
                deleted_count += 1
                removed_files += int(result["removed_artifact_files"])
                pending_files += int(result["failed_artifact_files"])

        return {
            "claimed_count": len(claimed),
            "deleted_count": deleted_count,
            "protected_count": protected_count,
            "failed_count": failed_count,
            "removed_artifact_files": removed_files,
            "pending_artifact_files": pending_files,
        }

    @staticmethod
    def _other_artifact_storage_uris(
        cursor: Any,
        storage_uris: list[str],
        *,
        owner_column: str,
        owner_id: str,
    ) -> list[str]:
        if not storage_uris:
            return []
        if owner_column not in {"report_run_id", "tenant_id"}:
            raise ValueError("Unsupported artifact owner column.")
        cursor.execute(
            f"""
            SELECT DISTINCT storage_uri
            FROM (
                SELECT storage_uri
                FROM control.report_artifacts
                WHERE {owner_column} <> %s AND storage_uri = ANY(%s::text[])
                UNION ALL
                SELECT storage_uri
                FROM public_data.raw_payload_refs
                WHERE {owner_column} <> %s AND storage_uri = ANY(%s::text[])
                UNION ALL
                SELECT storage_uri
                FROM gov_data.raw_payload_refs
                WHERE {owner_column} <> %s AND storage_uri = ANY(%s::text[])
                UNION ALL
                SELECT artifact_uri AS storage_uri
                FROM public_data.metric_series
                WHERE {owner_column} <> %s AND artifact_uri = ANY(%s::text[])
                UNION ALL
                SELECT artifact_uri AS storage_uri
                FROM gov_data.metric_series
                WHERE {owner_column} <> %s AND artifact_uri = ANY(%s::text[])
            ) referenced_artifacts
            """,
            (
                owner_id, storage_uris,
                owner_id, storage_uris,
                owner_id, storage_uris,
                owner_id, storage_uris,
                owner_id, storage_uris,
            ),
        )
        return [
            str(row["storage_uri"])
            for row in cursor.fetchall()
            if row.get("storage_uri")
        ]

    @staticmethod
    def _referenced_artifact_storage_uris(
        cursor: Any,
        storage_uris: list[str],
    ) -> set[str]:
        if not storage_uris:
            return set()
        cursor.execute(
            """
            SELECT DISTINCT storage_uri
            FROM (
                SELECT storage_uri FROM control.report_artifacts
                WHERE storage_uri = ANY(%s::text[])
                UNION ALL
                SELECT storage_uri FROM public_data.raw_payload_refs
                WHERE storage_uri = ANY(%s::text[])
                UNION ALL
                SELECT storage_uri FROM gov_data.raw_payload_refs
                WHERE storage_uri = ANY(%s::text[])
                UNION ALL
                SELECT artifact_uri AS storage_uri FROM public_data.metric_series
                WHERE artifact_uri = ANY(%s::text[])
                UNION ALL
                SELECT artifact_uri AS storage_uri FROM gov_data.metric_series
                WHERE artifact_uri = ANY(%s::text[])
            ) referenced_artifacts
            """,
            (storage_uris,) * 5,
        )
        return {
            str(row["storage_uri"])
            for row in cursor.fetchall()
            if row.get("storage_uri")
        }

    def _queue_artifact_cleanup(
        self,
        cursor: Any,
        *,
        tenant_id: str,
        storage_uris: list[str],
        owner_column: str,
        owner_id: str,
    ) -> tuple[Optional[str], int, int]:
        candidates, failed = _local_report_artifact_paths(
            storage_uris,
            reject_outside=True,
        )
        if failed:
            raise ValueError(
                f"로컬 보고서 경로 {failed}건을 안전하게 확인하지 못했습니다."
            )
        lookup_uris = list(dict.fromkeys((
            *storage_uris,
            *(candidate.as_uri() for candidate in candidates),
        )))
        shared_uris = self._other_artifact_storage_uris(
            cursor,
            lookup_uris,
            owner_column=owner_column,
            owner_id=owner_id,
        )
        shared_paths, _ = _local_report_artifact_paths(
            shared_uris,
            include_legacy=True,
        )
        shared_candidates = candidates & shared_paths
        candidates.difference_update(shared_paths)

        entries: list[tuple[str, str, int]] = []
        for candidate in sorted(candidates):
            try:
                checksum, byte_size = _artifact_fingerprint(candidate)
            except FileNotFoundError:
                continue
            except (OSError, ValueError):
                failed += 1
                continue
            entries.append((candidate.as_uri(), checksum, byte_size))
        if failed:
            raise ValueError(
                f"로컬 보고서 파일 {failed}건을 안전하게 확인하지 못했습니다."
            )
        if not entries:
            return None, 0, len(shared_candidates)

        operation_id = str(uuid4())
        for storage_uri, checksum, byte_size in entries:
            cursor.execute(
                """
                INSERT INTO control.artifact_cleanup_outbox (
                    operation_id, tenant_id, storage_uri,
                    expected_sha256, expected_byte_size
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    operation_id, tenant_id, storage_uri,
                    checksum, byte_size,
                ),
            )
        return operation_id, len(entries), len(shared_candidates)

    def retry_artifact_cleanup(
        self,
        *,
        limit: int = 100,
        operation_id: Optional[str] = None,
    ) -> tuple[int, int]:
        limit = max(1, min(int(limit), 1_000))
        operation_filter = ""
        parameters: list[Any] = []
        if operation_id:
            operation_filter = "AND operation_id = %s"
            parameters.append(operation_id)
        parameters.append(limit)

        removed = 0
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, storage_uri, expected_sha256, expected_byte_size
                FROM control.artifact_cleanup_outbox
                WHERE next_attempt_at <= clock_timestamp()
                  {operation_filter}
                ORDER BY next_attempt_at, created_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT %s
                """,
                tuple(parameters),
            )
            rows = cursor.fetchall()
            referenced_uris = self._referenced_artifact_storage_uris(
                cursor,
                [str(row["storage_uri"]) for row in rows],
            )
            for row in rows:
                if str(row["storage_uri"]) in referenced_uris:
                    completed, result_code = False, "STILL_REFERENCED"
                else:
                    try:
                        completed, result_code = _remove_queued_artifact(
                            str(row["storage_uri"]),
                            str(row["expected_sha256"]).strip(),
                            int(row["expected_byte_size"]),
                        )
                    except (KeyError, TypeError, ValueError):
                        completed, result_code = False, "INVALID_OUTBOX_ROW"
                if completed:
                    cursor.execute(
                        "DELETE FROM control.artifact_cleanup_outbox WHERE id = %s",
                        (row["id"],),
                    )
                    if result_code == "REMOVED":
                        removed += 1
                else:
                    cursor.execute(
                        """
                        UPDATE control.artifact_cleanup_outbox
                        SET attempt_count = attempt_count + 1,
                            next_attempt_at = clock_timestamp() + make_interval(
                                mins => 5 * (1 << LEAST(attempt_count, 8))
                            ),
                            last_error_code = %s
                        WHERE id = %s
                        """,
                        (result_code, row["id"]),
                    )

            count_filter = ""
            count_parameters: tuple[Any, ...] = ()
            if operation_id:
                count_filter = "WHERE operation_id = %s"
                count_parameters = (operation_id,)
            cursor.execute(
                "SELECT count(*) AS count "
                "FROM control.artifact_cleanup_outbox "
                f"{count_filter}",
                count_parameters,
            )
            pending = int(cursor.fetchone()["count"])
        return removed, pending

    def _finish_artifact_cleanup(
        self,
        operation_id: Optional[str],
        queued_count: int,
    ) -> tuple[int, int]:
        if not operation_id:
            return 0, 0
        try:
            return self.retry_artifact_cleanup(operation_id=operation_id)
        except Exception:
            LOGGER.warning(
                "Artifact cleanup operation %s was deferred for retry.",
                operation_id,
            )
            return 0, queued_count

    def delete_report(
        self,
        report_id: str,
        actor_id: Optional[str],
        *,
        protect_latest: bool = False,
        automated_retention: bool = False,
    ) -> dict[str, Any]:
        if automated_retention and actor_id is not None:
            raise ValueError("자동 보존 정리는 시스템 actor로 실행해야 합니다.")
        storage_uris: list[str] = []
        cleanup_operation_id: Optional[str] = None
        cleanup_queued_count = 0
        shared_artifact_count = 0
        retention_audit: dict[str, Any] = {}
        result: dict[str, Any]
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT report.id, report.tenant_id, report.environment,
                       report.status, report.report_type,
                       report.completed_at, report.created_at,
                       report.cleanup_reason,
                       tenant.customer_name,
                       report.id = (
                           SELECT latest.id
                           FROM control.report_runs latest
                           WHERE latest.tenant_id = report.tenant_id
                             AND latest.cloud_account_id IS NOT DISTINCT FROM
                                 report.cloud_account_id
                             AND latest.report_type = report.report_type
                             AND latest.status IN ('SUCCESS', 'PARTIAL_SUCCESS')
                           ORDER BY latest.completed_at DESC NULLS LAST,
                                    latest.created_at DESC, latest.id DESC
                           LIMIT 1
                       ) AS is_latest,
                       EXISTS (
                           SELECT 1
                           FROM control.report_artifacts artifact
                           WHERE artifact.report_run_id = report.id
                             AND artifact.retention_until >= CURRENT_DATE
                       ) AS retention_protected
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
                raise ReportCleanupProtectedError(
                    "실행 중인 보고서는 삭제할 수 없습니다."
                )
            cursor.execute(
                """
                SELECT settings, clock_timestamp() AS evaluated_at
                FROM control.tenant_report_settings
                WHERE tenant_id = %s
                FOR UPDATE
                """,
                (report["tenant_id"],),
            )
            settings_row = cursor.fetchone()
            policy = _explicit_report_retention_policy(
                settings_row.get("settings") if settings_row else None,
                str(report["report_type"]),
            )
            if policy and policy["mode"] == "FOREVER":
                raise ReportCleanupProtectedError(
                    "영구 보존 정책이 적용된 보고서는 정리할 수 없습니다."
                )
            if protect_latest and bool(report.get("is_latest")):
                raise ReportCleanupProtectedError(
                    "계정별 최신 정상 보고서는 정리할 수 없습니다."
                )
            if bool(report.get("retention_protected")):
                raise ReportCleanupProtectedError(
                    "보존 기한이 지나지 않은 보고서는 정리할 수 없습니다."
                )
            if automated_retention:
                if not policy or policy["mode"] != "DAYS" or not settings_row:
                    raise ReportCleanupProtectedError(
                        "유효한 기간 보존 정책을 확인할 수 없습니다."
                    )
                retention_base = report.get("completed_at") or report.get(
                    "created_at"
                )
                evaluated_at = settings_row.get("evaluated_at")
                if retention_base is None or evaluated_at is None:
                    raise ReportCleanupProtectedError(
                        "보고서 보존 기간의 기준 시각을 확인할 수 없습니다."
                    )
                expires_at = retention_base + timedelta(days=policy["days"])
                if expires_at > evaluated_at:
                    raise ReportCleanupProtectedError(
                        "보고서 보존 기간이 아직 지나지 않았습니다."
                    )
                retention_audit = {
                    "automated": True,
                    "cleanup_reason": "RETENTION_POLICY_EXPIRED",
                    "retention_policy": policy,
                    "retention_basis": (
                        "completed_at"
                        if report.get("completed_at") is not None
                        else "created_at"
                    ),
                    "retention_base_at": retention_base.isoformat(),
                    "retention_expired_at": expires_at.isoformat(),
                }

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

            (
                cleanup_operation_id,
                cleanup_queued_count,
                shared_artifact_count,
            ) = self._queue_artifact_cleanup(
                cursor,
                tenant_id=str(report["tenant_id"]),
                storage_uris=storage_uris,
                owner_column="report_run_id",
                owner_id=report_id,
            )

            changed_fields = {
                "report_type": report["report_type"],
                "status": report["status"],
                "artifact_reference_count": len(set(storage_uris)),
                "cleanup_operation_id": cleanup_operation_id,
                "cleanup_file_count": cleanup_queued_count,
                "shared_artifact_count": shared_artifact_count,
                **retention_audit,
            }
            if report.get("cleanup_reason") and not automated_retention:
                changed_fields["cleanup_reason"] = report["cleanup_reason"]
            cursor.execute(
                """
                INSERT INTO audit.data_change_logs (
                    tenant_id, actor_id, table_name, record_id,
                    operation, changed_fields
                ) VALUES (%s, %s, 'control.report_runs', %s, 'DELETE', %s::jsonb)
                """,
                (
                    report["tenant_id"], actor_id, report_id,
                    json.dumps(changed_fields),
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

        removed, pending = self._finish_artifact_cleanup(
            cleanup_operation_id,
            cleanup_queued_count,
        )
        result["removed_artifact_files"] = removed
        result["failed_artifact_files"] = pending
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
    ) -> tuple[str, int]:
        archive_reference = archive_reference.strip()
        if len(archive_reference) > 500:
            raise ValueError("외부 보관 참조는 500자 이하여야 합니다.")
        storage_uris: list[str] = []
        cleanup_operation_id: Optional[str] = None
        cleanup_queued_count = 0
        shared_artifact_count = 0
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
            if report_count and not archive_reference:
                raise ValueError("보고서가 있는 고객은 외부 보관 참조가 필요합니다.")

            cursor.execute(
                """
                SELECT artifact.storage_uri
                FROM control.report_artifacts artifact
                JOIN control.report_runs report
                  ON report.id = artifact.report_run_id
                WHERE report.tenant_id = %s
                """,
                (tenant_id,),
            )
            storage_uris.extend(
                str(row["storage_uri"])
                for row in cursor.fetchall()
                if row.get("storage_uri")
            )
            schema = (
                "public_data"
                if tenant["environment"] == "public"
                else "gov_data"
            )
            cursor.execute(
                f"SELECT storage_uri FROM {schema}.raw_payload_refs "
                "WHERE tenant_id = %s",
                (tenant_id,),
            )
            storage_uris.extend(
                str(row["storage_uri"])
                for row in cursor.fetchall()
                if row.get("storage_uri")
            )
            cursor.execute(
                f"SELECT artifact_uri FROM {schema}.metric_series "
                "WHERE tenant_id = %s AND artifact_uri IS NOT NULL",
                (tenant_id,),
            )
            storage_uris.extend(
                str(row["artifact_uri"])
                for row in cursor.fetchall()
                if row.get("artifact_uri")
            )

            (
                cleanup_operation_id,
                cleanup_queued_count,
                shared_artifact_count,
            ) = self._queue_artifact_cleanup(
                cursor,
                tenant_id=tenant_id,
                storage_uris=storage_uris,
                owner_column="tenant_id",
                owner_id=tenant_id,
            )

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
                    archive_reference, False, actor_id,
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
                        "artifact_reference_count": len(set(storage_uris)),
                        "cleanup_operation_id": cleanup_operation_id,
                        "cleanup_file_count": cleanup_queued_count,
                        "shared_artifact_count": shared_artifact_count,
                        "forced": False,
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
            result = tenant["customer_name"], report_count

        _, pending = self._finish_artifact_cleanup(
            cleanup_operation_id,
            cleanup_queued_count,
        )
        if pending:
            LOGGER.warning(
                "Tenant deletion left %d artifact cleanup item(s) queued.",
                pending,
            )
        return result

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

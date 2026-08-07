from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row

from database.config import DatabaseSettings


class ReportJobRepository:
    def __init__(self, settings: DatabaseSettings):
        self.settings = settings

    def _connect(self):
        import psycopg

        return psycopg.connect(
            **self.settings.connection_kwargs(), row_factory=dict_row
        )

    def enqueue(
        self,
        account_id: str,
        report_type: str,
        target_value: str,
        requested_by: Optional[str],
        trigger_type: str = "MANUAL",
        schedule_id: Optional[str] = None,
        start_datetime: Optional[str] = None,
        end_datetime: Optional[str] = None,
    ) -> str:
        report_type, target_value, period_key, period_start, period_end = (
            self._validate_target(
                report_type, target_value, start_datetime, end_datetime
            )
        )
        with self._connect() as connection, connection.cursor() as cursor:
            return self._enqueue_cursor(
                cursor, account_id, report_type, target_value, period_key,
                requested_by, trigger_type, schedule_id,
                period_start, period_end,
            )

    def _enqueue_cursor(
        self, cursor: Any, account_id: str, report_type: str,
        target_value: str, period_key: str, requested_by: Optional[str],
        trigger_type: str, schedule_id: Optional[str],
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> str:
        cursor.execute(
            """
            SELECT account.tenant_id, account.environment
            FROM control.cloud_accounts account
            JOIN control.encrypted_credentials credential
                ON credential.cloud_account_id = account.id
            WHERE account.id = %s AND account.status = 'ACTIVE'
              AND credential.status = 'VALID'
            """,
            (account_id,),
        )
        account = cursor.fetchone()
        if not account:
            raise ValueError("유효한 API 키가 등록된 활성 NCP 계정을 찾지 못했습니다.")
        cursor.execute(
            """
            INSERT INTO control.report_jobs (
                tenant_id, cloud_account_id, environment, report_type,
                target_value, period_key, trigger_type, requested_by,
                schedule_id, period_start, period_end
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (cloud_account_id, report_type, period_key)
                WHERE status IN ('QUEUED', 'RUNNING')
            DO NOTHING
            RETURNING id
            """,
            (
                account["tenant_id"], account_id, account["environment"],
                report_type, target_value, period_key, trigger_type,
                requested_by, schedule_id, period_start, period_end,
            ),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("같은 기간의 보고서가 이미 대기 또는 실행 중입니다.")
        return str(row["id"])

    def upsert_schedule(
        self,
        account_id: str,
        report_type: str,
        run_hour: int,
        run_minute: int,
        monthly_day: Optional[int],
        actor_id: str,
        timezone_name: str = "Asia/Seoul",
    ) -> str:
        report_type = report_type.strip().upper()
        if report_type not in {"DAILY", "MONTHLY"}:
            raise ValueError("지원하지 않는 보고서 유형입니다.")
        if not 0 <= run_hour <= 23 or not 0 <= run_minute <= 59:
            raise ValueError("실행 시간이 올바르지 않습니다.")
        if report_type == "MONTHLY":
            monthly_day = 1 if monthly_day is None else monthly_day
            if not 1 <= monthly_day <= 28:
                raise ValueError("월간 실행일은 1일부터 28일까지 가능합니다.")
        else:
            monthly_day = None
        next_run = self.next_run_at(
            report_type, run_hour, run_minute, monthly_day, timezone_name
        )
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT tenant_id FROM control.cloud_accounts WHERE id = %s",
                (account_id,),
            )
            account = cursor.fetchone()
            if not account:
                raise ValueError("NCP 계정을 찾지 못했습니다.")
            cursor.execute(
                """
                INSERT INTO control.account_report_schedules (
                    tenant_id, cloud_account_id, report_type, timezone,
                    run_hour, run_minute, monthly_day, next_run_at, created_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (cloud_account_id, report_type) DO UPDATE SET
                    timezone = EXCLUDED.timezone, run_hour = EXCLUDED.run_hour,
                    run_minute = EXCLUDED.run_minute,
                    monthly_day = EXCLUDED.monthly_day,
                    next_run_at = EXCLUDED.next_run_at,
                    enabled = true
                RETURNING id
                """,
                (
                    account["tenant_id"], account_id, report_type,
                    timezone_name, run_hour, run_minute, monthly_day,
                    next_run, actor_id,
                ),
            )
            return str(cursor.fetchone()["id"])

    def enqueue_due_schedules(self, limit: int = 100) -> int:
        count = 0
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM control.account_report_schedules
                WHERE enabled AND next_run_at <= clock_timestamp()
                ORDER BY next_run_at
                FOR UPDATE SKIP LOCKED LIMIT %s
                """,
                (limit,),
            )
            for schedule in cursor.fetchall():
                target = self.scheduled_target(schedule)
                _, normalized_target, period_key, _, _ = self._validate_target(
                    schedule["report_type"], target
                )
                try:
                    self._enqueue_cursor(
                        cursor, str(schedule["cloud_account_id"]),
                        schedule["report_type"], normalized_target, period_key,
                        None, "SCHEDULED", str(schedule["id"]),
                    )
                    count += 1
                except ValueError:
                    # The same period can already be running from a manual request.
                    # Advance the schedule to avoid a tight enqueue loop.
                    pass
                next_run = self.next_run_at(
                    schedule["report_type"], schedule["run_hour"],
                    schedule["run_minute"], schedule["monthly_day"],
                    schedule["timezone"],
                    now=datetime.now(timezone.utc) + timedelta(seconds=1),
                )
                cursor.execute(
                    """
                    UPDATE control.account_report_schedules
                    SET last_enqueued_at = clock_timestamp(), next_run_at = %s
                    WHERE id = %s
                    """,
                    (next_run, schedule["id"]),
                )
        return count

    def claim(self, environment: str, worker_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM control.report_jobs
                WHERE environment = %s AND status = 'QUEUED'
                  AND available_at <= clock_timestamp()
                  AND attempt_count < max_attempts
                ORDER BY available_at, created_at
                FOR UPDATE SKIP LOCKED LIMIT 1
                """,
                (environment,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            cursor.execute(
                """
                UPDATE control.report_jobs
                SET status = 'RUNNING', attempt_count = attempt_count + 1,
                    locked_at = clock_timestamp(), locked_by = %s,
                    started_at = clock_timestamp()
                WHERE id = %s RETURNING *
                """,
                (worker_id[:200], row["id"]),
            )
            return cursor.fetchone()

    def requeue_stale(self, stale_minutes: int = 360) -> int:
        if stale_minutes < 30:
            raise ValueError("Stale-job timeout must be at least 30 minutes.")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE control.report_jobs
                SET status = CASE WHEN attempt_count < max_attempts
                                  THEN 'QUEUED' ELSE 'FAILED' END,
                    available_at = clock_timestamp(), locked_at = NULL,
                    locked_by = NULL,
                    completed_at = CASE WHEN attempt_count >= max_attempts
                                        THEN clock_timestamp() ELSE NULL END,
                    last_error = 'Worker lease expired before completion.'
                WHERE status = 'RUNNING'
                  AND locked_at < clock_timestamp() - make_interval(mins => %s)
                """,
                (stale_minutes,),
            )
            return cursor.rowcount

    def complete(self, job_id: str, report_run_id: Optional[str]) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE control.report_jobs SET status = 'SUCCESS',
                    report_run_id = %s, completed_at = clock_timestamp(),
                    locked_at = NULL, locked_by = NULL, last_error = NULL
                WHERE id = %s
                """,
                (report_run_id, job_id),
            )

    def fail(self, job_id: str, message: str) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE control.report_jobs SET
                    status = CASE WHEN attempt_count < max_attempts
                                  THEN 'QUEUED' ELSE 'FAILED' END,
                    available_at = clock_timestamp()
                        + make_interval(secs => LEAST(900, 30 * power(2, attempt_count)::int)),
                    completed_at = CASE WHEN attempt_count >= max_attempts
                                        THEN clock_timestamp() ELSE NULL END,
                    locked_at = NULL, locked_by = NULL, last_error = %s
                WHERE id = %s
                """,
                (message[:2000], job_id),
            )

    def set_schedule_enabled(self, schedule_id: str, enabled: bool) -> bool:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT report_type, run_hour, run_minute, monthly_day, timezone
                FROM control.account_report_schedules
                WHERE id = %s
                FOR UPDATE
                """,
                (schedule_id,),
            )
            schedule = cursor.fetchone()
            if not schedule:
                return False
            next_run = None
            if enabled:
                next_run = self.next_run_at(
                    schedule["report_type"], schedule["run_hour"],
                    schedule["run_minute"], schedule["monthly_day"],
                    schedule["timezone"],
                )
            cursor.execute(
                """
                UPDATE control.account_report_schedules
                SET enabled = %s,
                    next_run_at = COALESCE(%s, next_run_at)
                WHERE id = %s
                RETURNING id
                """,
                (enabled, next_run, schedule_id),
            )
            return cursor.fetchone() is not None

    def bulk_upsert_schedules(
        self,
        account_ids: list[str],
        report_type: str,
        run_hour: int,
        run_minute: int,
        monthly_day: Optional[int],
        actor_id: str,
        timezone_name: str = "Asia/Seoul",
    ) -> int:
        report_type, monthly_day = self._validate_schedule_values(
            report_type, run_hour, run_minute, monthly_day
        )
        normalized_ids = self._normalize_account_ids(account_ids)
        next_run = self.next_run_at(
            report_type, run_hour, run_minute, monthly_day, timezone_name
        )
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT account.id, account.tenant_id
                FROM control.cloud_accounts account
                JOIN control.tenants tenant ON tenant.id = account.tenant_id
                JOIN control.encrypted_credentials credential
                    ON credential.cloud_account_id = account.id
                   AND credential.tenant_id = account.tenant_id
                WHERE account.id = ANY(%s::uuid[])
                  AND account.status = 'ACTIVE'
                  AND tenant.status = 'ACTIVE'
                FOR UPDATE OF account
                """,
                (normalized_ids,),
            )
            accounts = cursor.fetchall()
            if len(accounts) != len(normalized_ids):
                raise ValueError(
                    "선택한 고객 계정 중 일정 등록이 불가능한 계정이 있습니다."
                )
            for account in accounts:
                cursor.execute(
                    """
                    INSERT INTO control.account_report_schedules (
                        tenant_id, cloud_account_id, report_type, timezone,
                        run_hour, run_minute, monthly_day, next_run_at,
                        created_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (cloud_account_id, report_type) DO UPDATE SET
                        timezone = EXCLUDED.timezone,
                        run_hour = EXCLUDED.run_hour,
                        run_minute = EXCLUDED.run_minute,
                        monthly_day = EXCLUDED.monthly_day,
                        next_run_at = EXCLUDED.next_run_at,
                        enabled = true,
                        updated_at = clock_timestamp()
                    """,
                    (
                        account["tenant_id"], account["id"], report_type,
                        timezone_name, run_hour, run_minute, monthly_day,
                        next_run, actor_id,
                    ),
                )
            return len(accounts)

    def bulk_delete_schedules(
        self, account_ids: list[str], report_type: str
    ) -> int:
        normalized_type = str(report_type).strip().upper()
        report_type, _ = self._validate_schedule_values(
            normalized_type, 0, 0, 1 if normalized_type == "MONTHLY" else None
        )
        normalized_ids = self._normalize_account_ids(account_ids)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM control.account_report_schedules
                WHERE cloud_account_id = ANY(%s::uuid[])
                  AND report_type = %s
                """,
                (normalized_ids, report_type),
            )
            return cursor.rowcount

    @staticmethod
    def _validate_schedule_values(
        report_type: str,
        run_hour: int,
        run_minute: int,
        monthly_day: Optional[int],
    ) -> tuple[str, Optional[int]]:
        report_type = str(report_type).strip().upper()
        if report_type not in {"DAILY", "MONTHLY"}:
            raise ValueError("지원하지 않는 보고서 유형입니다.")
        if not 0 <= run_hour <= 23 or not 0 <= run_minute <= 59:
            raise ValueError("실행 시각이 올바르지 않습니다.")
        if report_type == "MONTHLY":
            monthly_day = 1 if monthly_day is None else monthly_day
            if not 1 <= monthly_day <= 28:
                raise ValueError("월간 실행일은 1일부터 28일까지 가능합니다.")
        else:
            monthly_day = None
        return report_type, monthly_day

    @staticmethod
    def _normalize_account_ids(account_ids: list[str]) -> list[str]:
        normalized: list[str] = []
        for account_id in account_ids:
            try:
                value = str(UUID(str(account_id)))
            except (TypeError, ValueError) as exc:
                raise ValueError("선택한 고객 계정이 올바르지 않습니다.") from exc
            if value not in normalized:
                normalized.append(value)
        if not normalized:
            raise ValueError("고객 또는 고객 계정을 하나 이상 선택해 주세요.")
        if len(normalized) > 1_000:
            raise ValueError("한 번에 최대 1,000개 계정까지 선택할 수 있습니다.")
        return normalized

    @staticmethod
    def _validate_target(
        report_type: str,
        target_value: str,
        start_datetime: Optional[str] = None,
        end_datetime: Optional[str] = None,
    ) -> tuple[str, str, str, Optional[datetime], Optional[datetime]]:
        report_type = report_type.strip().upper()
        target_value = target_value.strip()
        if report_type == "DAILY":
            try:
                normalized = datetime.strptime(target_value, "%Y-%m-%d").date().isoformat()
            except ValueError as exc:
                raise ValueError("일일 보고서 날짜 형식은 YYYY-MM-DD입니다.") from exc
            return report_type, normalized, normalized, None, None
        if report_type == "MONTHLY" and re.fullmatch(r"\d{4}-\d{2}", target_value):
            try:
                datetime.strptime(target_value, "%Y-%m")
            except ValueError as exc:
                raise ValueError("월간 보고서 형식은 YYYY-MM입니다.") from exc
            return report_type, target_value, target_value, None, None
        if report_type == "CUSTOM":
            start = ReportJobRepository._parse_kst_datetime(start_datetime)
            end = ReportJobRepository._parse_kst_datetime(end_datetime)
            if start >= end:
                raise ValueError("시작 시각은 종료 시각보다 빨라야 합니다.")
            effective_end = end - timedelta(microseconds=1)
            if start.strftime("%Y-%m") != effective_end.strftime("%Y-%m"):
                raise ValueError("시간 범위는 동일한 월 안에서 지정해야 합니다.")
            start_text = start.strftime("%Y-%m-%dT%H:%M:%S")
            end_text = end.strftime("%Y-%m-%dT%H:%M:%S")
            value = f"{start_text}/{end_text}"
            return report_type, value, value, start, end
        raise ValueError("보고서 유형 또는 대상 기간이 올바르지 않습니다.")

    @staticmethod
    def _parse_kst_datetime(value: Optional[str]) -> datetime:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("시작 시각과 종료 시각을 모두 입력하세요.")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("시간 형식이 올바르지 않습니다.") from exc
        zone = ZoneInfo("Asia/Seoul")
        return (
            parsed.replace(tzinfo=zone)
            if parsed.tzinfo is None
            else parsed.astimezone(zone)
        )

    @staticmethod
    def next_run_at(
        report_type: str, run_hour: int, run_minute: int,
        monthly_day: Optional[int], timezone_name: str,
        now: Optional[datetime] = None,
    ) -> datetime:
        zone = ZoneInfo(timezone_name)
        local_now = (now or datetime.now(timezone.utc)).astimezone(zone)
        day = local_now.day if report_type == "DAILY" else int(monthly_day or 1)
        candidate = local_now.replace(
            day=day, hour=run_hour, minute=run_minute,
            second=0, microsecond=0,
        )
        if candidate <= local_now:
            if report_type == "DAILY":
                candidate += timedelta(days=1)
            else:
                year = candidate.year + (1 if candidate.month == 12 else 0)
                month = 1 if candidate.month == 12 else candidate.month + 1
                candidate = candidate.replace(year=year, month=month, day=day)
        return candidate.astimezone(timezone.utc)

    @staticmethod
    def scheduled_target(schedule: dict[str, Any]) -> str:
        zone = ZoneInfo(schedule["timezone"])
        local_date = schedule["next_run_at"].astimezone(zone).date()
        if schedule["report_type"] == "DAILY":
            return (local_date - timedelta(days=1)).isoformat()
        first = local_date.replace(day=1)
        previous_end = first - timedelta(days=1)
        return previous_end.strftime("%Y-%m")

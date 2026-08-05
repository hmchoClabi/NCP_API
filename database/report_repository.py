from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional
from zoneinfo import ZoneInfo

from app.report_models import ReportResult
from database.config import DatabaseSettings
from utils.event_sort import event_timestamp_millis


class DatabasePersistenceError(RuntimeError):
    """Raised when a generated report cannot be persisted safely."""


class PostgresReportRepository:
    KST = ZoneInfo("Asia/Seoul")
    SCHEMAS = {"public": "public_data", "gov": "gov_data"}

    def __init__(
        self,
        settings: DatabaseSettings,
        idempotency_suffix: Optional[str] = None,
        trigger_type: str = "MANUAL",
    ):
        self.settings = settings
        self.idempotency_suffix = idempotency_suffix
        self.trigger_type = trigger_type if trigger_type in {
            "MANUAL", "SCHEDULED", "RETRY", "API"
        } else "MANUAL"
        self.last_report_run_id: Optional[str] = None

    def save_report(
        self,
        report: ReportResult,
        artifacts: Optional[Mapping[str, Path | str]] = None,
    ) -> str:
        try:
            import psycopg
        except ImportError as exc:
            raise DatabasePersistenceError(
                "PostgreSQL support is not installed. Run: pip install -r requirements.txt"
            ) from exc

        try:
            with psycopg.connect(**self.settings.connection_kwargs()) as connection:
                with connection.cursor() as cursor:
                    if self.settings.tenant_id:
                        cursor.execute(
                            "SELECT set_config('app.tenant_id', %s, true)",
                            (str(self.settings.tenant_id),),
                        )
                    tenant_id, environment = self._resolve_tenant(cursor, report)
                    cloud_account_id = self._resolve_cloud_account(
                        cursor, report, tenant_id, environment
                    )
                    report_run_id = self._upsert_report_run(
                        cursor, report, tenant_id, environment, cloud_account_id
                    )
                    self._replace_report_details(
                        cursor, report, report_run_id, tenant_id, environment
                    )
                    self._replace_artifacts(
                        cursor, report_run_id, tenant_id, artifacts or {}
                    )
                    self._replace_errors(cursor, report, report_run_id, tenant_id)
                    self._upsert_daily_fact(
                        cursor, report, report_run_id, tenant_id, environment
                    )
                self.last_report_run_id = str(report_run_id)
                return self.last_report_run_id
        except DatabasePersistenceError:
            raise
        except Exception as exc:
            raise DatabasePersistenceError(
                f"Report database persistence failed ({type(exc).__name__})."
            ) from exc

    def _resolve_tenant(self, cursor: Any, report: ReportResult) -> tuple[Any, str]:
        customer = report.customer if isinstance(report.customer, dict) else {}
        environment = str(customer.get("api_type") or "public").strip().casefold()
        if environment not in self.SCHEMAS:
            raise DatabasePersistenceError("Customer environment must be public or gov.")

        if self.settings.tenant_id:
            cursor.execute(
                "SELECT id, environment FROM control.tenants WHERE id = %s",
                (self.settings.tenant_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise DatabasePersistenceError("Configured database tenant was not found.")
            if row[1] != environment:
                raise DatabasePersistenceError(
                    "Configured database tenant environment does not match the customer."
                )
            return row[0], row[1]

        if self.settings.role != "msp":
            raise DatabasePersistenceError(
                "Only the MSP role may register a tenant automatically."
            )

        customer_id = str(customer.get("id") or "default")
        customer_code = self._customer_code(customer_id)
        customer_name = str(customer.get("name") or customer_id).strip()[:200]
        region = str(customer.get("region") or "KR").strip().upper()[:20]
        cursor.execute(
            """
            INSERT INTO control.tenants (
                customer_code, customer_name, environment, region
            ) VALUES (%s, %s, %s, %s)
            ON CONFLICT (customer_code) DO UPDATE SET
                customer_name = EXCLUDED.customer_name,
                region = EXCLUDED.region
            WHERE control.tenants.environment = EXCLUDED.environment
            RETURNING id, environment
            """,
            (customer_code, customer_name, environment, region),
        )
        row = cursor.fetchone()
        if not row:
            raise DatabasePersistenceError(
                "Customer code already belongs to a different NCP environment."
            )
        return row[0], row[1]

    def _upsert_report_run(
        self, cursor: Any, report: ReportResult, tenant_id: Any, environment: str,
        cloud_account_id: Any,
    ) -> Any:
        start, end, end_exclusive = self._period_bounds(report.period)
        report_type = self._report_type(report.period)
        error_count = len(report.collection_errors)
        status = "PARTIAL_SUCCESS" if error_count else "SUCCESS"
        idempotency_parts = [
            str(tenant_id), str(cloud_account_id), report.report_id
        ]
        if self.idempotency_suffix:
            idempotency_parts.append(self.idempotency_suffix)
        idempotency_key = ":".join(idempotency_parts)[:255]
        cursor.execute(
            """
            INSERT INTO control.report_runs (
                tenant_id, environment, report_type, period_start, period_end,
                end_exclusive, status, trigger_type, idempotency_key,
                collector_version, normalizer_version, renderer_version,
                cloud_account_id,
                attempt_count, error_count, started_at, completed_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                '1.0', '1.0', '1.0', %s, 1, %s, clock_timestamp(), clock_timestamp()
            )
            ON CONFLICT (idempotency_key) DO UPDATE SET
                period_start = EXCLUDED.period_start,
                period_end = EXCLUDED.period_end,
                end_exclusive = EXCLUDED.end_exclusive,
                status = EXCLUDED.status,
                error_count = EXCLUDED.error_count,
                attempt_count = control.report_runs.attempt_count + 1,
                started_at = clock_timestamp(),
                completed_at = clock_timestamp()
            RETURNING id
            """,
            (
                tenant_id, environment, report_type, start, end,
                end_exclusive, status, self.trigger_type, idempotency_key,
                cloud_account_id,
                error_count,
            ),
        )
        return cursor.fetchone()[0]

    def _resolve_cloud_account(
        self, cursor: Any, report: ReportResult, tenant_id: Any, environment: str
    ) -> Any:
        customer = report.customer if isinstance(report.customer, dict) else {}
        configured_id = customer.get("cloud_account_id")
        if configured_id:
            cursor.execute(
                """
                SELECT id FROM control.cloud_accounts
                WHERE id = %s AND tenant_id = %s AND environment = %s
                """,
                (configured_id, tenant_id, environment),
            )
            row = cursor.fetchone()
            if not row:
                raise DatabasePersistenceError("Configured cloud account was not found.")
            return row[0]
        account_code = str(customer.get("cloud_account_code") or "default")[:80]
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
                tenant_id, account_code,
                str(customer.get("name") or account_code)[:200], environment,
                str(customer.get("region") or "KR")[:20],
            ),
        )
        return cursor.fetchone()[0]

    def _replace_report_details(
        self,
        cursor: Any,
        report: ReportResult,
        report_run_id: Any,
        tenant_id: Any,
        environment: str,
    ) -> None:
        schema = self.SCHEMAS[environment]
        for table in (
            "report_snapshots", "insight_events", "activity_events",
            "metric_series", "metric_summaries", "cost_details", "raw_payload_refs",
        ):
            cursor.execute(
                f"DELETE FROM {schema}.{table} WHERE report_run_id = %s",
                (report_run_id,),
            )

        snapshot = report.to_dict()
        snapshot["server_metrics"] = report.server_metrics
        payload = self._json(snapshot)
        cursor.execute(
            f"""
            INSERT INTO {schema}.report_snapshots (
                report_run_id, tenant_id, schema_version, normalized_data,
                content_hash_sha256, collector_version, normalizer_version,
                renderer_version
            ) VALUES (%s, %s, '1.0', %s::jsonb, %s, '1.0', '1.0', '1.0')
            """,
            (
                report_run_id,
                tenant_id,
                payload,
                hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            ),
        )
        self._insert_insight_events(
            cursor, schema, report, report_run_id, tenant_id
        )
        self._insert_activity_events(
            cursor, schema, report, report_run_id, tenant_id
        )
        self._insert_metric_summaries(
            cursor, schema, report, report_run_id, tenant_id
        )
        self._insert_cost_details(
            cursor, schema, report, report_run_id, tenant_id
        )

    def _insert_insight_events(
        self, cursor: Any, schema: str, report: ReportResult,
        report_run_id: Any, tenant_id: Any,
    ) -> None:
        fallback_time = self._period_bounds(report.period)[0]
        for event in report.insight_events:
            if not isinstance(event, dict):
                continue
            cursor.execute(
                f"""
                INSERT INTO {schema}.insight_events (
                    report_run_id, tenant_id, source_event_id, occurred_at,
                    ended_at, severity, service_name, resource_id, resource_name,
                    resource_type, rule_id, rule_name, metric, operator, criteria,
                    detect_value, unit, aggregation, interval_name,
                    notification_status, in_maintenance, resource_deleted, details
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                )
                """,
                (
                    report_run_id, tenant_id, self._text(event.get("event_id"), 255),
                    self._event_datetime(event.get("start_time")) or fallback_time,
                    self._event_datetime(event.get("end_time")),
                    self._text(event.get("level"), 20),
                    self._text(event.get("prod_name"), 200),
                    self._text(event.get("resource_id"), 255),
                    self._text(event.get("resource_name"), 500),
                    self._text(event.get("resource_type"), 200),
                    self._text(event.get("rule_id"), 255),
                    self._text(event.get("rule_name"), 500),
                    self._text(event.get("metric"), 255),
                    self._text(event.get("operator"), 20),
                    self._text(event.get("criteria"), 255),
                    self._text(event.get("detect_value"), 255),
                    self._text(event.get("unit"), 50),
                    self._text(event.get("calc"), 30),
                    self._text(event.get("interval"), 30),
                    self._text(event.get("notification_status"), 30),
                    self._boolean(event.get("in_maintenance")),
                    self._boolean(event.get("resource_deleted")),
                    self._json(event),
                ),
            )

    def _insert_activity_events(
        self, cursor: Any, schema: str, report: ReportResult,
        report_run_id: Any, tenant_id: Any,
    ) -> None:
        fallback_time = self._period_bounds(report.period)[0]
        seen = set()
        for event in self._event_records(report.activity_events):
            signature = (
                event.get("event_id"), event.get("event_time"),
                event.get("action_name"), event.get("resource_id"),
            )
            if signature in seen:
                continue
            seen.add(signature)
            source_ip = self._ip_address(event.get("source_ip"))
            account_name = event.get("user_name") or event.get("member_no")
            cursor.execute(
                f"""
                INSERT INTO {schema}.activity_events (
                    report_run_id, tenant_id, source_event_id, occurred_at,
                    account_name, account_type, service_name, resource_type,
                    resource_id, resource_name, action_name, result, source_ip, details
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                )
                """,
                (
                    report_run_id, tenant_id, self._text(event.get("event_id"), 255),
                    self._event_datetime(event.get("event_time")) or fallback_time,
                    self._text(account_name, 320), self._text(event.get("user_type"), 100),
                    self._text(
                        event.get("product_display_name") or event.get("product_name"), 200
                    ),
                    self._text(event.get("resource_type"), 200),
                    self._text(event.get("resource_id"), 500),
                    self._text(event.get("resource_name"), 500),
                    self._text(event.get("action_name"), 300),
                    self._text(event.get("result"), 50), source_ip, self._json(event),
                ),
            )

    def _insert_metric_summaries(
        self, cursor: Any, schema: str, report: ReportResult,
        report_run_id: Any, tenant_id: Any,
    ) -> None:
        groups = (
            ("CPU", "cpu", "used_rto"),
            ("MEM", "mem", "mem_usert"),
            ("ROOT_DISK", "os_fs", "fs_usert"),
            ("DATA_DISK", "data_fs", "fs_usert"),
        )
        for metric in report.server_metrics:
            if not isinstance(metric, dict):
                continue
            resource_id = self._text(metric.get("server_id"), 255) or "unknown"
            for group, prefix, metric_name in groups:
                values = [metric.get(f"{prefix}_{name}") for name in ("min", "avg", "max")]
                if all(value is None for value in values):
                    continue
                cursor.execute(
                    f"""
                    INSERT INTO {schema}.metric_summaries (
                        report_run_id, tenant_id, resource_id, resource_name,
                        metric_group, metric_name, minimum, average, maximum, sample_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        report_run_id, tenant_id, resource_id,
                        self._text(metric.get("server_name"), 500), group, metric_name,
                        values[0], values[1], values[2],
                        self._metric_sample_count(metric, metric_name),
                    ),
                )

    def _insert_cost_details(
        self, cursor: Any, schema: str, report: ReportResult,
        report_run_id: Any, tenant_id: Any,
    ) -> None:
        billing = report.billing if isinstance(report.billing, dict) else {}
        billing_month = str(report.period.get("billing_month") or "")
        for row in billing.get("expected_cost_summary", []):
            if not isinstance(row, dict):
                continue
            cursor.execute(
                f"""
                INSERT INTO {schema}.cost_details (
                    report_run_id, tenant_id, billing_month, service_name,
                    item_name, item_code, usage_quantity, usage_unit, raw_unit_price,
                    expected_amount, calculation_method, calculation_status,
                    calculation_details
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    report_run_id, tenant_id, billing_month,
                    self._text(row.get("service_name") or "Unknown", 300),
                    self._text(row.get("item_name"), 500),
                    self._text(row.get("item_code"), 255), row.get("usage_quantity"),
                    self._text(row.get("unit_code"), 100), row.get("raw_price"),
                    row.get("expected_amount"),
                    self._text(row.get("calculation_method"), 255),
                    self._text(row.get("calculation_status") or "UNKNOWN", 100),
                    self._json(row),
                ),
            )

    def _replace_artifacts(
        self, cursor: Any, report_run_id: Any, tenant_id: Any,
        artifacts: Mapping[str, Path | str],
    ) -> None:
        cursor.execute(
            "DELETE FROM control.report_artifacts WHERE report_run_id = %s",
            (report_run_id,),
        )
        for artifact_type, path_value in artifacts.items():
            if artifact_type not in {"HTML", "PDF", "PUBLIC_JSON"}:
                continue
            path = Path(path_value).resolve()
            if not path.is_file():
                continue
            cursor.execute(
                """
                INSERT INTO control.report_artifacts (
                    report_run_id, tenant_id, artifact_type, storage_uri,
                    content_type, byte_size, checksum_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    report_run_id, tenant_id, artifact_type, path.as_uri(),
                    {"HTML": "text/html", "PDF": "application/pdf", "PUBLIC_JSON": "application/json"}[artifact_type],
                    path.stat().st_size, self._file_hash(path),
                ),
            )

    def _replace_errors(
        self, cursor: Any, report: ReportResult, report_run_id: Any, tenant_id: Any
    ) -> None:
        cursor.execute(
            "DELETE FROM control.collection_errors WHERE report_run_id = %s",
            (report_run_id,),
        )
        for error in report.collection_errors:
            if not isinstance(error, dict):
                continue
            cursor.execute(
                """
                INSERT INTO control.collection_errors (
                    report_run_id, tenant_id, collector, stage, target_type,
                    target_id, status_code, error_code, message, retryable
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    report_run_id, tenant_id,
                    self._text(error.get("collector") or error.get("normalizer") or "unknown", 100),
                    self._text(error.get("stage"), 100),
                    self._text(error.get("target_type"), 100),
                    self._text(error.get("target_id"), 255), error.get("status_code"),
                    self._text(error.get("error_code"), 100),
                    str(error.get("message") or "Collection error")[:10000],
                    bool(error.get("retryable", False)),
                ),
            )

    def _upsert_daily_fact(
        self, cursor: Any, report: ReportResult, report_run_id: Any,
        tenant_id: Any, environment: str,
    ) -> None:
        insight = [event for event in report.insight_events if isinstance(event, dict)]
        levels = [str(event.get("level") or "").upper() for event in insight]
        activities = list(self._event_records(report.activity_events))
        billing_summary = report.billing.get("summary", {}) if isinstance(report.billing, dict) else {}
        comparison_status = str(billing_summary.get("comparison_status") or "")
        confidence = (
            "VERIFIED_ESTIMATE" if comparison_status == "OK"
            else "PARTIAL" if billing_summary else "UNAVAILABLE"
        )
        cursor.execute(
            """
            INSERT INTO control.daily_customer_facts (
                tenant_id, fact_date, environment, latest_report_run_id,
                collection_status, server_count, critical_count, warning_count,
                info_count, activity_failure_count, collection_error_count,
                estimated_cost, confirmed_cost, cost_confidence
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, fact_date) DO UPDATE SET
                latest_report_run_id = EXCLUDED.latest_report_run_id,
                collection_status = EXCLUDED.collection_status,
                server_count = EXCLUDED.server_count,
                critical_count = EXCLUDED.critical_count,
                warning_count = EXCLUDED.warning_count,
                info_count = EXCLUDED.info_count,
                activity_failure_count = EXCLUDED.activity_failure_count,
                collection_error_count = EXCLUDED.collection_error_count,
                estimated_cost = EXCLUDED.estimated_cost,
                confirmed_cost = EXCLUDED.confirmed_cost,
                cost_confidence = EXCLUDED.cost_confidence,
                updated_at = clock_timestamp()
            """,
            (
                tenant_id, self._period_bounds(report.period)[0].date(), environment,
                report_run_id, "PARTIAL_SUCCESS" if report.collection_errors else "SUCCESS",
                len(report.servers), levels.count("CRITICAL"), levels.count("WARNING"),
                levels.count("INFO"),
                sum(
                    bool(event.get("result"))
                    and str(event.get("result")).upper() not in {"SUCCESS", "SUCCEED"}
                    for event in activities
                ),
                len(report.collection_errors), billing_summary.get("expected_total_amount"),
                billing_summary.get("confirmed_total_amount"), confidence,
            ),
        )

    def _period_bounds(self, period: Mapping[str, Any]) -> tuple[datetime, datetime, bool]:
        start = self._parse_datetime(period.get("start_dt"))
        end = self._parse_datetime(period.get("end_dt"))
        end_exclusive = bool(period.get("end_exclusive", False))
        if not end_exclusive:
            end += timedelta(seconds=1)
            end_exclusive = True
        if start >= end:
            raise DatabasePersistenceError("Report period is invalid.")
        return start, end, end_exclusive

    def _parse_datetime(self, value: Any) -> datetime:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=self.KST)
        return parsed.astimezone(self.KST)

    def _event_datetime(self, value: Any) -> Optional[datetime]:
        timestamp = event_timestamp_millis(value)
        if timestamp is None or timestamp <= 0:
            return None
        return datetime.fromtimestamp(timestamp / 1000, tz=self.KST)

    def _report_type(self, period: Mapping[str, Any]) -> str:
        period_type = str(period.get("period_type") or "").casefold()
        if period_type in {"day", "today", "yesterday"}:
            return "DAILY"
        if period_type in {"month", "prev_month"}:
            return "MONTHLY"
        return "CUSTOM"

    def _event_records(self, value: Any) -> Iterable[Dict[str, Any]]:
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield item
            return
        if not isinstance(value, dict):
            return
        direct = value.get("events")
        if isinstance(direct, list):
            yield from self._event_records(direct)
            return
        for item in value.values():
            if isinstance(item, list):
                yield from self._event_records(item)

    def _metric_sample_count(self, metric: Mapping[str, Any], metric_name: str) -> int:
        raw_metrics = metric.get("raw_metrics")
        if not isinstance(raw_metrics, dict):
            return 0
        stat_entries = raw_metrics.get(metric_name, {}).get("avg", [])
        return sum(
            len(entry.get("values", []))
            for entry in stat_entries
            if isinstance(entry, dict) and isinstance(entry.get("values"), list)
        )

    @staticmethod
    def _customer_code(value: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", value.casefold()).strip("-_")
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
        if len(normalized) < 3:
            normalized = f"{normalized or 'customer'}-{digest}"
        needs_digest = normalized != value.casefold() or len(normalized) > 80
        if needs_digest:
            return f"{normalized[:71].rstrip('-_')}-{digest}"
        return normalized

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))

    @staticmethod
    def _text(value: Any, limit: int) -> Optional[str]:
        if value is None or value == "":
            return None
        return str(value)[:limit]

    @staticmethod
    def _boolean(value: Any) -> Optional[bool]:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return value
        return str(value).strip().casefold() in {"1", "true", "yes", "y"}

    @staticmethod
    def _ip_address(value: Any) -> Optional[str]:
        if not value:
            return None
        try:
            return str(ipaddress.ip_address(str(value).strip()))
        except ValueError:
            return None

    @staticmethod
    def _file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

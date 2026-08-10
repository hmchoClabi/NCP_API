from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional
from zoneinfo import ZoneInfo

from app.report_models import ReportResult
from app.report_period import (
    build_snapshot_eligibility_window,
    normalize_period_bounds,
)
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
                        cursor, report, report_run_id, tenant_id, environment,
                        cloud_account_id,
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

    def load_period_infrastructure_snapshot(
        self,
        period: Mapping[str, Any],
        customer: Mapping[str, Any],
        reference_at: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """Return the latest inventory observed inside the report period.

        Current NCP inventory APIs do not provide a complete point-in-time view.
        A historical report accepts only observations collected inside its
        requested period. A current snapshot is never substituted.
        """
        tenant_id = self.settings.tenant_id
        cloud_account_id = customer.get("cloud_account_id")
        environment = str(customer.get("api_type") or "public").casefold()
        if (
            not tenant_id
            or not cloud_account_id
            or environment not in self.SCHEMAS
        ):
            return None

        window = self._snapshot_eligibility_window(period, reference_at)
        if window is None:
            return None

        try:
            import psycopg
        except ImportError as exc:
            raise DatabasePersistenceError(
                "PostgreSQL support is not installed. Run: pip install -r requirements.txt"
            ) from exc

        schema = self.SCHEMAS[environment]
        observed_text_expression = (
            "COALESCE(snapshot.normalized_data #>> "
            "'{collection_metadata,infrastructure,completed_at}', "
            "snapshot.normalized_data #>> "
            "'{collection_metadata,infrastructure,started_at}')"
        )
        observed_expression = (
            f"CASE WHEN ({observed_text_expression}) ~* "
            "'(Z|[+-][0-9]{2}(:[0-9]{2})?)$' "
            f"THEN ({observed_text_expression})::timestamptz "
            f"ELSE ({observed_text_expression})::timestamp "
            "AT TIME ZONE 'Asia/Seoul' END"
        )

        try:
            with psycopg.connect(
                **self.settings.connection_kwargs()
            ) as connection, connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.tenant_id', %s, true)",
                    (str(tenant_id),),
                )
                cursor.execute(
                    f"""
                    SELECT snapshot.normalized_data, snapshot.report_run_id,
                           {observed_expression} AS observed_at
                    FROM {schema}.report_snapshots snapshot
                    JOIN control.report_runs report_run
                      ON report_run.id = snapshot.report_run_id
                     AND report_run.tenant_id = snapshot.tenant_id
                    WHERE snapshot.tenant_id = %s
                      AND report_run.cloud_account_id = %s
                      AND jsonb_typeof(
                          snapshot.normalized_data -> 'infrastructure'
                      ) = 'array'
                      AND snapshot.normalized_data #>>
                          '{{collection_metadata,infrastructure,source}}'
                          = 'LIVE_API_COLLECTION'
                      AND ({observed_expression}) >= %s
                      AND ({observed_expression}) < %s
                    ORDER BY ({observed_expression}) DESC,
                             report_run.completed_at DESC NULLS LAST,
                             report_run.id DESC
                    LIMIT 1
                    """,
                    (
                        str(tenant_id),
                        str(cloud_account_id),
                        window["eligible_start"],
                        window["eligible_end"],
                    ),
                )
                row = cursor.fetchone()
        except Exception as exc:
            raise DatabasePersistenceError(
                "Historical infrastructure snapshot lookup failed."
            ) from exc

        if not row or not isinstance(row[0], dict):
            return None
        observed_at = self._parse_datetime(row[2])
        result = dict(row[0])
        result["_snapshot_reference"] = {
            "report_run_id": str(row[1]),
            "observed_at": observed_at.isoformat(),
            "reference_at": window["reference_at"].isoformat(),
            "eligible_start": window["eligible_start"].isoformat(),
            "eligible_end": window["eligible_end"].isoformat(),
            "snapshot_age_seconds": max(
                0,
                int(
                    (
                        window["reference_at"] - observed_at
                    ).total_seconds()
                ),
            ),
        }
        return result

    def _snapshot_eligibility_window(
        self,
        period: Mapping[str, Any],
        reference_at: Any = None,
    ) -> Optional[Dict[str, datetime]]:
        period_start, period_end, _ = self._period_bounds(period)
        reference = (
            datetime.now(self.KST)
            if reference_at is None
            else self._parse_datetime(reference_at)
        )
        return build_snapshot_eligibility_window(
            period_start,
            period_end,
            reference,
        )

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
                '1.3', '1.3', '1.3', %s, 1, %s, clock_timestamp(), clock_timestamp()
            )
            ON CONFLICT (idempotency_key) DO UPDATE SET
                period_start = EXCLUDED.period_start,
                period_end = EXCLUDED.period_end,
                end_exclusive = EXCLUDED.end_exclusive,
                status = EXCLUDED.status,
                error_count = EXCLUDED.error_count,
                collector_version = EXCLUDED.collector_version,
                normalizer_version = EXCLUDED.normalizer_version,
                renderer_version = EXCLUDED.renderer_version,
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
        cloud_account_id: Any,
    ) -> None:
        schema = self.SCHEMAS[environment]
        for table in (
            "report_snapshots", "insight_events", "activity_events",
            "metric_series", "metric_summaries", "cost_details",
            "billing_cost_facts", "raw_payload_refs",
            "billing_account_cost_facts",
        ):
            cursor.execute(
                f"DELETE FROM {schema}.{table} WHERE report_run_id = %s",
                (report_run_id,),
            )

        snapshot = report.to_persistence_dict()
        snapshot["server_metrics"] = report.server_metrics
        payload = self._json(snapshot)
        cursor.execute(
            f"""
            INSERT INTO {schema}.report_snapshots (
                report_run_id, tenant_id, schema_version, normalized_data,
                content_hash_sha256, collector_version, normalizer_version,
                renderer_version
            ) VALUES (%s, %s, '1.3', %s::jsonb, %s, '1.3', '1.3', '1.3')
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
        self._insert_billing_cost_facts(
            cursor, schema, report, report_run_id, tenant_id,
            cloud_account_id,
        )
        self._upsert_organization_members(
            cursor, report, tenant_id, cloud_account_id
        )
        self._insert_billing_account_cost_facts(
            cursor, schema, report, report_run_id, tenant_id,
            cloud_account_id,
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

    def _insert_billing_cost_facts(
        self, cursor: Any, schema: str, report: ReportResult,
        report_run_id: Any, tenant_id: Any, cloud_account_id: Any,
    ) -> None:
        billing = report.billing if isinstance(report.billing, dict) else {}
        allowed_types = {
            "CONFIRMED", "PERIOD_ESTIMATE",
            "MONTH_TO_DATE_ESTIMATE", "MONTH_END_PROJECTION",
        }
        for fact in billing.get("cost_facts", []):
            if not isinstance(fact, dict):
                continue
            cost_type = str(fact.get("cost_type") or "")
            status = str(fact.get("status") or "")
            if cost_type not in allowed_types or status not in {
                "AVAILABLE", "UNAVAILABLE"
            }:
                continue
            cursor.execute(
                f"""
                INSERT INTO {schema}.billing_cost_facts (
                    report_run_id, tenant_id, cloud_account_id, cost_type,
                    status, period_start, period_end, coverage_start,
                    coverage_end, calculated_at, subtotal_amount,
                    discount_amount, vat_amount, total_amount, currency,
                    amount_basis, includes_discount, includes_vat, confidence,
                    excluded_item_count, source_api, calculation_version,
                    details
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s::jsonb
                )
                """,
                (
                    report_run_id, tenant_id, cloud_account_id, cost_type,
                    status, fact.get("period_start"), fact.get("period_end"),
                    fact.get("coverage_start"), fact.get("coverage_end"),
                    fact.get("calculated_at") or report.generated_at,
                    fact.get("subtotal_amount"), fact.get("discount_amount"),
                    fact.get("vat_amount"), fact.get("total_amount"),
                    self._text(fact.get("currency") or "KRW", 3),
                    self._text(fact.get("amount_basis") or "UNKNOWN", 60),
                    bool(fact.get("includes_discount")),
                    bool(fact.get("includes_vat")),
                    self._text(fact.get("confidence") or "UNAVAILABLE", 30),
                    max(int(fact.get("excluded_item_count") or 0), 0),
                    self._text(fact.get("source_api"), 500),
                    self._text(fact.get("calculation_version") or "1.1", 40),
                    self._json(
                        fact.get("details")
                        if isinstance(fact.get("details"), dict) else {}
                    ),
                ),
            )

    def _upsert_organization_members(
        self, cursor: Any, report: ReportResult, tenant_id: Any,
        cloud_account_id: Any,
    ) -> None:
        billing = report.billing if isinstance(report.billing, dict) else {}
        organization = billing.get("organization")
        if not isinstance(organization, dict) or organization.get("scope") != "ORGANIZATION":
            return
        for member in organization.get("members", []):
            if not isinstance(member, dict) or not member.get("member_no"):
                continue
            cursor.execute(
                """
                INSERT INTO control.organization_members (
                    tenant_id, source_cloud_account_id, member_no,
                    display_name, organization_no, group_no, group_path,
                    is_master, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_cloud_account_id, member_no) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    organization_no = EXCLUDED.organization_no,
                    group_no = EXCLUDED.group_no,
                    group_path = EXCLUDED.group_path,
                    is_master = EXCLUDED.is_master,
                    status = EXCLUDED.status,
                    last_seen_at = clock_timestamp()
                """,
                (
                    tenant_id, cloud_account_id,
                    self._text(member.get("member_no"), 30),
                    self._text(member.get("display_name") or member.get("member_no"), 200),
                    self._text(organization.get("organization_no"), 30),
                    self._text(member.get("group_no"), 30),
                    self._text(member.get("group_path"), 500),
                    bool(member.get("is_master")),
                    self._text(member.get("status") or "JOIN", 30),
                ),
            )

    def _insert_billing_account_cost_facts(
        self, cursor: Any, schema: str, report: ReportResult,
        report_run_id: Any, tenant_id: Any, cloud_account_id: Any,
    ) -> None:
        billing = report.billing if isinstance(report.billing, dict) else {}
        for account in billing.get("account_costs", []):
            if not isinstance(account, dict) or not account.get("member_no"):
                continue
            for fact in account.get("cost_facts", []):
                if not isinstance(fact, dict) or not fact.get("period_start"):
                    continue
                service_costs = (
                    account.get("service_summary", [])
                    if fact.get("cost_type") == "CONFIRMED"
                    else account.get("current_service_summary", [])
                    if fact.get("cost_type") == "CURRENT_PROVISIONAL"
                    else account.get("expected_by_service", [])
                )
                cursor.execute(
                    f"""
                    INSERT INTO {schema}.billing_account_cost_facts (
                        report_run_id, tenant_id, cloud_account_id,
                        member_no, display_name, is_master, cost_type,
                        status, period_start, period_end, subtotal_amount,
                        vat_amount, total_amount, confidence, service_costs,
                        details
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb
                    )
                    """,
                    (
                        report_run_id, tenant_id, cloud_account_id,
                        self._text(account.get("member_no"), 30),
                        self._text(account.get("display_name") or account.get("member_no"), 200),
                        bool(account.get("is_master")),
                        self._text(fact.get("cost_type"), 40),
                        self._text(fact.get("status") or "UNAVAILABLE", 30),
                        fact.get("period_start"), fact.get("period_end"),
                        fact.get("subtotal_amount"), fact.get("vat_amount"),
                        fact.get("total_amount"),
                        self._text(fact.get("confidence") or "UNAVAILABLE", 30),
                        self._json(service_costs), self._json(fact.get("details") or {}),
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
        billing = report.billing if isinstance(report.billing, dict) else {}
        period_estimate = billing.get("period_estimate", {})
        month_to_date_estimate = billing.get("month_to_date_estimate", {})
        invoice_summary = billing.get("invoice_summary", {})
        active_estimate = (
            month_to_date_estimate
            if (
                period_estimate.get("status") == "NOT_APPLICABLE"
                and month_to_date_estimate.get("status") == "AVAILABLE"
            )
            else period_estimate
        )
        confidence = str(
            active_estimate.get("confidence")
            or invoice_summary.get("confidence")
            or "UNAVAILABLE"
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
                len(report.collection_errors), active_estimate.get("total_amount"),
                invoice_summary.get("total_amount"), confidence,
            ),
        )

    def _period_bounds(self, period: Mapping[str, Any]) -> tuple[datetime, datetime, bool]:
        start = self._parse_datetime(period.get("start_dt"))
        end = self._parse_datetime(period.get("end_dt"))
        end_exclusive = bool(period.get("end_exclusive", False))
        try:
            start, end = normalize_period_bounds(
                start,
                end,
                end_exclusive=end_exclusive,
            )
        except ValueError as exc:
            raise DatabasePersistenceError(str(exc)) from exc
        return start, end, True

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

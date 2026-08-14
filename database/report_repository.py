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
    NETWORK_CONFIGURATION_CATEGORIES = frozenset({
        "ROUTE_TABLE",
        "ACCESS_CONTROL_GROUP",
        "NETWORK_ACL",
    })
    NETWORK_SNAPSHOT_SCHEMA_VERSION = "1.0"

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
                    cursor.execute(
                        "SELECT set_config('app.tenant_id', %s, true)",
                        (str(tenant_id),),
                    )
                    cursor.execute(
                        "SELECT set_config('app.environment_scope', %s, true)",
                        (environment,),
                    )
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
                        cursor,
                        report,
                        report_run_id,
                        tenant_id,
                        environment,
                        cloud_account_id,
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
            "'{infrastructure_snapshot,metadata,completed_at}', "
            "snapshot.normalized_data #>> "
            "'{infrastructure_snapshot,metadata,started_at}', "
            "snapshot.normalized_data #>> "
            "'{collection_metadata,infrastructure,completed_at}', "
            "snapshot.normalized_data #>> "
            "'{collection_metadata,infrastructure,started_at}')"
        )
        source_text_expression = (
            "COALESCE(snapshot.normalized_data #>> "
            "'{infrastructure_snapshot,metadata,source}', "
            "snapshot.normalized_data #>> "
            "'{collection_metadata,infrastructure,source}')"
        )
        infrastructure_expression = (
            "COALESCE(snapshot.normalized_data #> "
            "'{infrastructure_snapshot,infrastructure}', "
            "snapshot.normalized_data -> 'infrastructure')"
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
                      AND jsonb_typeof({infrastructure_expression}) = 'array'
                      AND ({source_text_expression}) = 'LIVE_API_COLLECTION'
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
        infrastructure_snapshot = result.get("infrastructure_snapshot")
        if isinstance(infrastructure_snapshot, Mapping):
            snapshot_servers = infrastructure_snapshot.get("servers")
            snapshot_infrastructure = infrastructure_snapshot.get(
                "infrastructure"
            )
            snapshot_metadata = infrastructure_snapshot.get("metadata")
            if isinstance(snapshot_servers, list):
                result["servers"] = list(snapshot_servers)
            if isinstance(snapshot_infrastructure, list):
                result["infrastructure"] = list(snapshot_infrastructure)
            if isinstance(snapshot_metadata, Mapping):
                collection_metadata = result.get("collection_metadata")
                collection_metadata = (
                    dict(collection_metadata)
                    if isinstance(collection_metadata, Mapping)
                    else {}
                )
                collection_metadata["infrastructure"] = dict(
                    snapshot_metadata
                )
                result["collection_metadata"] = collection_metadata
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

    def load_period_network_configuration_snapshot(
        self,
        period: Mapping[str, Any],
        customer: Mapping[str, Any],
        reference_at: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """Return the latest network configuration captured in the period.

        ``captured_at`` is the report-generation time, not the report lookup
        time and not an arbitrary historical state reconstructed from NCP.
        Consequently, only a snapshot whose capture time falls inside the
        requested period is eligible for reuse.
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
                    SELECT configuration, report_run_id, captured_at,
                           period_start, period_end, end_exclusive,
                           source, schema_version, capture_metadata
                    FROM {schema}.network_configuration_snapshots
                    WHERE tenant_id = %s
                      AND cloud_account_id = %s
                      AND captured_at >= %s
                      AND captured_at < %s
                    ORDER BY captured_at DESC, created_at DESC, id DESC
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
                "Historical network configuration snapshot lookup failed."
            ) from exc

        if not row or not isinstance(row[0], list):
            return None

        captured_at = self._parse_datetime(row[2])
        period_start = self._parse_datetime(row[3])
        period_end = self._parse_datetime(row[4])
        metadata = row[8] if isinstance(row[8], dict) else {}
        raw_selected_categories = metadata.get("selected_categories")
        selected_categories = (
            list(raw_selected_categories)
            if isinstance(raw_selected_categories, list)
            else []
        )
        return {
            "configuration": list(row[0]),
            "captured_at": captured_at.isoformat(),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "end_exclusive": bool(row[5]),
            "source": str(row[6]),
            "schema_version": str(row[7]),
            "metadata": dict(metadata),
            "selected_categories": selected_categories,
            "collection_source": metadata.get("collection_source"),
            "collection_completeness": metadata.get(
                "collection_completeness"
            ),
            "collection_issue_count": metadata.get(
                "collection_issue_count",
                0,
            ),
            "reused": True,
            "_snapshot_reference": {
                "report_run_id": str(row[1]),
                "captured_at": captured_at.isoformat(),
                "capture_basis": "REPORT_GENERATION_TIME",
                "reference_at": window["reference_at"].isoformat(),
                "eligible_start": window["eligible_start"].isoformat(),
                "eligible_end": window["eligible_end"].isoformat(),
                "snapshot_age_seconds": max(
                    0,
                    int(
                        (
                            window["reference_at"] - captured_at
                        ).total_seconds()
                    ),
                ),
            },
        }

    def load_previous_report_snapshot(
        self,
        period: Mapping[str, Any],
        customer: Mapping[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Return the latest comparable report that ended before this period.

        The lookup is tenant, cloud-account, environment and report-type
        scoped. A rerun of the same period therefore cannot accidentally use
        itself as the comparison baseline.
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

        period_start, _, _ = self._period_bounds(period)
        report_type = self._report_type(period)
        try:
            import psycopg
        except ImportError as exc:
            raise DatabasePersistenceError(
                "PostgreSQL support is not installed. Run: pip install -r requirements.txt"
            ) from exc

        schema = self.SCHEMAS[environment]
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
                    SELECT snapshot.normalized_data, report_run.id,
                           report_run.period_start, report_run.period_end,
                           report_run.completed_at
                    FROM {schema}.report_snapshots snapshot
                    JOIN control.report_runs report_run
                      ON report_run.id = snapshot.report_run_id
                     AND report_run.tenant_id = snapshot.tenant_id
                    WHERE snapshot.tenant_id = %s
                      AND report_run.cloud_account_id = %s
                      AND report_run.environment = %s
                      AND report_run.report_type = %s
                      AND report_run.status IN ('SUCCESS', 'PARTIAL_SUCCESS')
                      AND report_run.period_end <= %s
                      AND jsonb_typeof(snapshot.normalized_data) = 'object'
                    ORDER BY report_run.period_end DESC,
                             report_run.completed_at DESC NULLS LAST,
                             report_run.id DESC
                    LIMIT 1
                    """,
                    (
                        str(tenant_id),
                        str(cloud_account_id),
                        environment,
                        report_type,
                        period_start,
                    ),
                )
                row = cursor.fetchone()
        except Exception as exc:
            raise DatabasePersistenceError(
                "Previous report comparison lookup failed."
            ) from exc

        if not row or not isinstance(row[0], dict):
            return None
        result = dict(row[0])
        result["_comparison_reference"] = {
            "report_run_id": str(row[1]),
            "period_start": self._parse_datetime(row[2]).isoformat(),
            "period_end": self._parse_datetime(row[3]).isoformat(),
            "completed_at": (
                self._parse_datetime(row[4]).isoformat()
                if row[4] is not None
                else None
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
                '1.5', '1.5', '1.5', %s, 1, %s, clock_timestamp(), clock_timestamp()
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
            "network_configuration_snapshots",
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
            ) VALUES (%s, %s, '1.5', %s::jsonb, %s, '1.5', '1.5', '1.5')
            """,
            (
                report_run_id,
                tenant_id,
                payload,
                hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            ),
        )
        self._insert_network_configuration_snapshot(
            cursor,
            schema,
            report,
            report_run_id,
            tenant_id,
            cloud_account_id,
        )
        self._insert_insight_events(
            cursor, schema, report, report_run_id, tenant_id
        )
        self._insert_activity_events(
            cursor, schema, report, report_run_id, tenant_id
        )
        self._insert_metric_series(
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

    def _insert_network_configuration_snapshot(
        self,
        cursor: Any,
        schema: str,
        report: ReportResult,
        report_run_id: Any,
        tenant_id: Any,
        cloud_account_id: Any,
    ) -> None:
        """Persist a report-generation network snapshot in its own table.

        Reused historical data is deliberately not written again. Re-saving
        it with a new timestamp would make an old configuration look as if it
        had been observed at the current report generation time.
        """
        snapshot = getattr(report, "network_configuration_snapshot", None)
        if snapshot is None:
            return
        if not isinstance(snapshot, Mapping):
            raise DatabasePersistenceError(
                "Network configuration snapshot must be an object."
            )
        if not snapshot:
            return

        source = str(snapshot.get("source") or "").strip().upper()
        reused = bool(snapshot.get("reused"))
        if reused or source == "STORED_NETWORK_CONFIGURATION_SNAPSHOT":
            return
        if source != "REPORT_GENERATION":
            raise DatabasePersistenceError(
                "Network configuration snapshot source must be REPORT_GENERATION."
            )

        raw_configuration = snapshot.get("configuration")
        if not isinstance(raw_configuration, list):
            raise DatabasePersistenceError(
                "Network configuration snapshot data must be an array."
            )

        configuration = []
        configuration_categories = set()
        for item in raw_configuration:
            if not isinstance(item, Mapping):
                raise DatabasePersistenceError(
                    "Network configuration snapshot entries must be objects."
                )
            category = str(item.get("category") or "").strip().upper()
            if category not in self.NETWORK_CONFIGURATION_CATEGORIES:
                raise DatabasePersistenceError(
                    "Network configuration snapshot contains an unsupported category."
                )
            configuration.append(dict(item))
            configuration_categories.add(category)

        raw_selected_categories = snapshot.get("selected_categories")
        selected_categories = sorted({
            str(category).strip().upper()
            for category in (
                raw_selected_categories
                if isinstance(raw_selected_categories, (list, tuple, set))
                else []
            )
            if str(category).strip().upper()
            in self.NETWORK_CONFIGURATION_CATEGORIES
        })
        if not selected_categories:
            selected_categories = sorted(configuration_categories)
        if not selected_categories:
            return
        if not configuration_categories.issubset(selected_categories):
            raise DatabasePersistenceError(
                "Network configuration contains a category outside the selected scope."
            )

        raw_metadata = snapshot.get("metadata")
        metadata = raw_metadata if isinstance(raw_metadata, Mapping) else {}
        collection_issue_count = (
            metadata.get("collection_issue_count")
            if "collection_issue_count" in metadata
            else snapshot.get("collection_issue_count")
        )
        try:
            collection_issue_count = max(0, int(collection_issue_count or 0))
        except (TypeError, ValueError):
            collection_issue_count = 0
        category_counts = {
            category: sum(
                str(item.get("category") or "").upper() == category
                for item in configuration
            )
            for category in selected_categories
        }
        capture_metadata = {
            "capture_basis": "REPORT_GENERATION_TIME",
            "selected_categories": selected_categories,
            "category_counts": category_counts,
            "resource_count": len(configuration),
            "collection_source": self._text(
                metadata.get("collection_source")
                or snapshot.get("collection_source"),
                80,
            ),
            "collection_started_at": self._text(
                metadata.get("collection_started_at")
                or snapshot.get("collection_started_at"),
                80,
            ),
            "collection_completed_at": self._text(
                metadata.get("collection_completed_at")
                or snapshot.get("collection_completed_at"),
                80,
            ),
            "collection_completeness": self._text(
                metadata.get("collection_completeness")
                or snapshot.get("collection_completeness")
                or metadata.get("completeness")
                or snapshot.get("completeness"),
                80,
            ),
            "collection_issue_count": collection_issue_count,
        }
        capture_metadata = {
            key: value
            for key, value in capture_metadata.items()
            if value is not None
        }

        captured_at = self._parse_datetime(
            snapshot.get("captured_at") or report.generated_at
        )
        period_start, period_end, end_exclusive = self._period_bounds(
            report.period
        )
        configuration_payload = self._json(configuration)
        cursor.execute(
            f"""
            INSERT INTO {schema}.network_configuration_snapshots (
                report_run_id, tenant_id, cloud_account_id, captured_at,
                period_start, period_end, end_exclusive, source,
                schema_version, configuration, capture_metadata,
                content_hash_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, 'REPORT_GENERATION',
                %s, %s::jsonb, %s::jsonb, %s
            )
            """,
            (
                report_run_id,
                tenant_id,
                cloud_account_id,
                captured_at,
                period_start,
                period_end,
                end_exclusive,
                self.NETWORK_SNAPSHOT_SCHEMA_VERSION,
                configuration_payload,
                self._json(capture_metadata),
                hashlib.sha256(
                    configuration_payload.encode("utf-8")
                ).hexdigest(),
            ),
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

    def _insert_metric_series(
        self,
        cursor: Any,
        schema: str,
        report: ReportResult,
        report_run_id: Any,
        tenant_id: Any,
    ) -> None:
        """Persist sanitized chart points used by deterministic analysis.

        Raw provider responses may contain fields that are unnecessary for
        reporting. Only timestamp/value pairs and allowlisted dimensions are
        copied to the normalized metric table.
        """
        period_start, period_end, _ = self._period_bounds(report.period)
        for metric in report.server_metrics:
            if not isinstance(metric, Mapping):
                continue
            resource_id = self._text(metric.get("server_id"), 255)
            raw_metrics = metric.get("raw_metrics")
            if not resource_id or not isinstance(raw_metrics, Mapping):
                continue
            for metric_name, statistics in raw_metrics.items():
                if not isinstance(statistics, Mapping):
                    continue
                entries = statistics.get("avg")
                if not isinstance(entries, list):
                    entries = next(
                        (
                            value
                            for value in statistics.values()
                            if isinstance(value, list)
                        ),
                        [],
                    )
                for entry in entries:
                    if not isinstance(entry, Mapping):
                        continue
                    dimensions = self._safe_metric_dimensions(
                        entry.get("dimensions")
                    )
                    raw = entry.get("raw")
                    raw_points = (
                        raw.get("dps") if isinstance(raw, Mapping) else None
                    )
                    points = self._normalized_metric_points(raw_points)
                    if not points:
                        continue
                    cursor.execute(
                        f"""
                        INSERT INTO {schema}.metric_series (
                            report_run_id, tenant_id, resource_id,
                            resource_name, metric_group, metric_name,
                            dimensions, interval_name, aggregation,
                            period_start, period_end, points, point_count
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s::jsonb,
                            %s, %s, %s, %s, %s::jsonb, %s
                        )
                        """,
                        (
                            report_run_id,
                            tenant_id,
                            resource_id,
                            self._text(metric.get("server_name"), 500),
                            self._server_metric_group(
                                str(metric_name), dimensions
                            ),
                            self._text(metric_name, 255) or "unknown",
                            self._json(dimensions),
                            self._text(raw.get("interval"), 30)
                            if isinstance(raw, Mapping)
                            else None,
                            "AVG",
                            period_start,
                            period_end,
                            self._json(points),
                            len(points),
                        ),
                    )

        for group in report.infrastructure_metrics:
            if not isinstance(group, Mapping):
                continue
            metric_name = self._text(group.get("metric"), 255)
            if not metric_name:
                continue
            for series in group.get("series") or []:
                if not isinstance(series, Mapping):
                    continue
                resource_id = self._text(series.get("resource_id"), 255)
                points = self._normalized_metric_points(series.get("points"))
                if not resource_id or not points:
                    continue
                dimensions = self._safe_metric_dimensions(
                    series.get("dimensions")
                )
                dimensions.update({
                    key: value
                    for key, value in {
                        "category": self._text(group.get("category"), 80),
                        "product": self._text(group.get("product"), 120),
                        "unit": self._text(group.get("unit"), 40),
                    }.items()
                    if value
                })
                cursor.execute(
                    f"""
                    INSERT INTO {schema}.metric_series (
                        report_run_id, tenant_id, resource_id,
                        resource_name, metric_group, metric_name,
                        dimensions, interval_name, aggregation,
                        period_start, period_end, points, point_count
                    ) VALUES (
                        %s, %s, %s, %s, 'OTHER', %s, %s::jsonb,
                        %s, %s, %s, %s, %s::jsonb, %s
                    )
                    """,
                    (
                        report_run_id,
                        tenant_id,
                        resource_id,
                        self._text(series.get("resource_name"), 500),
                        metric_name,
                        self._json(dimensions),
                        self._text(group.get("interval"), 30),
                        self._text(group.get("aggregation"), 30),
                        period_start,
                        period_end,
                        self._json(points),
                        len(points),
                    ),
                )

    @staticmethod
    def _safe_metric_dimensions(value: Any) -> Dict[str, Any]:
        if not isinstance(value, Mapping):
            return {}
        allowed = {
            "instanceNo",
            "mnt_nm",
            "mount",
            "role",
            "nodeRole",
            "targetGroupNo",
            "loadBalancerInstanceNo",
        }
        return {
            str(key)[:80]: str(item)[:500]
            for key, item in value.items()
            if str(key) in allowed and item not in (None, "")
        }

    @staticmethod
    def _normalized_metric_points(value: Any) -> list[list[float | int]]:
        if not isinstance(value, list):
            return []
        points: dict[int, float] = {}
        for point in value:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            try:
                timestamp = int(float(point[0]))
                metric_value = float(point[1])
            except (TypeError, ValueError, OverflowError):
                continue
            if timestamp < 0 or not (-1e300 < metric_value < 1e300):
                continue
            points[timestamp] = metric_value
        return [
            [timestamp, points[timestamp]] for timestamp in sorted(points)
        ]

    @staticmethod
    def _server_metric_group(
        metric_name: str,
        dimensions: Mapping[str, Any],
    ) -> str:
        normalized = metric_name.strip().casefold()
        if normalized == "used_rto":
            return "CPU"
        if normalized == "mem_usert":
            return "MEM"
        if normalized == "fs_usert":
            mount = str(
                dimensions.get("mnt_nm") or dimensions.get("mount") or ""
            ).replace("\\", "/").rstrip("/")
            if mount in {"", "/"} or mount.casefold().startswith("c:"):
                return "ROOT_DISK"
            return "DATA_DISK"
        return "OTHER"

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
        tenant_id: Any, environment: str, cloud_account_id: Any,
    ) -> None:
        insight = [event for event in report.insight_events if isinstance(event, dict)]
        insight_levels = [
            str(event.get("level") or "").upper() for event in insight
        ]
        analysis = (
            report.analysis if isinstance(report.analysis, Mapping) else {}
        )
        active_findings = [
            finding
            for finding in analysis.get("findings") or []
            if isinstance(finding, Mapping)
            and finding.get("status") != "EXCEPTION"
            and finding.get("category") != "DATA_QUALITY"
        ]
        finding_levels = [
            str(finding.get("severity") or "").upper()
            for finding in active_findings
        ]
        levels = finding_levels if analysis else insight_levels
        quality = (
            analysis.get("data_quality")
            if isinstance(analysis.get("data_quality"), Mapping)
            else {}
        )
        quality_status = str(
            quality.get("overall_status") or ""
        ).upper()
        if quality_status == "COMPLETE":
            collection_status = "SUCCESS"
        elif quality_status == "FAILED":
            collection_status = "FAILED"
        elif quality_status:
            collection_status = "PARTIAL_SUCCESS"
        else:
            collection_status = (
                "PARTIAL_SUCCESS" if report.collection_errors else "SUCCESS"
            )
        activities = list(self._event_records(report.activity_events))
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
        fact_date = self._period_bounds(report.period)[0].date()
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"daily-fact:{tenant_id}:{fact_date.isoformat()}",),
        )
        cursor.execute(
            """
            INSERT INTO control.daily_account_facts (
                tenant_id, cloud_account_id, fact_date, environment,
                latest_report_run_id,
                collection_status, server_count, critical_count, warning_count,
                info_count, activity_failure_count, collection_error_count,
                estimated_cost, confirmed_cost, cost_confidence
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (tenant_id, cloud_account_id, fact_date) DO UPDATE SET
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
                tenant_id, cloud_account_id,
                fact_date, environment,
                report_run_id, collection_status,
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
        # 구버전 코드 원복 호환을 위해 기존 고객/일자 사실 테이블의 키와
        # 쓰기 계약은 유지하고, 새 계정별 사실을 합산한 값만 갱신한다.
        cursor.execute(
            """
            INSERT INTO control.daily_customer_facts (
                tenant_id, fact_date, environment, latest_report_run_id,
                collection_status, server_count, critical_count, warning_count,
                info_count, activity_failure_count, collection_error_count,
                estimated_cost, confirmed_cost, cost_confidence
            )
            SELECT
                tenant_id,
                fact_date,
                environment,
                (
                    array_agg(
                        latest_report_run_id ORDER BY updated_at DESC
                    ) FILTER (WHERE latest_report_run_id IS NOT NULL)
                )[1],
                CASE
                    WHEN bool_or(collection_status = 'FAILED') THEN 'FAILED'
                    WHEN bool_or(
                        collection_status IS DISTINCT FROM 'SUCCESS'
                    ) THEN 'PARTIAL_SUCCESS'
                    ELSE 'SUCCESS'
                END,
                sum(server_count)::integer,
                sum(critical_count)::integer,
                sum(warning_count)::integer,
                sum(info_count)::integer,
                sum(activity_failure_count)::integer,
                sum(collection_error_count)::integer,
                sum(estimated_cost),
                sum(confirmed_cost),
                CASE
                    WHEN bool_or(cost_confidence = 'UNAVAILABLE')
                        THEN 'UNAVAILABLE'
                    WHEN bool_or(cost_confidence = 'PARTIAL') THEN 'PARTIAL'
                    WHEN bool_or(cost_confidence = 'VERIFIED_ESTIMATE')
                        THEN 'VERIFIED_ESTIMATE'
                    WHEN bool_or(cost_confidence = 'CONFIRMED')
                        THEN 'CONFIRMED'
                    ELSE NULL
                END
            FROM control.daily_account_facts
            WHERE tenant_id = %s AND fact_date = %s
            GROUP BY tenant_id, fact_date, environment
            ON CONFLICT (tenant_id, fact_date) DO UPDATE SET
                environment = EXCLUDED.environment,
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
            (tenant_id, fact_date),
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

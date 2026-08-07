from app.apifactory import APIFactory
from app.customer import CustomerProfile
from app.infrastructure_topology import InfrastructureTopologyBuilder
from app.renderers import HtmlReportRenderer
from app.report_models import ReportResult
from app.report_options import ReportOptions
from collectors import (
    ServerCollector,
    InsightMetricCollector,
    ActivityTracerEventCollector,
    BillingCollector,
    InfrastructureCollector,
    InfrastructureMetricCollector,
    OrganizationCollector,
)
from collectors.insighteventcollector import InsightEventCollector
from normalizers.billingnormalizer import BillingNormalizer
from utils.common_rest import safe_exception_message
from utils.data_utils import get_unix_time_stamp
from utils.event_sort import sort_event_records

import json
import calendar
import logging
import os
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo


class ReportRunner:
    KST = ZoneInfo("Asia/Seoul")

    def __init__(
        self,
        output_dir: Optional[str] = None,
        api_factory: Optional[APIFactory] = None,
        customer: Optional[CustomerProfile] = None,
        report_repository: Optional[Any] = None,
    ):
        self.api_factory = api_factory or APIFactory()
        self.customer = customer
        self.report_repository = report_repository
        base_output_dir = Path(
            output_dir
            or os.getenv("REPORT_OUTPUT_DIR")
            or "./output/report"
        )
        if customer is not None and not customer.is_default:
            base_output_dir = base_output_dir / customer.customer_id
        if (
            output_dir is None
            and not os.getenv("REPORT_OUTPUT_DIR")
            and (customer is None or customer.is_default)
        ):
            self.output_dir = "./output/report"
        else:
            self.output_dir = str(base_output_dir)

    def get_month_range(self) -> Dict[str, Any]:
        today = self._today_kst()

        first_day_this_month = today.replace(day=1)
        last_day_prev_month = first_day_this_month - timedelta(days=1)
        first_day_prev_month = last_day_prev_month.replace(day=1)

        return self.build_period(
            start=first_day_prev_month,
            end=last_day_prev_month,
            period_type="prev_month",
        )

    def get_period(
        self,
        target_month: Optional[str] = None,
        target_day: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        start_datetime: Optional[str] = None,
        end_datetime: Optional[str] = None,
    ) -> Dict[str, Any]:
        if start_datetime and end_datetime:
            start_dt = self._parse_kst_datetime(start_datetime)
            end_dt = self._parse_kst_datetime(end_datetime)

            if start_dt >= end_dt:
                raise ValueError(
                    "start_datetime은 end_datetime보다 빨라야 합니다."
                )

            effective_end = end_dt - timedelta(milliseconds=1)
            if start_dt.strftime("%Y%m") != effective_end.strftime("%Y%m"):
                raise ValueError(
                    "Billing API 기준으로 동일 월 안의 시간 범위만 지정하세요."
                )

            return self.build_datetime_period(
                start=start_dt,
                end=end_dt,
            )

        if target_day:
            start = datetime.strptime(target_day, "%Y-%m-%d").date()
            end = start
            period_type = "day"

        elif target_month:
            start = datetime.strptime(target_month, "%Y-%m").date().replace(day=1)

            if start.month == 12:
                next_month = start.replace(year=start.year + 1, month=1)
            else:
                next_month = start.replace(month=start.month + 1)

            end = next_month - timedelta(days=1)
            period_type = "month"

        elif start_date and end_date:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()

            if start > end:
                raise ValueError("start_date는 end_date보다 늦을 수 없습니다.")

            if start.strftime("%Y%m") != end.strftime("%Y%m"):
                raise ValueError("Billing API 기준으로는 동일 월 안의 기간만 지정하세요.")

            period_type = "range"

        else:
            return self.get_month_range()

        return self.build_period(
            start=start,
            end=end,
            period_type=period_type,
        )

    def build_datetime_period(
        self,
        start: datetime,
        end: datetime,
    ) -> Dict[str, Any]:
        """Build a KST period whose end boundary is exclusive."""
        start_kst = self._as_kst(start)
        end_kst = self._as_kst(end)
        effective_end = end_kst - timedelta(milliseconds=1)
        start_text = self._format_period_boundary(start_kst)
        end_text = self._format_period_boundary(end_kst)

        return {
            "period_type": "datetime_range",
            "start_dt": start_text,
            "end_dt": end_text,
            "end_exclusive": True,
            "start_time": int(start_kst.timestamp() * 1000),
            "end_time": int(end_kst.timestamp() * 1000) - 1,
            "use_start_date": start_kst.strftime("%Y%m%d"),
            "use_end_date": effective_end.strftime("%Y%m%d"),
            "billing_month": start_kst.strftime("%Y%m"),
            "file_suffix": (
                f"{start_kst:%Y%m%d_%H%M%S}_"
                f"{end_kst:%Y%m%d_%H%M%S}"
            ),
            "is_full_month": False,
            "is_closed_month": False,
            "billing_scope": "date_only",
        }

    @staticmethod
    def _format_period_boundary(value: datetime) -> str:
        timespec = "milliseconds" if value.microsecond else "seconds"
        return value.replace(tzinfo=None).isoformat(
            sep=" ",
            timespec=timespec,
        )

    def build_period(
        self,
        start: date,
        end: date,
        period_type: str,
    ) -> Dict[str, Any]:
        start_dt = f"{start:%Y-%m-%d} 00:00:00"
        end_dt = f"{end:%Y-%m-%d} 23:59:59"
        is_full_month = (
            start.year == end.year
            and start.month == end.month
            and start.day == 1
            and end.day == calendar.monthrange(end.year, end.month)[1]
        )
        first_day_current_month = self._today_kst().replace(day=1)
        is_closed_month = is_full_month and end < first_day_current_month

        return {
            "period_type": period_type,
            "start_dt": start_dt,
            "end_dt": end_dt,
            "start_time": get_unix_time_stamp(start_dt),
            "end_time": get_unix_time_stamp(end_dt),
            "use_start_date": f"{start:%Y%m%d}",
            "use_end_date": f"{end:%Y%m%d}",
            "billing_month": f"{start:%Y%m}",
            "file_suffix": f"{start:%Y%m%d}_{end:%Y%m%d}",
            "is_full_month": is_full_month,
            "is_closed_month": is_closed_month,
        }

    def _today_kst(self) -> date:
        return datetime.now(self.KST).date()

    def _parse_kst_datetime(self, value: str) -> datetime:
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("조회 일시는 비어 있을 수 없습니다.")

        normalized = self._resolve_relative_datetime(normalized)

        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"

        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(
                "조회 일시는 YYYY-MM-DD HH:MM[:SS], "
                "today/yesterday HH:MM[:SS] 또는 ISO 8601 형식이어야 합니다."
            ) from exc
        return self._as_kst(parsed)

    def _resolve_relative_datetime(self, value: str) -> str:
        aliases = {
            "today": 0,
            "오늘": 0,
            "yesterday": -1,
            "어제": -1,
        }
        folded = value.casefold()
        for alias, day_offset in aliases.items():
            for separator in (" ", "T"):
                prefix = alias + separator
                if not folded.startswith(prefix.casefold()):
                    continue
                clock = value[len(prefix):].strip()
                if not clock:
                    break
                resolved_date = self._today_kst() + timedelta(
                    days=day_offset
                )
                return f"{resolved_date.isoformat()}T{clock}"
        return value

    def _as_kst(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=self.KST)
        return value.astimezone(self.KST)

    def _billing_period_context(self, period: Dict[str, Any]) -> Dict[str, Any]:
        target_month = datetime.strptime(period["billing_month"], "%Y%m").date()
        target_month = target_month.replace(day=1)
        current_month = self._today_kst().replace(day=1)
        target_month_closed = target_month < current_month
        if target_month_closed:
            confirmed_month = target_month
        else:
            confirmed_month = current_month - timedelta(days=1)
            confirmed_month = confirmed_month.replace(day=1)

        requested_end = datetime.strptime(
            period["use_end_date"], "%Y%m%d"
        ).date()
        usage_end = min(requested_end, self._today_kst())
        month_to_date_start = target_month
        month_to_date_end = usage_end if usage_end >= target_month else None

        return {
            "confirmed_demand_month": confirmed_month.strftime("%Y%m"),
            "target_month_closed": target_month_closed,
            "usage_query_end_date": usage_end.strftime("%Y%m%d"),
            "month_to_date_start": month_to_date_start.strftime("%Y%m%d"),
            "month_to_date_end": (
                month_to_date_end.strftime("%Y%m%d")
                if month_to_date_end is not None
                else None
            ),
            "calculated_at": datetime.now(self.KST).isoformat(timespec="seconds"),
        }

    def _selected_report_options(self) -> ReportOptions:
        customer = getattr(self, "customer", None)
        return ReportOptions.from_value(
            getattr(customer, "report_options", None)
        )

    def _now_kst_iso(self) -> str:
        return datetime.now(self.KST).isoformat(timespec="microseconds")

    def _period_bounds_kst(
        self,
        period: Dict[str, Any],
    ) -> tuple[datetime, datetime]:
        """Return canonical ``[start, end)`` report bounds in KST."""
        period_start = self._parse_kst_datetime(period["start_dt"])
        period_end = self._parse_kst_datetime(period["end_dt"])
        if not period.get("end_exclusive"):
            period_end += timedelta(seconds=1)
        if period_start >= period_end:
            raise ValueError("Report period is invalid.")
        return period_start, period_end

    def _snapshot_eligibility_window(
        self,
        period: Dict[str, Any],
        reference_at: Any,
    ) -> Optional[Dict[str, datetime]]:
        """Return the report-period window observed up to ``reference_at``."""
        try:
            period_start, period_end = self._period_bounds_kst(period)
            requested_reference = self._parse_kst_datetime(str(reference_at))
        except (KeyError, TypeError, ValueError):
            return None
        if requested_reference < period_start:
            return None

        reference = min(
            requested_reference,
            period_end - timedelta(microseconds=1),
        )
        eligible_start = period_start
        eligible_end = min(
            period_end,
            reference + timedelta(microseconds=1),
        )
        if eligible_start >= eligible_end:
            return None
        return {
            "reference_at": reference,
            "eligible_start": eligible_start,
            "eligible_end": eligible_end,
        }

    @staticmethod
    def _snapshot_window_metadata(
        window: Optional[Dict[str, datetime]],
        observed_at: Any = None,
    ) -> Dict[str, Any]:
        if not window:
            return {
                "reference_at": None,
                "eligible_start": None,
                "eligible_end": None,
                "snapshot_age_seconds": None,
            }
        metadata: Dict[str, Any] = {
            key: window[key].isoformat()
            for key in ("reference_at", "eligible_start", "eligible_end")
        }
        metadata["snapshot_age_seconds"] = None
        if isinstance(observed_at, datetime):
            metadata["snapshot_age_seconds"] = max(
                0,
                int((window["reference_at"] - observed_at).total_seconds()),
            )
        return metadata

    def _snapshot_observed_in_window(
        self,
        period: Dict[str, Any],
        observed_at: Any,
        reference_at: Any,
    ) -> bool:
        try:
            observed = self._parse_kst_datetime(str(observed_at))
        except (TypeError, ValueError):
            return False
        window = self._snapshot_eligibility_window(period, reference_at)
        return bool(
            window
            and window["eligible_start"] <= observed < window["eligible_end"]
        )

    def _period_contains_timestamp(
        self,
        period: Dict[str, Any],
        timestamp: Any,
    ) -> bool:
        try:
            observed_at = self._parse_kst_datetime(str(timestamp))
            period_start, period_end = self._period_bounds_kst(period)
        except (KeyError, TypeError, ValueError):
            return False
        return period_start <= observed_at < period_end

    def _load_period_infrastructure_snapshot(
        self,
        period: Dict[str, Any],
        customer: Dict[str, Any],
        reference_at: Any,
    ) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        repository = getattr(self, "report_repository", None)
        loader = getattr(
            repository,
            "load_period_infrastructure_snapshot",
            None,
        )
        if not callable(loader):
            return None, None
        try:
            snapshot = loader(
                period,
                customer,
                reference_at=reference_at,
            )
        except Exception as exc:
            return None, {
                "collector": "InfrastructureSnapshotRepository",
                "stage": "historical_snapshot_lookup",
                "target_type": "infrastructure",
                "api": "postgresql",
                "severity": "warning",
                "exception_type": type(exc).__name__,
                "message": safe_exception_message(exc),
            }
        if not isinstance(snapshot, dict):
            return None, None

        snapshot_reference = snapshot.get("_snapshot_reference")
        if not isinstance(snapshot_reference, dict):
            snapshot_reference = {}
        snapshot_metadata = snapshot.get("collection_metadata")
        infrastructure_metadata = (
            snapshot_metadata.get("infrastructure")
            if isinstance(snapshot_metadata, dict)
            else None
        )
        if not isinstance(infrastructure_metadata, dict):
            infrastructure_metadata = {}
        observed_at = (
            snapshot_reference.get("observed_at")
            or infrastructure_metadata.get("completed_at")
            or infrastructure_metadata.get("started_at")
        )
        effective_reference = (
            snapshot_reference.get("reference_at") or reference_at
        )
        if not self._snapshot_observed_in_window(
            period,
            observed_at,
            effective_reference,
        ):
            return None, {
                "collector": "InfrastructureSnapshotRepository",
                "stage": "historical_snapshot_validation",
                "target_type": "infrastructure",
                "severity": "warning",
                "code": "SNAPSHOT_OUTSIDE_REFERENCE_WINDOW",
                "message": (
                    "저장된 인프라 스냅샷이 보고 기준일의 허용 범위를 "
                    "벗어나 사용하지 않았습니다."
                ),
            }
        return snapshot, None

    def _build_period_topology(
        self,
        *,
        period: Dict[str, Any],
        infrastructure: List[Dict[str, Any]],
        collection_metadata: Dict[str, Any],
        report_options: ReportOptions,
    ) -> Dict[str, Any]:
        infrastructure_metadata = collection_metadata.get("infrastructure")
        if not isinstance(infrastructure_metadata, dict):
            infrastructure_metadata = {}
        observed_at = (
            infrastructure_metadata.get("completed_at")
            or infrastructure_metadata.get("started_at")
        )
        source = str(infrastructure_metadata.get("source") or "UNAVAILABLE")
        reference_at = (
            infrastructure_metadata.get("reference_at")
            or self._now_kst_iso()
        )
        window = self._snapshot_eligibility_window(period, reference_at)
        try:
            parsed_observed_at = self._parse_kst_datetime(str(observed_at))
        except (TypeError, ValueError):
            parsed_observed_at = None
        window_metadata = self._snapshot_window_metadata(
            window,
            parsed_observed_at,
        )
        if (
            not observed_at
            or not self._snapshot_observed_in_window(
                period,
                observed_at,
                reference_at,
            )
        ):
            return {
                "nodes": [],
                "edges": [],
                "unmapped_node_ids": [],
                "unresolved_node_ids": [],
                "warnings": [{
                    "code": "PERIOD_SNAPSHOT_UNAVAILABLE",
                    "message": (
                        "보고 기간 안에 실제 수집된 인프라 스냅샷이 없어 "
                        "현재 구성을 대신 그리지 않았습니다."
                    ),
                    "source": "stored_report_snapshot",
                    "confidence": "UNAVAILABLE",
                }],
                "summary": {
                    "representative_node_count": 0,
                    "supporting_node_count": 0,
                    "verified_edge_count": 0,
                    "total_verified_edge_count": 0,
                    "unmapped_resource_count": 0,
                    "unresolved_reference_count": 0,
                    "collected_at": observed_at,
                    "max_nodes": report_options.diagram_option("max_nodes"),
                    "truncated": False,
                    "omitted_node_count": 0,
                    "confidence": "UNAVAILABLE",
                    "relationship_confidence": "UNAVAILABLE",
                    "relationship_coverage": "UNAVAILABLE",
                    "inventory_completeness": "UNAVAILABLE",
                    "collection_issue_count": 1,
                    "time_basis": "REPORT_PERIOD",
                    "snapshot_source": source,
                    "period_start": period.get("start_dt"),
                    "period_end": period.get("end_dt"),
                    **window_metadata,
                },
            }

        topology = InfrastructureTopologyBuilder().build(
            infrastructure,
            collected_at=str(observed_at),
            max_nodes=report_options.diagram_option("max_nodes"),
            allowed_reference_categories=report_options.to_dict()[
                "resource_categories"
            ],
            inventory_completeness=str(
                infrastructure_metadata.get("inventory_completeness")
                or "UNKNOWN"
            ),
            collection_issue_count=(
                infrastructure_metadata.get("collection_issue_count") or 0
            ),
        )
        summary = topology.setdefault("summary", {})
        summary.update({
            "time_basis": "REPORT_PERIOD",
            "snapshot_source": source,
            "period_start": period.get("start_dt"),
            "period_end": period.get("end_dt"),
            "source_report_run_id": infrastructure_metadata.get(
                "source_report_run_id"
            ),
            **window_metadata,
        })
        return topology

    def run(
        self,
        target_month: Optional[str] = None,
        target_day: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        start_datetime: Optional[str] = None,
        end_datetime: Optional[str] = None,
    ) -> ReportResult:
        period = self.get_period(
            target_month=target_month,
            target_day=target_day,
            start_date=start_date,
            end_date=end_date,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
        )
        billing_context = self._billing_period_context(period)
        period.update(billing_context)

        self.print_period_summary(period)
        report_options = self._selected_report_options()
        report_options_snapshot = report_options.to_dict()
        customer_snapshot = (
            getattr(self, "customer", None).to_dict()
            if getattr(self, "customer", None) is not None
            else {}
        )
        selected_resource_categories = set(
            report_options_snapshot["resource_categories"]
        )
        selected_monitoring_categories = set(
            report_options_snapshot["monitoring_categories"]
        )
        inventory_enabled = report_options.section_enabled(
            "infrastructure_inventory"
        )
        diagram_enabled = (
            report_options.section_enabled("infrastructure_diagram")
            and bool(report_options.diagram_option("enabled", True))
        )
        monitoring_enabled = report_options.section_enabled("monitoring")
        active_monitoring_categories = (
            selected_monitoring_categories if monitoring_enabled else set()
        )
        monitored_infrastructure_categories = (
            active_monitoring_categories - {"SERVER"}
        )
        collection_resource_categories = set()
        if inventory_enabled or diagram_enabled:
            collection_resource_categories.update(
                selected_resource_categories
            )
        collection_resource_categories.update(active_monitoring_categories)
        needs_infrastructure_collection = bool(
            collection_resource_categories
        )
        needs_resource_snapshot = (
            needs_infrastructure_collection
            or (
                monitoring_enabled
                and "SERVER" in selected_monitoring_categories
            )
        )

        observation_check_at = self._now_kst_iso()
        request_snapshot_window = self._snapshot_eligibility_window(
            period,
            observation_check_at,
        )
        live_snapshot_in_period = self._period_contains_timestamp(
            period,
            observation_check_at,
        )
        period_snapshot = None
        snapshot_lookup_warning = None
        if needs_resource_snapshot and not live_snapshot_in_period:
            (
                period_snapshot,
                snapshot_lookup_warning,
            ) = self._load_period_infrastructure_snapshot(
                period,
                customer_snapshot,
                observation_check_at,
            )
        needs_server_collection = (
            live_snapshot_in_period
            and (
                "SERVER" in collection_resource_categories
                or (
                    monitoring_enabled
                    and "SERVER" in selected_monitoring_categories
                )
            )
        )

        collection_metadata: Dict[str, Any] = {}
        server_data: List[Dict[str, Any]] = []
        server_errors: List[Dict[str, Any]] = []
        server_raw_data: Dict[str, Any] = {}
        infrastructure_collected_data: List[Dict[str, Any]] = []
        infrastructure_errors: List[Dict[str, Any]] = []
        infrastructure_warnings: List[Dict[str, Any]] = []
        if snapshot_lookup_warning:
            infrastructure_warnings.append(snapshot_lookup_warning)

        if period_snapshot is not None:
            server_data = self._dict_records(
                period_snapshot.get("servers")
            )
            infrastructure_collected_data = self._dict_records(
                period_snapshot.get("infrastructure")
            )
            snapshot_options_value = period_snapshot.get("report_options")
            snapshot_resource_categories: Optional[set[str]] = None
            if isinstance(snapshot_options_value, dict):
                snapshot_resource_categories = set(
                    ReportOptions.from_value(
                        snapshot_options_value
                    ).to_dict()["resource_categories"]
                )
            snapshot_metadata = period_snapshot.get("collection_metadata")
            snapshot_infrastructure_metadata = (
                snapshot_metadata.get("infrastructure")
                if isinstance(snapshot_metadata, dict)
                else None
            )
            if not isinstance(snapshot_infrastructure_metadata, dict):
                snapshot_infrastructure_metadata = {}
            metadata_categories = (
                snapshot_infrastructure_metadata.get(
                    "collected_categories"
                )
                or snapshot_infrastructure_metadata.get(
                    "resource_categories"
                )
            )
            if isinstance(metadata_categories, list):
                snapshot_resource_categories = {
                    str(category).upper()
                    for category in metadata_categories
                }
            snapshot_reference = period_snapshot.get("_snapshot_reference")
            if not isinstance(snapshot_reference, dict):
                snapshot_reference = {}
            stored_observed_at = (
                snapshot_infrastructure_metadata.get("completed_at")
                or snapshot_infrastructure_metadata.get("started_at")
                or snapshot_reference.get("observed_at")
            )
            stored_reference_at = (
                snapshot_reference.get("reference_at")
                or observation_check_at
            )
            stored_window = self._snapshot_eligibility_window(
                period,
                stored_reference_at,
            )
            try:
                parsed_stored_observed_at = self._parse_kst_datetime(
                    str(stored_observed_at)
                )
            except (TypeError, ValueError):
                parsed_stored_observed_at = None
            collection_metadata["infrastructure"] = {
                **snapshot_infrastructure_metadata,
                "completed_at": stored_observed_at,
                "source": "STORED_REPORT_SNAPSHOT",
                "time_basis": "REPORT_PERIOD",
                "source_report_run_id": snapshot_reference.get(
                    "report_run_id"
                ),
                **self._snapshot_window_metadata(
                    stored_window,
                    parsed_stored_observed_at,
                ),
            }

            original_issue_count = snapshot_infrastructure_metadata.get(
                "collection_issue_count"
            )
            try:
                original_issue_count = max(0, int(original_issue_count or 0))
            except (TypeError, ValueError):
                original_issue_count = 1
            original_completeness = str(
                snapshot_infrastructure_metadata.get(
                    "inventory_completeness"
                )
                or "UNKNOWN"
            ).upper()
            coverage_issue_count = 0
            if snapshot_resource_categories is None:
                infrastructure_warnings.append({
                    "collector": "InfrastructureSnapshotRepository",
                    "stage": "historical_snapshot_coverage",
                    "target_type": "infrastructure",
                    "severity": "warning",
                    "code": "SNAPSHOT_CATEGORY_COVERAGE_UNKNOWN",
                    "message": (
                        "저장된 과거 스냅샷에 수집 자원 범주 메타데이터가 없어 "
                        "현재 선택 항목의 전체 포함 여부를 검증할 수 없습니다."
                    ),
                })
                collection_metadata["infrastructure"].update({
                    "inventory_completeness": "PARTIAL",
                    "collection_issue_count": original_issue_count + 1,
                })
            else:
                missing_categories = sorted(
                    collection_resource_categories
                    - snapshot_resource_categories
                )
                if missing_categories:
                    coverage_issue_count = 1
                    infrastructure_warnings.append({
                        "collector": "InfrastructureSnapshotRepository",
                        "stage": "historical_snapshot_coverage",
                        "target_type": "infrastructure",
                        "severity": "warning",
                        "code": "SNAPSHOT_CATEGORY_COVERAGE_INCOMPLETE",
                        "missing_categories": missing_categories,
                        "message": (
                            "저장된 과거 스냅샷이 현재 선택한 일부 자원 범주를 "
                            "수집하지 않아 구성도에서 제외했습니다."
                        ),
                    })
                collection_metadata["infrastructure"].update({
                    "inventory_completeness": (
                        "PARTIAL"
                        if (
                            missing_categories
                            or original_issue_count
                            or original_completeness
                            not in {
                                "COMPLETE_FOR_SELECTED_SCOPE",
                                "COMPLETE_FOR_SNAPSHOT_SCOPE",
                            }
                        )
                        else "COMPLETE_FOR_SNAPSHOT_SCOPE"
                    ),
                    "collection_issue_count": (
                        original_issue_count + coverage_issue_count
                    ),
                })
        elif needs_resource_snapshot and not live_snapshot_in_period:
            collection_metadata["infrastructure"] = {
                "source": "UNAVAILABLE",
                "time_basis": "REPORT_PERIOD",
                "period_start": period.get("start_dt"),
                "period_end": period.get("end_dt"),
                "inventory_completeness": "UNAVAILABLE",
                "collection_issue_count": 1,
                **self._snapshot_window_metadata(request_snapshot_window),
            }
            infrastructure_warnings.append({
                "collector": "InfrastructureCollector",
                "stage": "historical_snapshot_lookup",
                "target_type": "infrastructure",
                "severity": "warning",
                "code": "PERIOD_SNAPSHOT_UNAVAILABLE",
                "message": (
                    "보고 기간 안에 실제 수집된 인프라 스냅샷이 없어 "
                    "현재 자원 목록과 구성도를 대신 사용하지 않았습니다."
                ),
            })

        if needs_server_collection:
            server_collector = ServerCollector(api_factory=self.api_factory)
            server_data = server_collector.collect()
            server_errors = list(
                getattr(server_collector, "last_errors", [])
            )
            server_raw_data = getattr(
                server_collector,
                "last_raw_data",
                {},
            )

        if needs_infrastructure_collection and live_snapshot_in_period:
            infrastructure_started_at = self._now_kst_iso()
            (
                infrastructure_collected_data,
                infrastructure_errors,
                infrastructure_warnings,
            ) = self.collect_infrastructure(
                servers=server_data,
                server_raw_data=server_raw_data,
                categories=collection_resource_categories,
            )
            infrastructure_completed_at = self._now_kst_iso()
            live_snapshot_window = self._snapshot_eligibility_window(
                period,
                infrastructure_completed_at,
            )
            parsed_live_completed_at = self._parse_kst_datetime(
                infrastructure_completed_at
            )
            collection_metadata["infrastructure"] = {
                "started_at": infrastructure_started_at,
                "completed_at": infrastructure_completed_at,
                "source": "LIVE_API_COLLECTION",
                "time_basis": "REPORT_PERIOD",
                "resource_categories": sorted(
                    selected_resource_categories
                ),
                "collected_categories": sorted(
                    collection_resource_categories
                ),
                "persisted_categories": sorted({
                    str(item.get("category") or "").upper()
                    for item in infrastructure_collected_data
                    if isinstance(item, dict) and item.get("category")
                }),
                "persisted_resource_count": len(
                    infrastructure_collected_data
                ),
                "persisted_server_count": len(server_data),
                "inventory_completeness": (
                    "PARTIAL"
                    if (
                        server_errors
                        or infrastructure_errors
                        or infrastructure_warnings
                    )
                    else "COMPLETE_FOR_SELECTED_SCOPE"
                ),
                "collection_issue_count": (
                    len(server_errors)
                    + len(infrastructure_errors)
                    + len(infrastructure_warnings)
                ),
                **self._snapshot_window_metadata(
                    live_snapshot_window,
                    parsed_live_completed_at,
                ),
            }

            completed_at = collection_metadata["infrastructure"].get(
                "completed_at"
            )
            if not self._period_contains_timestamp(period, completed_at):
                boundary_snapshot, boundary_lookup_warning = (
                    self._load_period_infrastructure_snapshot(
                        period,
                        customer_snapshot,
                        completed_at,
                    )
                )
                infrastructure_warnings.append({
                    "collector": "InfrastructureCollector",
                    "stage": "period_boundary_validation",
                    "target_type": "infrastructure",
                    "severity": "warning",
                    "code": "LIVE_SNAPSHOT_OUTSIDE_PERIOD",
                    "message": (
                        "인프라 수집이 보고 기간 종료 경계를 넘어 완료되어 "
                        "해당 실시간 결과를 보고서에서 제외했습니다."
                    ),
                })
                if boundary_lookup_warning:
                    infrastructure_warnings.append(
                        boundary_lookup_warning
                    )
                if boundary_snapshot is not None:
                    server_data = self._dict_records(
                        boundary_snapshot.get("servers")
                    )
                    infrastructure_collected_data = self._dict_records(
                        boundary_snapshot.get("infrastructure")
                    )
                    boundary_metadata = boundary_snapshot.get(
                        "collection_metadata"
                    )
                    if not isinstance(boundary_metadata, dict):
                        boundary_metadata = {}
                    boundary_infrastructure_metadata = (
                        boundary_metadata.get("infrastructure")
                    )
                    if not isinstance(
                        boundary_infrastructure_metadata,
                        dict,
                    ):
                        boundary_infrastructure_metadata = {}
                    boundary_reference = boundary_snapshot.get(
                        "_snapshot_reference"
                    )
                    if not isinstance(boundary_reference, dict):
                        boundary_reference = {}
                    boundary_observed_at = (
                        boundary_infrastructure_metadata.get(
                            "completed_at"
                        )
                        or boundary_infrastructure_metadata.get(
                            "started_at"
                        )
                        or boundary_reference.get("observed_at")
                    )
                    boundary_reference_at = (
                        boundary_reference.get("reference_at")
                        or completed_at
                    )
                    boundary_window = self._snapshot_eligibility_window(
                        period,
                        boundary_reference_at,
                    )
                    try:
                        parsed_boundary_observed_at = (
                            self._parse_kst_datetime(
                                str(boundary_observed_at)
                            )
                        )
                    except (TypeError, ValueError):
                        parsed_boundary_observed_at = None
                    collection_metadata["infrastructure"] = {
                        **boundary_infrastructure_metadata,
                        "completed_at": boundary_observed_at,
                        "source": "STORED_REPORT_SNAPSHOT",
                        "time_basis": "REPORT_PERIOD",
                        "source_report_run_id": boundary_reference.get(
                            "report_run_id"
                        ),
                        **self._snapshot_window_metadata(
                            boundary_window,
                            parsed_boundary_observed_at,
                        ),
                    }
                    boundary_observed_at = collection_metadata[
                        "infrastructure"
                    ].get("completed_at")
                    if not self._period_contains_timestamp(
                        period,
                        boundary_observed_at,
                    ):
                        server_data = []
                        infrastructure_collected_data = []
                        server_raw_data = {}
                        collection_metadata["infrastructure"] = {
                            "source": "UNAVAILABLE",
                            "time_basis": "REPORT_PERIOD",
                            "period_start": period.get("start_dt"),
                            "period_end": period.get("end_dt"),
                            "inventory_completeness": "UNAVAILABLE",
                            "collection_issue_count": 1,
                        }
                        infrastructure_warnings.append({
                            "collector": "InfrastructureSnapshotRepository",
                            "stage": "period_boundary_fallback_validation",
                            "target_type": "infrastructure",
                            "severity": "warning",
                            "code": "SNAPSHOT_OUTSIDE_REPORT_PERIOD",
                            "message": (
                                "경계 대체 스냅샷의 관측 시각이 보고 기간 "
                                "밖이어서 사용하지 않았습니다."
                            ),
                        })
                    else:
                        boundary_categories = (
                            boundary_infrastructure_metadata.get(
                                "collected_categories"
                            )
                            or boundary_infrastructure_metadata.get(
                                "resource_categories"
                            )
                        )
                        missing_boundary_categories = []
                        coverage_unknown = not isinstance(
                            boundary_categories,
                            list,
                        )
                        if not coverage_unknown:
                            missing_boundary_categories = sorted(
                                collection_resource_categories
                                - {
                                    str(category).upper()
                                    for category in boundary_categories
                                }
                            )
                        original_boundary_issue_count = (
                            boundary_infrastructure_metadata.get(
                                "collection_issue_count"
                            )
                        )
                        try:
                            original_boundary_issue_count = max(
                                0,
                                int(original_boundary_issue_count or 0),
                            )
                        except (TypeError, ValueError):
                            original_boundary_issue_count = 1
                        original_boundary_completeness = str(
                            boundary_infrastructure_metadata.get(
                                "inventory_completeness"
                            )
                            or "UNKNOWN"
                        ).upper()
                        coverage_issue_count = int(
                            coverage_unknown
                            or bool(missing_boundary_categories)
                        )
                        if coverage_unknown or missing_boundary_categories:
                            infrastructure_warnings.append({
                                "collector": (
                                    "InfrastructureSnapshotRepository"
                                ),
                                "stage": (
                                    "period_boundary_fallback_coverage"
                                ),
                                "target_type": "infrastructure",
                                "severity": "warning",
                                "code": (
                                    "SNAPSHOT_CATEGORY_COVERAGE_UNKNOWN"
                                    if coverage_unknown
                                    else (
                                        "SNAPSHOT_CATEGORY_COVERAGE_"
                                        "INCOMPLETE"
                                    )
                                ),
                                "missing_categories": (
                                    missing_boundary_categories
                                ),
                                "message": (
                                    "경계 대체 스냅샷이 현재 선택 범주의 "
                                    "전체 수집 범위를 충족하지 않습니다."
                                ),
                            })
                        collection_metadata["infrastructure"].update({
                            "inventory_completeness": (
                                "PARTIAL"
                                if (
                                    coverage_issue_count
                                    or original_boundary_issue_count
                                    or original_boundary_completeness
                                    not in {
                                        "COMPLETE_FOR_SELECTED_SCOPE",
                                        "COMPLETE_FOR_SNAPSHOT_SCOPE",
                                    }
                                )
                                else "COMPLETE_FOR_SNAPSHOT_SCOPE"
                            ),
                            "collection_issue_count": (
                                original_boundary_issue_count
                                + coverage_issue_count
                            ),
                        })
                else:
                    server_data = []
                    infrastructure_collected_data = []
                    server_raw_data = {}
                    collection_metadata["infrastructure"] = {
                        "source": "UNAVAILABLE",
                        "time_basis": "REPORT_PERIOD",
                        "period_start": period.get("start_dt"),
                        "period_end": period.get("end_dt"),
                        "inventory_completeness": "UNAVAILABLE",
                        "collection_issue_count": 1,
                        **self._snapshot_window_metadata(
                            self._snapshot_eligibility_window(
                                period,
                                completed_at,
                            )
                        ),
                    }

        infrastructure_data = [
            item for item in infrastructure_collected_data
            if str(item.get("category") or "").upper()
            in selected_resource_categories
        ]
        report_server_data = (
            server_data
            if (
                "SERVER" in selected_resource_categories
                or (
                    monitoring_enabled
                    and "SERVER" in selected_monitoring_categories
                )
            )
            else []
        )

        insight_data: List[Dict[str, Any]] = []
        insight_metric_errors: List[Dict[str, Any]] = []
        if (
            monitoring_enabled
            and "SERVER" in selected_monitoring_categories
        ):
            insight_data, insight_metric_errors = self.collect_insight_metrics(
                server_data=server_data,
                period=period,
            )

        infrastructure_metric_data: List[Dict[str, Any]] = []
        infrastructure_metric_errors: List[Dict[str, Any]] = []
        infrastructure_metric_warnings: List[Dict[str, Any]] = []
        if monitored_infrastructure_categories:
            monitoring_infrastructure = [
                item for item in infrastructure_collected_data
                if str(item.get("category") or "").upper()
                in monitored_infrastructure_categories
            ]
            (
                infrastructure_metric_data,
                infrastructure_metric_errors,
                infrastructure_metric_warnings,
            ) = self.collect_infrastructure_metrics(
                infrastructure=monitoring_infrastructure,
                start_time=period["start_time"],
                end_time=period["end_time"],
                categories=monitored_infrastructure_categories,
            )

        insight_events: List[Dict[str, Any]] = []
        insight_grouped_events: Dict[str, List[Dict[str, Any]]] = {}
        insight_event_errors: List[Dict[str, Any]] = []
        if report_options.section_enabled("insight_events"):
            (
                insight_events,
                insight_grouped_events,
                insight_event_errors,
            ) = self.collect_insight_events(period=period)

        activity_data: Dict[str, Any] = {}
        activity_errors: List[Dict[str, Any]] = []
        if report_options.section_enabled("activity_history"):
            activity_collector = ActivityTracerEventCollector(
                api_factory=self.api_factory
            )
            activity_data = activity_collector.collect(
                start_time=period["start_time"],
                end_time=period["end_time"],
            )
            activity_errors = list(
                getattr(activity_collector, "last_errors", [])
            )

        all_insight_errors = self._merge_error_lists(
            insight_metric_errors,
            insight_event_errors,
        )
        all_collection_errors = self._merge_error_lists(
            server_errors,
            infrastructure_errors,
            all_insight_errors,
            infrastructure_metric_errors,
            activity_errors,
        )
        all_collection_warnings = self._merge_error_lists(
            infrastructure_warnings,
            infrastructure_metric_warnings,
        )

        # Billing이 실패하더라도 먼저 완료된 수집 결과는 보존한다.
        self.print_server_metric_summary(
            insight_data,
            file_suffix=period["file_suffix"],
        )
        self.print_insight_event_summary(insight_events)
        self.print_insight_error_summary(
            all_insight_errors,
            file_suffix=period["file_suffix"],
        )
        self.save_json_file(
            data={
                "events": insight_events,
                "grouped_events": insight_grouped_events,
                "errors": insight_event_errors,
            },
            output_dir=self.output_dir,
            filename=f"cloud_insight_events_{period['file_suffix']}.json",
        )

        self.save_json_file(
            data=activity_data,
            output_dir=self.output_dir,
            filename=f"activity_tracer_events_{period['file_suffix']}.json",
        )

        self.save_json_file(
            data=activity_errors,
            output_dir=self.output_dir,
            filename=f"activity_tracer_errors_{period['file_suffix']}.json",
        )

        self.save_json_file(
            data=all_collection_errors,
            output_dir=self.output_dir,
            filename=f"collection_errors_{period['file_suffix']}.json",
        )

        self.save_json_file(
            data=infrastructure_data,
            output_dir=self.output_dir,
            filename=(
                f"infrastructure_inventory_{period['file_suffix']}.json"
            ),
        )
        self.save_json_file(
            data=infrastructure_metric_data,
            output_dir=self.output_dir,
            filename=(
                f"infrastructure_metrics_{period['file_suffix']}.json"
            ),
        )

        billing_result: Dict[str, Any] = {}
        billing_enabled = (
            report_options.section_enabled("billing")
            or report_options.section_enabled("organization_billing")
        )
        if billing_enabled:
            billing_collector = None
            billing_stage = "collection"

            try:
                organization_context = (
                    OrganizationCollector(
                        api_factory=self.api_factory
                    ).discover()
                    if report_options.section_enabled(
                        "organization_billing"
                    )
                    else {"scope": "SELF", "members": []}
                )
                billing_collector = BillingCollector(
                    api_factory=self.api_factory
                )
                billing_raw = billing_collector.collect_raw(
                    use_start_date=period["use_start_date"],
                    use_end_date=period["usage_query_end_date"],
                    demand_month=period["billing_month"],
                    region_code="KR",
                    pay_currency_code="KRW",
                    confirmed_demand_month=(
                        period["confirmed_demand_month"]
                    ),
                    month_to_date_start=period["month_to_date_start"],
                    month_to_date_end=period["month_to_date_end"],
                    organization_context=organization_context,
                )
                billing_errors = list(
                    getattr(billing_collector, "last_errors", [])
                )
                all_collection_errors = self._merge_error_lists(
                    all_collection_errors,
                    billing_errors,
                )
                all_collection_warnings = self._merge_error_lists(
                    all_collection_warnings,
                    getattr(billing_collector, "last_warnings", []),
                )
                self.save_json_file(
                    data=all_collection_errors,
                    output_dir=self.output_dir,
                    filename=(
                        f"collection_errors_{period['file_suffix']}.json"
                    ),
                )
                self.save_json_file(
                    data=billing_raw,
                    output_dir=self.output_dir,
                    filename=f"billing_raw_{period['file_suffix']}.json",
                )

                billing_stage = "normalization"
                billing_result = BillingNormalizer().normalize(
                    raw_data=billing_raw,
                    current_month=period["billing_month"],
                    billing_month=period["billing_month"],
                    use_end_date=period["use_end_date"],
                    comparison_enabled=bool(
                        period.get("is_closed_month", False)
                    ),
                    report_period=period,
                    calculated_at=period["calculated_at"],
                )
                self.save_json_file(
                    data=billing_result,
                    output_dir=self.output_dir,
                    filename=(
                        f"billing_result_{period['file_suffix']}.json"
                    ),
                )
            except Exception as exc:
                billing_failure = {
                    "collector": (
                        "BillingCollector"
                        if billing_stage == "collection"
                        else "BillingNormalizer"
                    ),
                    "stage": billing_stage,
                    "target_type": "billing",
                    "api": "platform",
                    "exception_type": type(exc).__name__,
                    "message": safe_exception_message(exc),
                }
                all_collection_errors = self._merge_error_lists(
                    all_collection_errors,
                    getattr(billing_collector, "last_errors", []),
                    [billing_failure],
                )
                self.save_json_file(
                    data=all_collection_errors,
                    output_dir=self.output_dir,
                    filename=(
                        f"collection_errors_{period['file_suffix']}.json"
                    ),
                )
                raise

            self.print_network_usage_summary(
                billing_result.get("network_usage_summary", [])
            )
            self.print_billing_summary(billing_result, period=period)
            self.print_usage_summary(
                billing_result.get("usage_summary", [])
            )

        infrastructure_topology: Dict[str, Any] = {}
        if diagram_enabled:
            infrastructure_topology = self._build_period_topology(
                period=period,
                infrastructure=self._dict_records(infrastructure_data),
                collection_metadata=collection_metadata,
                report_options=report_options,
            )

        report = ReportResult(
            period=period,
            customer=customer_snapshot,
            servers=self._dict_records(report_server_data),
            server_metrics=self._dict_records(insight_data),
            infrastructure=self._dict_records(
                infrastructure_collected_data
            ),
            infrastructure_metrics=self._dict_records(
                infrastructure_metric_data
            ),
            insight_events=self._dict_records(insight_events),
            grouped_insight_events=insight_grouped_events,
            activity_events=activity_data,
            billing=billing_result,
            report_options=report_options_snapshot,
            collection_metadata=collection_metadata,
            infrastructure_topology=infrastructure_topology,
            collection_errors=all_collection_errors,
            collection_warnings=all_collection_warnings,
        )
        report_json_path = self.save_json_file(
            data=report.to_dict(),
            output_dir=self.output_dir,
            filename=f"ncp_report_{period['file_suffix']}.json",
        )
        report_html_path = Path(self.output_dir) / (
            f"ncp_report_{period['file_suffix']}.html"
        )
        HtmlReportRenderer().write(
            report=report,
            path=report_html_path,
        )
        repository = getattr(self, "report_repository", None)
        if repository is not None:
            try:
                repository.save_report(
                    report,
                    artifacts={
                        "PUBLIC_JSON": report_json_path,
                        "HTML": report_html_path,
                    },
                )
            except Exception:
                if getattr(
                    getattr(repository, "settings", None),
                    "required",
                    True,
                ):
                    raise
                logging.getLogger(__name__).exception(
                    "보고서는 생성했지만 선택적 DB 저장에 실패했습니다."
                )
        return report

    def print_period_summary(self, period: Dict[str, Any]) -> None:
        print("\n" + "=" * 80)
        print("보고서 기준 기간")
        print("=" * 80)
        print(f"구분     : {period['period_type']}")
        print(f"시작일시 : {period['start_dt']}")
        print(f"종료일시 : {period['end_dt']}")
        print(f"청구월   : {period['billing_month']}")

    def collect_insight_metrics(
        self,
        server_data: List[Dict[str, Any]],
        period: Dict[str, Any],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        insight_collector = InsightMetricCollector(api_factory=self.api_factory)

        insight_result = insight_collector.collect(
            server_data,
            start_time=period["start_time"],
            end_time=period["end_time"],
        )

        if isinstance(insight_result, dict):
            insight_data = insight_result.get("metrics", [])
            insight_errors = insight_result.get("errors", [])
        else:
            insight_data = insight_result if isinstance(insight_result, list) else []
            insight_errors = []

        collector_errors = getattr(insight_collector, "last_errors", [])

        return insight_data, self._merge_error_lists(
            insight_errors,
            collector_errors,
        )

    def collect_infrastructure(
        self,
        servers: List[Dict[str, Any]],
        server_raw_data: Dict[str, Any],
        categories: Optional[set[str]] = None,
    ) -> tuple[
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
    ]:
        collector = None
        try:
            collector = InfrastructureCollector(api_factory=self.api_factory)
            normalized_categories = {
                str(category).upper() for category in (categories or set())
            }
            collect_kwargs: Dict[str, Any] = {
                "servers": servers,
                "server_raw_data": server_raw_data,
            }
            if categories is not None:
                collect_kwargs["categories"] = sorted(
                    normalized_categories
                )
            data = collector.collect(**collect_kwargs)
            normalized_data = self._dict_records(data)
            if normalized_categories:
                normalized_data = [
                    item for item in normalized_data
                    if str(item.get("category") or "").upper()
                    in normalized_categories
                ]
            return (
                normalized_data,
                self._dict_records(getattr(collector, "last_errors", [])),
                self._dict_records(getattr(collector, "last_warnings", [])),
            )
        except Exception as exc:
            failure = {
                "collector": "InfrastructureCollector",
                "stage": "collection",
                "target_type": "infrastructure",
                "api": "platform",
                "exception_type": type(exc).__name__,
                "message": safe_exception_message(exc),
            }
            return (
                [],
                self._merge_error_lists(
                    getattr(collector, "last_errors", []),
                    [failure],
                ),
                self._dict_records(
                    getattr(collector, "last_warnings", [])
                ),
            )

    def collect_infrastructure_metrics(
        self,
        infrastructure: List[Dict[str, Any]],
        start_time: int,
        end_time: int,
        categories: Optional[set[str]] = None,
    ) -> tuple[
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
    ]:
        collector = None
        try:
            collector = InfrastructureMetricCollector(
                api_factory=self.api_factory
            )
            normalized_categories = {
                str(category).upper() for category in (categories or set())
            }
            metric_infrastructure = (
                [
                    item for item in infrastructure
                    if str(item.get("category") or "").upper()
                    in normalized_categories
                ]
                if normalized_categories
                else infrastructure
            )
            data = collector.collect(
                infrastructure=metric_infrastructure,
                start_time=start_time,
                end_time=end_time,
                selected_categories=(
                    sorted(normalized_categories)
                    if categories is not None else None
                ),
            )
            return (
                self._dict_records(data),
                self._dict_records(getattr(collector, "last_errors", [])),
                self._dict_records(getattr(collector, "last_warnings", [])),
            )
        except Exception as exc:
            failure = {
                "collector": "InfrastructureMetricCollector",
                "stage": "collection",
                "target_type": "infrastructure_metric",
                "api": "cloud_insight",
                "exception_type": type(exc).__name__,
                "message": safe_exception_message(exc),
            }
            return (
                [],
                self._merge_error_lists(
                    getattr(collector, "last_errors", []),
                    [failure],
                ),
                self._dict_records(
                    getattr(collector, "last_warnings", [])
                ),
            )

    def collect_insight_events(
        self,
        period: Dict[str, Any],
    ) -> tuple[
        List[Dict[str, Any]],
        Dict[str, List[Dict[str, Any]]],
        List[Dict[str, Any]],
    ]:
        insight_event_collector = InsightEventCollector(api_factory=self.api_factory)

        insight_event_result = insight_event_collector.collect(
            start_time=period["start_time"],
            end_time=period["end_time"],
        )

        insight_events: List[Dict[str, Any]] = []
        insight_grouped_events: Dict[str, List[Dict[str, Any]]] = {}
        insight_event_errors: List[Dict[str, Any]] = []

        if isinstance(insight_event_result, list):
            insight_events = self._dict_records(insight_event_result)
        elif isinstance(insight_event_result, dict):
            is_envelope = (
                "grouped_events" in insight_event_result
                or isinstance(insight_event_result.get("events"), list)
            )

            if is_envelope:
                insight_events = self._dict_records(
                    insight_event_result.get("events", [])
                )
                insight_grouped_events = self._grouped_event_map(
                    insight_event_result.get("grouped_events", {})
                )
                insight_event_errors = self._dict_records(
                    insight_event_result.get("errors", [])
                )
            else:
                # InsightEventCollector의 기존 공개 계약은 그룹 맵이다.
                # 이를 그대로 수용하면서 보고서용 평탄 이벤트도 복원한다.
                insight_grouped_events = self._grouped_event_map(
                    insight_event_result
                )

        collector_events = self._dict_records(
            getattr(insight_event_collector, "last_events", [])
        )

        if not insight_events:
            insight_events = (
                collector_events
                or self._flatten_grouped_events(insight_grouped_events)
            )

        insight_events = sort_event_records(
            self._deduplicate_events(insight_events),
            ("event_time", "start_time", "time", "timestamp"),
        )

        if not insight_grouped_events and insight_events:
            normalizer = getattr(insight_event_collector, "normalizer", None)

            if normalizer is not None and hasattr(normalizer, "group_events"):
                insight_grouped_events = normalizer.group_events(insight_events)
            else:
                insight_grouped_events = self._fallback_group_events(
                    insight_events
                )

        insight_grouped_events = {
            group_key: sort_event_records(
                group_events,
                ("event_time", "start_time", "time", "timestamp"),
            )
            for group_key, group_events in insight_grouped_events.items()
        }

        insight_event_errors = self._merge_error_lists(
            insight_event_errors,
            getattr(insight_event_collector, "last_errors", []),
        )

        return insight_events, insight_grouped_events, insight_event_errors

    def _dict_records(self, value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []

        return [item for item in value if isinstance(item, dict)]

    def _grouped_event_map(
        self,
        value: Any,
    ) -> Dict[str, List[Dict[str, Any]]]:
        if not isinstance(value, dict):
            return {}

        result: Dict[str, List[Dict[str, Any]]] = {}

        for group_key, group_events in value.items():
            events = self._dict_records(group_events)

            if isinstance(group_events, list):
                result[str(group_key)] = events

        return result

    def _flatten_grouped_events(
        self,
        grouped_events: Dict[str, List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        events = []

        for group_events in grouped_events.values():
            events.extend(self._dict_records(group_events))

        return self._deduplicate_events(events)

    def _deduplicate_events(
        self,
        events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = []
        seen = set()

        for event in self._dict_records(events):
            event_id = (
                event.get("event_id")
                or event.get("eventId")
                or event.get("historyId")
                or event.get("id")
            )
            identity = (
                f"id:{event_id}"
                if event_id is not None and str(event_id).strip()
                else "row:" + json.dumps(
                    event,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
            )

            if identity in seen:
                continue

            seen.add(identity)
            result.append(event)

        return result

    def _fallback_group_events(
        self,
        events: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        result: Dict[str, List[Dict[str, Any]]] = {}

        for event in events:
            group_key = (
                event.get("resource_id")
                or event.get("resource_name")
                or event.get("prod_key")
                or "unknown"
            )
            result.setdefault(str(group_key), []).append(event)

        return result

    def _merge_error_lists(
        self,
        *error_lists: Any,
    ) -> List[Dict[str, Any]]:
        result = []
        seen = set()

        for error_list in error_lists:
            for error in self._dict_records(error_list):
                identity = json.dumps(
                    error,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )

                if identity in seen:
                    continue

                seen.add(identity)
                result.append(error)

        return result

    def print_server_metric_summary(
        self,
        insight_data: List[Dict[str, Any]],
        file_suffix: Optional[str] = None,
    ) -> None:
        print()
        print("=" * 80)
        print("서버 메트릭")
        print("=" * 80)

        if not insight_data:
            print("서버 메트릭 없음")

        summaries = []

        for item in insight_data or []:
            if not isinstance(item, dict):
                continue

            summary = {
                key: value
                for key, value in item.items()
                if key != "raw_metrics"
            }
            summaries.append(summary)

            os_fs_text = ", ".join(
                f"{fs.get('mount')}:min={fs.get('min')} avg={fs.get('avg')} max={fs.get('max')}%"
                for fs in (summary.get("os_fs_details") or [])
            )

            data_fs_text = ", ".join(
                f"{fs.get('mount')}:min={fs.get('min')} avg={fs.get('avg')} max={fs.get('max')}%"
                for fs in (summary.get("data_fs_details") or [])
            )

            print(
                f"{summary.get('server_name', '-'):<35} "
                f"CPU min={summary.get('cpu_min')} avg={summary.get('cpu_avg')} max={summary.get('cpu_max')} | "
                f"MEM min={summary.get('mem_min')} avg={summary.get('mem_avg')} max={summary.get('mem_max')} | "
                f"OS=[{os_fs_text}] | "
                f"DATA=[{data_fs_text}]"
            )

        self.save_json_file(
            data=summaries,
            output_dir=self.output_dir,
            filename=(
                f"server_metric_summary_{file_suffix}.json"
                if file_suffix
                else "server_metric_summary.json"
            ),
        )
        if file_suffix:
            self.save_json_file(
                data=summaries,
                output_dir=self.output_dir,
                filename="server_metric_summary.json",
            )

    def print_insight_event_summary(
        self,
        insight_events: List[Dict[str, Any]],
    ) -> None:
        print()
        print("=" * 80)
        print("Cloud Insight 이벤트")
        print("=" * 80)

        if not insight_events:
            print("Cloud Insight 이벤트 없음")
            return

        for event in insight_events:
            event_time = (
                event.get("event_time")
                or event.get("time")
                or event.get("timestamp")
                or event.get("start_time")
                or "-"
            )

            severity = (
                event.get("severity")
                or event.get("level")
                or event.get("event_level")
                or event.get("status")
                or "-"
            )

            resource = (
                event.get("resource_name")
                or event.get("resource_id")
                or event.get("target_name")
                or event.get("target_id")
                or event.get("nrn")
                or "-"
            )

            event_type = (
                event.get("event_type")
                or event.get("type")
                or event.get("rule_name")
                or event.get("metric")
                or "-"
            )

            message = (
                event.get("message")
                or event.get("description")
                or event.get("reason")
                or event.get("event_message")
                or "-"
            )

            print(
                f"{event_time} | "
                f"severity={severity} | "
                f"resource={resource} | "
                f"type={event_type} | "
                f"message={message}"
            )

    def print_insight_error_summary(
        self,
        insight_errors: List[Dict[str, Any]],
        file_suffix: Optional[str] = None,
    ) -> None:
        print()
        print("=" * 80)
        print("Cloud Insight 수집 오류")
        print("=" * 80)

        if not insight_errors:
            print("Cloud Insight 수집 오류 없음")

        for error in insight_errors or []:
            if not isinstance(error, dict):
                continue

            target = (
                error.get("target_name")
                or error.get("target_id")
                or error.get("resource_id")
                or "-"
            )

            print(
                f"[{error.get('collector', '-')}] "
                f"stage={error.get('stage', '-')} | "
                f"target_type={error.get('target_type', '-')} | "
                f"target={target} | "
                f"product_key={error.get('product_key', '-')} | "
                f"metric={error.get('metric', '-')} | "
                f"api={error.get('api', '-')} | "
                f"status={error.get('status_code', '-')} | "
                f"code={error.get('error_code', '-')} | "
                f"message={error.get('message', '-')}"
            )

        self.save_json_file(
            data=self._dict_records(insight_errors),
            output_dir=self.output_dir,
            filename=(
                f"cloud_insight_errors_{file_suffix}.json"
                if file_suffix
                else "cloud_insight_errors.json"
            ),
        )
        if file_suffix:
            self.save_json_file(
                data=self._dict_records(insight_errors),
                output_dir=self.output_dir,
                filename="cloud_insight_errors.json",
            )

    def print_network_usage_summary(
        self,
        network_usage_summary: List[Dict[str, Any]],
    ) -> None:
        print()
        print("=" * 80)
        print("네트워크 사용량")
        print("=" * 80)

        if not network_usage_summary:
            print("네트워크 사용량 없음")
            return

        for item in network_usage_summary:
            print(
                f"{item['service_name']:<35} "
                f"{item['direction']:<10} "
                f"{item['name']:<45} "
                f"{item['usage_gb']:>10,.3f} GB "
                f"({item['row_count']}건)"
            )

    def print_billing_summary(
        self,
        billing_result: Dict[str, Any],
        period: Optional[Dict[str, Any]] = None,
    ) -> None:
        summary = billing_result["summary"]
        use_estimated_cost = bool(
            period and period.get("is_closed_month") is False
        )

        if use_estimated_cost:
            title = "예상 비용 (미확정)"
            total = summary.get("expected_total_amount", 0)
            rows = [
                {
                    "service_name": row.get("service_name"),
                    "amount": row.get("expected_amount", 0),
                    "row_count": row.get("row_count", 0),
                }
                for row in billing_result.get("expected_by_service", [])
                if isinstance(row, dict)
            ]
        else:
            title = "확정 청구 금액"
            total = summary.get("confirmed_total_amount", 0)
            rows = billing_result.get("service_summary", [])

        print("\n" + "=" * 80)
        print(title)
        print("=" * 80)
        print(f"청구월 : {summary['billing_month']}")
        print(f"{title} : {total:,.0f} 원")
        print(f"청구 항목 수 : {summary.get('row_count', summary.get('service_count', 0))} 건")

        print("\n" + "=" * 80)
        print(f"서비스별 {title}")
        print("=" * 80)

        for service in rows:
            print(
                f"{service['service_name']:<35} "
                f"{service['amount']:>15,.0f} 원 "
                f"({service['row_count']}건)"
            )

    def print_usage_summary(
        self,
        usage_summary: List[Dict[str, Any]],
    ) -> None:
        print()
        print("=" * 80)
        print("서비스별 사용량")
        print("=" * 80)

        if not usage_summary:
            print("서비스별 사용량 없음")
            return

        for item in usage_summary:
            print(
                f"{item['service_name']:<35} "
                f"{item['item_name']:<45} "
                f"{item['usage_quantity']:>15,.3f} "
                f"{item['unit_code']} "
                f"({item['row_count']}건)"
            )

    def save_json_file(
        self,
        data: Any,
        output_dir: str,
        filename: str,
    ) -> Path:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        file_path = output_path / filename

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

        return file_path

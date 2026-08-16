from app.apifactory import APIFactory
from app.collection_diagnostics import normalize_collection_issue
from app.customer import CustomerProfile
from app.renderers import HtmlReportRenderer
from app.network_configuration import (
    build_generation_snapshot,
    configuration_records,
    replace_configuration_records,
    snapshot_categories,
)
from app.report_models import ReportResult
from app.report_analysis import analyze_report
from app.report_analysis.quality import monitoring_observation_count
from app.report_options import (
    NETWORK_CONFIGURATION_CATEGORY_OPTIONS,
    ReportOptions,
)
from app.report_pipeline import (
    NetworkConfigurationResult,
    ObservabilityResult,
    ReportCollectionPlan,
    ResourceCollectionResult,
    SnapshotDecision,
    build_collection_plan,
)
from app.report_period import (
    build_snapshot_eligibility_window,
    normalize_period_bounds,
    snapshot_window_metadata,
)
from collectors import (
    ServerCollector,
    InsightMetricCollector,
    ActivityTracerEventCollector,
    BillingCollector,
    InfrastructureCollector,
    InfrastructureMetricCollector,
    OrganizationCollector,
    SecurityMonitoringCollector,
    WMSCollector,
)
from collectors.insighteventcollector import InsightEventCollector
from normalizers.billingnormalizer import BillingNormalizer
from utils.common_rest import safe_exception_message
from utils.data_utils import get_unix_time_stamp
from utils.event_sort import event_timestamp_millis, sort_event_records

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

    @staticmethod
    def _operational_analysis_feature_enabled() -> bool:
        value = os.getenv("REPORT_OPERATIONAL_ANALYSIS_ENABLED")
        if value is None:
            return True
        return value.strip().casefold() in {"1", "true", "yes", "on"}

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
        # 기간 API는 밀리초 단위의 포함 종료값을 사용한다. 날짜형
        # 보고서의 마지막 999ms도 빠지지 않도록 다음 날 0시 직전으로
        # 계산하되, 사람이 읽는 종료 표시는 기존의 23:59:59를 유지한다.
        end_exclusive = datetime.combine(
            end + timedelta(days=1),
            datetime.min.time(),
            tzinfo=self.KST,
        )
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
            "end_time": int(end_exclusive.timestamp() * 1000) - 1,
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

    def _now_kst_iso(self) -> str:
        return datetime.now(self.KST).isoformat(timespec="microseconds")

    def _period_bounds_kst(
        self,
        period: Dict[str, Any],
    ) -> tuple[datetime, datetime]:
        """KST 보고 기간을 표준 ``[start, end)`` 경계로 반환한다."""
        period_start = self._parse_kst_datetime(period["start_dt"])
        period_end = self._parse_kst_datetime(period["end_dt"])
        return normalize_period_bounds(
            period_start,
            period_end,
            end_exclusive=bool(period.get("end_exclusive")),
        )

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
        return build_snapshot_eligibility_window(
            period_start,
            period_end,
            requested_reference,
        )

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

    def _filter_current_infrastructure_for_period(
        self,
        resources: List[Dict[str, Any]],
        period: Dict[str, Any],
    ) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
        """Infer historical presence from creation time for current resources.

        This fallback can safely exclude resources created after the requested
        report period. It intentionally retains resources with an unknown
        creation time because dropping them would hide potentially valid
        historical infrastructure.
        """
        _, period_end = self._period_bounds_kst(period)
        period_end_ms = int(period_end.timestamp() * 1000)
        filtered: List[Dict[str, Any]] = []
        stats = {
            "input_count": 0,
            "included_count": 0,
            "excluded_after_period_count": 0,
            "unknown_create_time_count": 0,
        }

        for resource in self._dict_records(resources):
            stats["input_count"] += 1
            create_value = resource.get("create_time")
            create_time = event_timestamp_millis(create_value)
            if create_time is not None and create_time >= period_end_ms:
                stats["excluded_after_period_count"] += 1
                continue

            normalized = dict(resource)
            details = normalized.get("details")
            details = dict(details) if isinstance(details, dict) else {}
            if create_time is None:
                stats["unknown_create_time_count"] += 1
                details["historical_presence_confidence"] = "UNKNOWN"
            else:
                details["historical_presence_confidence"] = (
                    "INFERRED_FROM_CREATE_TIME"
                )
                details["historical_presence_basis"] = (
                    "RESOURCE_MANAGER_OR_SERVICE_API_CREATE_TIME"
                )
            normalized["details"] = details
            filtered.append(normalized)
            stats["included_count"] += 1

        return filtered, stats

    def _filter_current_servers_for_period(
        self,
        servers: List[Dict[str, Any]],
        infrastructure: List[Dict[str, Any]],
        period: Dict[str, Any],
    ) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
        """Apply the same creation-time inference to the server detail list."""
        _, period_end = self._period_bounds_kst(period)
        period_end_ms = int(period_end.timestamp() * 1000)
        infrastructure_servers = {
            str(resource.get("resource_id")): resource
            for resource in self._dict_records(infrastructure)
            if (
                str(resource.get("category") or "").upper() == "SERVER"
                and resource.get("resource_id") is not None
            )
        }
        filtered: List[Dict[str, Any]] = []
        stats = {
            "input_count": 0,
            "included_count": 0,
            "excluded_after_period_count": 0,
            "unknown_create_time_count": 0,
        }

        for server in self._dict_records(servers):
            stats["input_count"] += 1
            server_id = str(server.get("server_id") or "")
            infrastructure_server = infrastructure_servers.get(server_id, {})
            create_value = infrastructure_server.get("create_time")
            if create_value in (None, ""):
                create_value = server.get("create_date")
            if create_value in (None, ""):
                raw_server = server.get("raw_server")
                if isinstance(raw_server, dict):
                    create_value = raw_server.get("createDate")

            create_time = event_timestamp_millis(create_value)
            if create_time is not None and create_time >= period_end_ms:
                stats["excluded_after_period_count"] += 1
                continue

            normalized = dict(server)
            if create_value is not None:
                normalized["create_date"] = create_value
            infrastructure_details = infrastructure_server.get("details")
            if isinstance(infrastructure_details, dict):
                create_time_source = infrastructure_details.get(
                    "create_time_source"
                )
                if create_time_source:
                    normalized["create_time_source"] = create_time_source
            if create_time is None:
                stats["unknown_create_time_count"] += 1
                normalized["historical_presence_confidence"] = "UNKNOWN"
            else:
                normalized["historical_presence_confidence"] = (
                    "INFERRED_FROM_CREATE_TIME"
                )
            filtered.append(normalized)
            stats["included_count"] += 1

        return filtered, stats

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

    def _load_period_network_configuration_snapshot(
        self,
        *,
        period: Dict[str, Any],
        customer: Dict[str, Any],
        reference_at: str,
        requested_categories: set[str],
    ) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """보고 기간 안에 실제로 관측된 전용 네트워크 스냅샷을 찾는다."""
        repository = getattr(self, "report_repository", None)
        loader = getattr(
            repository,
            "load_period_network_configuration_snapshot",
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
                "collector": "NetworkConfigurationSnapshotRepository",
                "stage": "historical_snapshot_lookup",
                "target_type": "network_configuration",
                "api": "postgresql",
                "severity": "warning",
                "exception_type": type(exc).__name__,
                "message": safe_exception_message(exc),
            }
        if not isinstance(snapshot, dict):
            return None, None

        captured_at = snapshot.get("captured_at")
        if not self._snapshot_observed_in_window(
            period,
            captured_at,
            reference_at,
        ):
            return None, {
                "collector": "NetworkConfigurationSnapshotRepository",
                "stage": "historical_snapshot_validation",
                "target_type": "network_configuration",
                "severity": "warning",
                "code": "NETWORK_SNAPSHOT_OUTSIDE_REPORT_PERIOD",
                "message": (
                    "저장된 네트워크 구성의 실제 수집 시각이 보고 기간 밖이어서 "
                    "기간 데이터로 사용하지 않았습니다."
                ),
            }

        missing_categories = requested_categories - set(
            snapshot_categories(snapshot)
        )
        if missing_categories:
            return None, {
                "collector": "NetworkConfigurationSnapshotRepository",
                "stage": "historical_snapshot_coverage",
                "target_type": "network_configuration",
                "severity": "warning",
                "code": "NETWORK_SNAPSHOT_CATEGORY_COVERAGE_INCOMPLETE",
                "message": (
                    "보고 기간의 네트워크 구성 스냅샷에 요청 범주가 모두 "
                    f"포함되지 않았습니다: {', '.join(sorted(missing_categories))}"
                ),
            }
        return snapshot, None

    def _resolve_network_configuration(
        self,
        *,
        period: Dict[str, Any],
        collection_plan: ReportCollectionPlan,
        customer_snapshot: Dict[str, Any],
        resource_result: ResourceCollectionResult,
    ) -> NetworkConfigurationResult:
        """기간 스냅샷과 생성시점 백업을 혼동하지 않도록 분리한다."""
        requested_categories = set(
            collection_plan.selected_resource_categories
        ) & set(NETWORK_CONFIGURATION_CATEGORY_OPTIONS)
        if (
            not collection_plan.report_options.section_enabled(
                "infrastructure_inventory"
            )
            or not requested_categories
        ):
            return NetworkConfigurationResult()

        infrastructure_metadata = resource_result.collection_metadata.get(
            "infrastructure"
        )
        if not isinstance(infrastructure_metadata, dict):
            infrastructure_metadata = {}
        collected_categories = {
            str(category).upper()
            for category in (
                infrastructure_metadata.get("collected_categories") or []
            )
        }
        can_reuse_live_collection = bool(
            infrastructure_metadata.get("source") == "LIVE_API_COLLECTION"
            and requested_categories <= collected_categories
        )

        generation_errors: List[Dict[str, Any]] = []
        generation_warnings: List[Dict[str, Any]] = []
        if can_reuse_live_collection:
            generation_configuration = configuration_records(
                resource_result.infrastructure,
                requested_categories,
            )
            captured_at = str(
                infrastructure_metadata.get("completed_at")
                or infrastructure_metadata.get("started_at")
                or self._now_kst_iso()
            )
            collection_source = "LIVE_INFRASTRUCTURE_COLLECTION"
        else:
            (
                generation_configuration,
                generation_errors,
                generation_warnings,
            ) = self.collect_infrastructure(
                servers=[],
                server_raw_data={},
                categories=requested_categories,
            )
            captured_at = self._now_kst_iso()
            collection_source = "DEDICATED_NETWORK_API_COLLECTION"

        generation_snapshot = build_generation_snapshot(
            configuration=generation_configuration,
            selected_categories=requested_categories,
            captured_at=captured_at,
            collection_source=collection_source,
            errors=generation_errors,
            warnings=generation_warnings,
        )

        captured_in_report_period = self._period_contains_timestamp(
            period,
            captured_at,
        )
        period_snapshot: Optional[Dict[str, Any]] = None
        lookup_warning: Optional[Dict[str, Any]] = None
        if not captured_in_report_period:
            period_snapshot, lookup_warning = (
                self._load_period_network_configuration_snapshot(
                    period=period,
                    customer=customer_snapshot,
                    reference_at=captured_at,
                    requested_categories=requested_categories,
                )
            )

        warnings = list(generation_warnings)
        if lookup_warning:
            warnings.append(lookup_warning)

        if period_snapshot is not None:
            display_configuration = configuration_records(
                period_snapshot.get("configuration"),
                requested_categories,
            )
            display_captured_at = str(period_snapshot.get("captured_at") or "")
            snapshot_reference = period_snapshot.get("_snapshot_reference")
            if not isinstance(snapshot_reference, dict):
                snapshot_reference = {}
            display_source = "STORED_NETWORK_CONFIGURATION_SNAPSHOT"
            source_report_run_id = snapshot_reference.get("report_run_id")
            time_basis = "POINT_IN_TIME_WITHIN_REPORT_PERIOD"
            is_report_period_snapshot = True
            display_completeness = period_snapshot.get(
                "collection_completeness"
            )
            display_issue_count = period_snapshot.get(
                "collection_issue_count",
                0,
            )
        else:
            display_configuration = configuration_records(
                generation_configuration,
                requested_categories,
            )
            display_captured_at = captured_at
            display_source = "REPORT_GENERATION_SNAPSHOT"
            source_report_run_id = None
            is_report_period_snapshot = captured_in_report_period
            time_basis = (
                "POINT_IN_TIME_WITHIN_REPORT_PERIOD"
                if captured_in_report_period
                else "REPORT_GENERATION_TIME_NOT_REPORT_PERIOD"
            )
            display_completeness = generation_snapshot.get(
                "collection_completeness"
            )
            display_issue_count = generation_snapshot.get(
                "collection_issue_count",
                0,
            )
            if not captured_in_report_period:
                warnings.append({
                    "collector": "NetworkConfigurationSnapshotRepository",
                    "stage": "historical_snapshot_lookup",
                    "target_type": "network_configuration",
                    "severity": "warning",
                    "code": "NETWORK_PERIOD_SNAPSHOT_UNAVAILABLE",
                    "message": (
                        "보고 기간 안에 수집된 Route Table·ACG·Network ACL "
                        "스냅샷이 없어, 보고서 생성 과정에서 백업한 현재 구성을 "
                        "기간 데이터와 구분해 표시합니다."
                    ),
                })

        metadata = {
            "source": display_source,
            "time_basis": time_basis,
            "captured_at": display_captured_at,
            "capture_trigger": "REPORT_GENERATION",
            "is_point_in_time_snapshot": True,
            "is_report_period_snapshot": is_report_period_snapshot,
            "report_period_start": period.get("start_dt"),
            "report_period_end": period.get("end_dt"),
            "selected_categories": sorted(requested_categories),
            "source_report_run_id": source_report_run_id,
            "backup_captured_at": captured_at,
            "backup_storage": "DEDICATED_NETWORK_CONFIGURATION_SNAPSHOT",
            "collection_source": generation_snapshot.get(
                "collection_source"
            ),
            "collection_completeness": display_completeness,
            "collection_issue_count": display_issue_count,
            "backup_collection_completeness": generation_snapshot.get(
                "collection_completeness"
            ),
            "backup_collection_issue_count": generation_snapshot.get(
                "collection_issue_count"
            ),
        }
        return NetworkConfigurationResult(
            display_configuration=display_configuration,
            generation_snapshot=generation_snapshot,
            metadata=metadata,
            errors=generation_errors,
            warnings=warnings,
        )

    def _resolve_snapshot_decision(
        self,
        *,
        period: Dict[str, Any],
        collection_plan: ReportCollectionPlan,
        customer_snapshot: Dict[str, Any],
    ) -> SnapshotDecision:
        """보고 기간에 저장 스냅샷과 현재 수집 중 무엇을 쓸지 결정한다."""
        observation_check_at = self._now_kst_iso()
        request_window = self._snapshot_eligibility_window(
            period,
            observation_check_at,
        )
        live_snapshot_in_period = self._period_contains_timestamp(
            period,
            observation_check_at,
        )
        _, report_period_end = self._period_bounds_kst(period)
        observation_after_period = (
            self._parse_kst_datetime(observation_check_at)
            >= report_period_end
        )

        period_snapshot = None
        lookup_warning = None
        if (
            collection_plan.needs_resource_snapshot
            and not live_snapshot_in_period
        ):
            period_snapshot, lookup_warning = (
                self._load_period_infrastructure_snapshot(
                    period,
                    customer_snapshot,
                    observation_check_at,
                )
            )

        # 과거 스냅샷이 없을 때만 생성 시각 기반의 보수적 보완을 허용한다.
        current_state_period_fallback = bool(
            collection_plan.needs_resource_snapshot
            and not live_snapshot_in_period
            and observation_after_period
            and period_snapshot is None
        )
        needs_server_collection = (
            period_snapshot is None
            and (live_snapshot_in_period or current_state_period_fallback)
            and "SERVER" in collection_plan.collection_resource_categories
        )
        return SnapshotDecision(
            observation_check_at=observation_check_at,
            request_window=request_window,
            live_snapshot_in_period=live_snapshot_in_period,
            current_state_period_fallback=current_state_period_fallback,
            period_snapshot=period_snapshot,
            lookup_warning=lookup_warning,
            needs_server_collection=needs_server_collection,
        )

    def _stored_snapshot_result(
        self,
        *,
        period: Dict[str, Any],
        snapshot: Dict[str, Any],
        observation_check_at: str,
        requested_categories: set[str] | frozenset[str],
        initial_warnings: List[Dict[str, Any]],
    ) -> ResourceCollectionResult:
        """저장된 보고서 스냅샷을 현재 실행의 수집 결과 형식으로 복원한다."""
        result = ResourceCollectionResult(
            servers=self._dict_records(snapshot.get("servers")),
            infrastructure=self._dict_records(snapshot.get("infrastructure")),
            infrastructure_warnings=list(initial_warnings),
        )
        snapshot_options = snapshot.get("report_options")
        snapshot_categories: Optional[set[str]] = None
        if isinstance(snapshot_options, dict):
            snapshot_categories = set(
                ReportOptions.from_value(snapshot_options).to_dict()[
                    "resource_categories"
                ]
            )

        snapshot_metadata = snapshot.get("collection_metadata")
        infrastructure_metadata = (
            snapshot_metadata.get("infrastructure")
            if isinstance(snapshot_metadata, dict)
            else None
        )
        if not isinstance(infrastructure_metadata, dict):
            infrastructure_metadata = {}
        metadata_categories = (
            infrastructure_metadata.get("collected_categories")
            or infrastructure_metadata.get("resource_categories")
        )
        if isinstance(metadata_categories, list):
            snapshot_categories = {
                str(category).upper() for category in metadata_categories
            }

        snapshot_reference = snapshot.get("_snapshot_reference")
        if not isinstance(snapshot_reference, dict):
            snapshot_reference = {}
        stored_observed_at = (
            infrastructure_metadata.get("completed_at")
            or infrastructure_metadata.get("started_at")
            or snapshot_reference.get("observed_at")
        )
        stored_reference_at = (
            snapshot_reference.get("reference_at") or observation_check_at
        )
        stored_window = self._snapshot_eligibility_window(
            period,
            stored_reference_at,
        )
        try:
            parsed_observed_at = self._parse_kst_datetime(
                str(stored_observed_at)
            )
        except (TypeError, ValueError):
            parsed_observed_at = None
        result.collection_metadata["infrastructure"] = {
            **infrastructure_metadata,
            "completed_at": stored_observed_at,
            "source": "STORED_REPORT_SNAPSHOT",
            "time_basis": "REPORT_PERIOD",
            "source_report_run_id": snapshot_reference.get("report_run_id"),
            **snapshot_window_metadata(
                stored_window,
                parsed_observed_at,
            ),
        }

        original_issue_count = infrastructure_metadata.get(
            "collection_issue_count"
        )
        try:
            original_issue_count = max(0, int(original_issue_count or 0))
        except (TypeError, ValueError):
            original_issue_count = 1
        original_completeness = str(
            infrastructure_metadata.get("inventory_completeness") or "UNKNOWN"
        ).upper()

        if snapshot_categories is None:
            result.infrastructure_warnings.append({
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
            result.collection_metadata["infrastructure"].update({
                "inventory_completeness": "PARTIAL",
                "collection_issue_count": original_issue_count + 1,
            })
            return result

        missing_categories = sorted(
            requested_categories - snapshot_categories
        )
        if missing_categories:
            result.infrastructure_warnings.append({
                "collector": "InfrastructureSnapshotRepository",
                "stage": "historical_snapshot_coverage",
                "target_type": "infrastructure",
                "severity": "warning",
                "code": "SNAPSHOT_CATEGORY_COVERAGE_INCOMPLETE",
                "missing_categories": missing_categories,
                "message": (
                    "저장된 과거 스냅샷이 현재 선택한 일부 자원 범주를 "
                    "수집하지 않아 자원 목록과 모니터링 대상에서 제외했습니다."
                ),
            })
        result.collection_metadata["infrastructure"].update({
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
                original_issue_count + int(bool(missing_categories))
            ),
        })
        return result

    def _unavailable_snapshot_result(
        self,
        *,
        period: Dict[str, Any],
        decision: SnapshotDecision,
        initial_warnings: List[Dict[str, Any]],
    ) -> ResourceCollectionResult:
        """보고 기간의 스냅샷을 확보하지 못한 상태를 명시적으로 만든다."""
        warnings = [*initial_warnings, {
            "collector": "InfrastructureCollector",
            "stage": "historical_snapshot_lookup",
            "target_type": "infrastructure",
            "severity": "warning",
            "code": "PERIOD_SNAPSHOT_UNAVAILABLE",
            "message": (
                "보고 기간이 아직 시작되지 않아 현재 상태로 "
                "대체하지 않았습니다."
            ),
        }]
        return ResourceCollectionResult(
            infrastructure_warnings=warnings,
            collection_metadata={
                "infrastructure": {
                    "source": "UNAVAILABLE",
                    "time_basis": "REPORT_PERIOD",
                    "period_start": period.get("start_dt"),
                    "period_end": period.get("end_dt"),
                    "inventory_completeness": "UNAVAILABLE",
                    "collection_issue_count": 1,
                    **snapshot_window_metadata(
                        decision.request_window
                    ),
                }
            },
        )

    def _collect_observability(
        self,
        *,
        period: Dict[str, Any],
        report_options: ReportOptions,
        server_data: List[Dict[str, Any]],
        infrastructure_data: List[Dict[str, Any]],
        monitoring_enabled: bool,
        selected_monitoring_categories: set[str] | frozenset[str],
        monitored_infrastructure_categories: set[str] | frozenset[str],
        base_errors: List[List[Dict[str, Any]]],
        base_warnings: List[List[Dict[str, Any]]],
    ) -> ObservabilityResult:
        """메트릭과 이벤트 수집을 한 단계로 실행하고 오류를 병합한다."""
        server_metrics: List[Dict[str, Any]] = []
        server_metric_errors: List[Dict[str, Any]] = []
        if monitoring_enabled and "SERVER" in selected_monitoring_categories:
            server_metrics, server_metric_errors = (
                self.collect_insight_metrics(
                    server_data=server_data,
                    period=period,
                )
            )

        infrastructure_metrics: List[Dict[str, Any]] = []
        infrastructure_metric_errors: List[Dict[str, Any]] = []
        infrastructure_metric_warnings: List[Dict[str, Any]] = []
        if monitored_infrastructure_categories:
            metric_resource_categories = set(
                monitored_infrastructure_categories
            )
            if "LOAD_BALANCER" in metric_resource_categories:
                metric_resource_categories.add("TARGET_GROUP")
            monitoring_infrastructure = [
                item for item in infrastructure_data
                if str(item.get("category") or "").upper()
                in metric_resource_categories
            ]
            (
                infrastructure_metrics,
                infrastructure_metric_errors,
                infrastructure_metric_warnings,
            ) = self.collect_infrastructure_metrics(
                infrastructure=monitoring_infrastructure,
                start_time=period["start_time"],
                end_time=period["end_time"],
                categories=monitored_infrastructure_categories,
            )

        insight_events: List[Dict[str, Any]] = []
        grouped_insight_events: Dict[str, List[Dict[str, Any]]] = {}
        insight_event_errors: List[Dict[str, Any]] = []
        if report_options.section_enabled("insight_events"):
            (
                insight_events,
                grouped_insight_events,
                insight_event_errors,
            ) = self.collect_insight_events(period=period)

        activity_events: Dict[str, Any] = {}
        activity_errors: List[Dict[str, Any]] = []
        if report_options.section_enabled("activity_history"):
            activity_collector = ActivityTracerEventCollector(
                api_factory=self.api_factory
            )
            activity_events = activity_collector.collect(
                start_time=period["start_time"],
                end_time=period["end_time"],
            )
            activity_errors = list(
                getattr(activity_collector, "last_errors", [])
            )

        service_availability: Dict[str, Any] = {}
        security_monitoring: Dict[str, Any] = {}
        dataset_statuses: List[Dict[str, Any]] = []
        operational_source_errors: List[Dict[str, Any]] = []
        if (
            self._operational_analysis_feature_enabled()
            and report_options.analysis_enabled()
        ):
            if report_options.analysis_collector_enabled("wms"):
                wms_collector = WMSCollector(api_factory=self.api_factory)
                aggregation = self._wms_aggregation(period)
                scenarios = wms_collector.collect(
                    start_time=period["start_time"],
                    end_time=period["end_time"],
                    aggregation=aggregation,
                )
                wms_errors = list(wms_collector.last_errors)
                observation_count = self._wms_observation_count(scenarios)
                operational_source_errors.extend(wms_errors)
                service_availability = {
                    "source": "NCP_WMS",
                    "status": wms_collector.last_dataset_status,
                    "aggregation": aggregation,
                    "scenarios": scenarios,
                    "observation_count": observation_count,
                    "error_count": len(wms_errors),
                }
                dataset_statuses.append({
                    "key": "service_availability",
                    "label": "서비스 가용성(WMS)",
                    "status": wms_collector.last_dataset_status,
                    "record_count": observation_count,
                    "error_count": len(wms_errors),
                    "source": "NCP_WMS",
                })
            else:
                dataset_statuses.append({
                    "key": "service_availability",
                    "label": "서비스 가용성(WMS)",
                    "status": "NOT_REQUESTED",
                    "record_count": 0,
                    "error_count": 0,
                    "reason": "고객 보고서 설정에서 수집하지 않도록 지정했습니다.",
                })

            if report_options.analysis_collector_enabled(
                "security_monitoring"
            ):
                security_collector = SecurityMonitoringCollector(
                    api_factory=self.api_factory
                )
                security_events = security_collector.collect(
                    start_time=period["start_time"],
                    end_time=period["end_time"],
                )
                security_errors = list(security_collector.last_errors)
                operational_source_errors.extend(security_errors)
                security_monitoring = {
                    "source": "NCP_SECURITY_MONITORING",
                    "scope": "VPC",
                    "status": security_collector.last_dataset_status,
                    "service_statuses": dict(
                        security_collector.last_service_statuses
                    ),
                    "events": security_events,
                    "error_count": len(security_errors),
                }
                dataset_statuses.append({
                    "key": "security_events",
                    "label": "Security Monitoring(VPC)",
                    "status": security_collector.last_dataset_status,
                    "record_count": len(security_events),
                    "error_count": len(security_errors),
                    "source": "NCP_SECURITY_MONITORING",
                    "scope": "VPC",
                    "service_statuses": dict(
                        security_collector.last_service_statuses
                    ),
                })
            else:
                dataset_statuses.append({
                    "key": "security_events",
                    "label": "Security Monitoring(VPC)",
                    "status": "NOT_REQUESTED",
                    "record_count": 0,
                    "error_count": 0,
                    "reason": "고객 보고서 설정에서 수집하지 않도록 지정했습니다.",
                })

        insight_errors = self._merge_error_lists(
            server_metric_errors,
            insight_event_errors,
        )
        return ObservabilityResult(
            server_metrics=server_metrics,
            infrastructure_metrics=infrastructure_metrics,
            insight_events=insight_events,
            grouped_insight_events=grouped_insight_events,
            activity_events=activity_events,
            service_availability=service_availability,
            security_monitoring=security_monitoring,
            dataset_statuses=dataset_statuses,
            activity_errors=activity_errors,
            insight_event_errors=insight_event_errors,
            insight_errors=insight_errors,
            errors=self._merge_error_lists(
                *base_errors,
                insight_errors,
                infrastructure_metric_errors,
                activity_errors,
                operational_source_errors,
            ),
            warnings=self._merge_error_lists(
                *base_warnings,
                infrastructure_metric_warnings,
            ),
        )

    @staticmethod
    def _wms_aggregation(period: Dict[str, Any]) -> str:
        try:
            duration_ms = int(period["end_time"]) - int(period["start_time"])
        except (KeyError, TypeError, ValueError):
            return "MIN5"
        duration_days = max(duration_ms, 0) / 86_400_000
        if duration_days > 7:
            return "HOUR2"
        if duration_days > 2:
            return "MIN30"
        return "MIN5"

    def _load_analysis_baseline(
        self,
        *,
        period: Dict[str, Any],
        customer: Dict[str, Any],
    ) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        repository = getattr(self, "report_repository", None)
        loader = getattr(repository, "load_previous_report_snapshot", None)
        if not callable(loader):
            return None, None
        try:
            return loader(period, customer), None
        except Exception as exc:
            return None, {
                "collector": "OperationalAnalysis",
                "stage": "comparison_baseline",
                "target_type": "previous_report",
                "api": "PostgreSQL/report_snapshots",
                "exception_type": type(exc).__name__,
                "message": (
                    "이전 보고서 비교 기준을 불러오지 못해 현재 기간만 "
                    "분석했습니다."
                ),
            }

    @staticmethod
    def _wms_observation_count(
        scenarios: List[Dict[str, Any]],
    ) -> int:
        count = 0
        for scenario in scenarios:
            if not isinstance(scenario, dict):
                continue
            raw_total = scenario.get("total_count")
            try:
                count += (
                    max(int(raw_total), 0)
                    if raw_total is not None
                    else len(scenario.get("results") or [])
                )
            except (TypeError, ValueError):
                count += len(scenario.get("results") or [])
        return count

    @staticmethod
    def _dataset_status_entry(
        *,
        key: str,
        label: str,
        requested: bool,
        record_count: int,
        errors: List[Dict[str, Any]],
        warnings: Optional[List[Dict[str, Any]]] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        warnings = warnings or []
        if not requested:
            status = "NOT_REQUESTED"
            reason = "고객 보고서 설정에서 수집하지 않도록 지정했습니다."
        elif errors and record_count:
            status = "PARTIAL"
            reason = "일부 결과는 수집했으나 관련 오류가 있습니다."
        elif errors:
            status = "FAILED"
            reason = "관련 수집 오류로 사용할 수 있는 결과가 없습니다."
        elif warnings:
            status = "PARTIAL"
            reason = "수집 결과는 있으나 범위 또는 최신성 경고가 있습니다."
        elif record_count:
            status = "COLLECTED"
            reason = "요청한 범위의 수집 결과가 있습니다."
        else:
            status = "COLLECTED_EMPTY"
            reason = "수집은 완료되었으나 결과가 0건입니다."
        return {
            "key": key,
            "label": label,
            "status": status,
            "record_count": max(int(record_count), 0),
            "error_count": len(errors),
            "warning_count": len(warnings),
            "reason": reason,
            **({"source": source} if source else {}),
        }

    @staticmethod
    def _grouped_record_count(value: Any) -> int:
        if isinstance(value, list):
            return sum(isinstance(item, dict) for item in value)
        if isinstance(value, dict):
            return sum(
                ReportRunner._grouped_record_count(item)
                for item in value.values()
            )
        return 0

    @staticmethod
    def _issues_matching(
        issues: List[Dict[str, Any]], *tokens: str
    ) -> List[Dict[str, Any]]:
        normalized_tokens = tuple(token.casefold() for token in tokens)
        result = []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            haystack = " ".join(
                str(issue.get(name) or "").casefold()
                for name in (
                    "collector", "stage", "target_type", "api", "service_name"
                )
            )
            if any(token in haystack for token in normalized_tokens):
                result.append(issue)
        return result

    @staticmethod
    def _billing_available_fact_count(billing: Dict[str, Any]) -> int:
        count = 0
        for name in (
            "invoice_summary",
            "period_estimate",
            "month_to_date_estimate",
            "month_end_projection",
        ):
            fact = billing.get(name)
            if isinstance(fact, dict) and fact.get("status") == "AVAILABLE":
                count += 1
        return count

    def _write_prebilling_artifacts(
        self,
        *,
        period: Dict[str, Any],
        observability: ObservabilityResult,
        infrastructure: List[Dict[str, Any]],
    ) -> None:
        """과금 단계와 무관하게 완료된 수집 산출물을 먼저 보존한다.

        Billing API가 실패해도 서버·인프라·이벤트 수집 결과는 진단에
        필요하므로 이 저장 단계는 과금 수집보다 반드시 먼저 실행한다.
        """
        file_suffix = period["file_suffix"]
        network_categories = set(NETWORK_CONFIGURATION_CATEGORY_OPTIONS)
        self.print_server_metric_summary(
            observability.server_metrics,
            file_suffix=file_suffix,
        )
        self.print_insight_event_summary(observability.insight_events)
        self.print_insight_error_summary(
            observability.insight_errors,
            file_suffix=file_suffix,
        )
        self.save_json_file(
            data={
                "events": observability.insight_events,
                "grouped_events": observability.grouped_insight_events,
                "errors": observability.insight_event_errors,
            },
            output_dir=self.output_dir,
            filename=f"cloud_insight_events_{file_suffix}.json",
        )
        self.save_json_file(
            data=observability.activity_events,
            output_dir=self.output_dir,
            filename=f"activity_tracer_events_{file_suffix}.json",
        )
        self.save_json_file(
            data=observability.errors,
            output_dir=self.output_dir,
            filename=f"collection_errors_{file_suffix}.json",
        )
        self.save_json_file(
            data=[
                resource
                for resource in infrastructure
                if str(resource.get("category") or "").upper()
                not in network_categories
            ],
            output_dir=self.output_dir,
            filename=f"infrastructure_inventory_{file_suffix}.json",
        )
        self.save_json_file(
            data=observability.infrastructure_metrics,
            output_dir=self.output_dir,
            filename=f"infrastructure_metrics_{file_suffix}.json",
        )

        # 기존 진단 파일 계약상 Activity 오류는 병합 파일과 별도로도 남긴다.
        self.save_json_file(
            data=observability.activity_errors,
            output_dir=self.output_dir,
            filename=f"activity_tracer_errors_{file_suffix}.json",
        )

    def _collect_billing(
        self,
        *,
        period: Dict[str, Any],
        report_options: ReportOptions,
        collection_errors: List[Dict[str, Any]],
        collection_warnings: List[Dict[str, Any]],
    ) -> tuple[
        Dict[str, Any],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
    ]:
        """Organization 범위를 포함한 과금 수집과 정규화를 실행한다."""
        billing_enabled = (
            report_options.section_enabled("billing")
            or report_options.section_enabled("organization_billing")
        )
        if not billing_enabled:
            return {}, collection_errors, collection_warnings

        billing_collector = None
        billing_stage = "collection"
        try:
            organization_context = (
                OrganizationCollector(api_factory=self.api_factory).discover()
                if report_options.section_enabled("organization_billing")
                else {"scope": "SELF", "members": []}
            )
            billing_collector = BillingCollector(api_factory=self.api_factory)
            billing_raw = billing_collector.collect_raw(
                use_start_date=period["use_start_date"],
                use_end_date=period["usage_query_end_date"],
                demand_month=period["billing_month"],
                region_code=str(
                    getattr(getattr(self, "customer", None), "region", None)
                    or "KR"
                ).upper(),
                pay_currency_code="KRW",
                confirmed_demand_month=period["confirmed_demand_month"],
                month_to_date_start=period["month_to_date_start"],
                month_to_date_end=period["month_to_date_end"],
                organization_context=organization_context,
            )
            collection_errors = self._merge_error_lists(
                collection_errors,
                getattr(billing_collector, "last_errors", []),
            )
            collection_warnings = self._merge_error_lists(
                collection_warnings,
                getattr(billing_collector, "last_warnings", []),
            )
            self.save_json_file(
                data=collection_errors,
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
                comparison_enabled=bool(period.get("is_closed_month", False)),
                report_period=period,
                calculated_at=period["calculated_at"],
            )
            self.save_json_file(
                data=billing_result,
                output_dir=self.output_dir,
                filename=f"billing_result_{period['file_suffix']}.json",
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
            collection_errors = self._merge_error_lists(
                collection_errors,
                getattr(billing_collector, "last_errors", []),
                [billing_failure],
            )
            self.save_json_file(
                data=collection_errors,
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
        self.print_usage_summary(billing_result.get("usage_summary", []))
        return billing_result, collection_errors, collection_warnings

    def _persist_report_artifacts(
        self,
        report: ReportResult,
        *,
        file_suffix: str,
    ) -> None:
        """공개 산출물을 기록하고, 설정된 경우 동일 보고서를 DB에 저장한다."""
        report_json_path = self.save_json_file(
            data=report.to_dict(),
            output_dir=self.output_dir,
            filename=f"ncp_report_{file_suffix}.json",
        )
        report_html_path = Path(self.output_dir) / (
            f"ncp_report_{file_suffix}.html"
        )
        HtmlReportRenderer().write(report=report, path=report_html_path)

        repository = getattr(self, "report_repository", None)
        if repository is None:
            return
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

    def _apply_current_state_period_fallback(
        self,
        *,
        period: Dict[str, Any],
        server_data: List[Dict[str, Any]],
        infrastructure_collected_data: List[Dict[str, Any]],
        infrastructure_warnings: List[Dict[str, Any]],
    ) -> tuple[
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        Dict[str, Any],
    ]:
        """현재 자원에서 보고 종료 전에 생성된 항목만 보수적으로 남긴다.

        현재 API만으로 삭제·변경된 과거 자원을 복원할 수 없으므로 생성 시각이
        확인된 신규 자원만 제외한다. 생성 시각이 없는 자원은 누락 방지를 위해
        유지하되 UNKNOWN 경고로 과거 존재 여부가 확정되지 않았음을 표시한다.
        """
        current_infrastructure = infrastructure_collected_data
        (
            infrastructure_collected_data,
            infrastructure_filter_stats,
        ) = self._filter_current_infrastructure_for_period(
            current_infrastructure,
            period,
        )
        server_data, server_filter_stats = (
            self._filter_current_servers_for_period(
                server_data,
                current_infrastructure,
                period,
            )
        )
        historical_filter_stats = {
            "infrastructure": infrastructure_filter_stats,
            "servers": server_filter_stats,
        }
        infrastructure_warnings.append({
            "collector": "InfrastructureCollector",
            "stage": "historical_presence_inference",
            "target_type": "infrastructure",
            "severity": "warning",
            "code": "CURRENT_STATE_FILTERED_BY_CREATE_TIME",
            "message": (
                "저장된 기간 스냅샷이 없어 현재 자원 중 보고 종료 "
                "이전에 생성된 자원만 목록과 모니터링 대상으로 "
                "사용했습니다. 삭제되었거나 변경된 과거 자원은 "
                "복원되지 않습니다."
            ),
        })
        unknown_resource_keys = {
            (
                str(resource.get("category") or "").upper(),
                str(
                    resource.get("resource_id")
                    or resource.get("resource_name")
                    or f"row-{index}"
                ),
            )
            for index, resource in enumerate(
                infrastructure_collected_data
            )
            if (
                isinstance(resource.get("details"), dict)
                and resource["details"].get(
                    "historical_presence_confidence"
                ) == "UNKNOWN"
            )
        }
        unknown_resource_keys.update(
            (
                "SERVER",
                str(
                    server.get("server_id")
                    or server.get("server_name")
                    or f"row-{index}"
                ),
            )
            for index, server in enumerate(server_data)
            if server.get("historical_presence_confidence")
            == "UNKNOWN"
        )
        unknown_create_time_count = len(unknown_resource_keys)
        historical_filter_stats["unknown_create_time_count"] = (
            unknown_create_time_count
        )
        if unknown_create_time_count:
            infrastructure_warnings.append({
                "collector": "InfrastructureCollector",
                "stage": "historical_presence_inference",
                "target_type": "infrastructure",
                "severity": "warning",
                "code": "RESOURCE_CREATE_TIME_UNAVAILABLE",
                "unknown_create_time_count": (
                    unknown_create_time_count
                ),
                "message": (
                    "생성 시각을 확인할 수 없는 현재 자원은 누락을 "
                    "방지하기 위해 포함했으며 과거 존재 여부는 "
                    "확정할 수 없습니다."
                ),
            })

        return (
            server_data,
            infrastructure_collected_data,
            historical_filter_stats,
        )

    def _restore_boundary_snapshot_payload(
        self,
        *,
        period: Dict[str, Any],
        boundary_snapshot: Dict[str, Any],
        completed_at: Any,
    ) -> tuple[
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        Dict[str, Any],
        Dict[str, Any],
    ]:
        """경계 대체 스냅샷의 payload와 관측 기준 metadata를 복원한다.

        서버와 인프라는 저장 payload만 사용하고, 관측 시각은 수집 완료·시작·
        저장소 참조 시각 순으로 선택해 기존 저장 보고서의 시간 기준을 유지한다.
        """
        server_data = self._dict_records(boundary_snapshot.get("servers"))
        infrastructure_collected_data = self._dict_records(
            boundary_snapshot.get("infrastructure")
        )
        boundary_metadata = boundary_snapshot.get("collection_metadata")
        if not isinstance(boundary_metadata, dict):
            boundary_metadata = {}
        boundary_infrastructure_metadata = boundary_metadata.get(
            "infrastructure"
        )
        if not isinstance(boundary_infrastructure_metadata, dict):
            boundary_infrastructure_metadata = {}
        boundary_reference = boundary_snapshot.get("_snapshot_reference")
        if not isinstance(boundary_reference, dict):
            boundary_reference = {}
        boundary_observed_at = (
            boundary_infrastructure_metadata.get("completed_at")
            or boundary_infrastructure_metadata.get("started_at")
            or boundary_reference.get("observed_at")
        )
        boundary_reference_at = (
            boundary_reference.get("reference_at") or completed_at
        )
        boundary_window = self._snapshot_eligibility_window(
            period,
            boundary_reference_at,
        )
        try:
            parsed_boundary_observed_at = self._parse_kst_datetime(
                str(boundary_observed_at)
            )
        except (TypeError, ValueError):
            parsed_boundary_observed_at = None
        restored_metadata = {
            **boundary_infrastructure_metadata,
            "completed_at": boundary_observed_at,
            "source": "STORED_REPORT_SNAPSHOT",
            "time_basis": "REPORT_PERIOD",
            "source_report_run_id": boundary_reference.get(
                "report_run_id"
            ),
            **snapshot_window_metadata(
                boundary_window,
                parsed_boundary_observed_at,
            ),
        }
        return (
            server_data,
            infrastructure_collected_data,
            boundary_infrastructure_metadata,
            restored_metadata,
        )

    def _validate_boundary_snapshot_observation(
        self,
        *,
        period: Dict[str, Any],
        collection_metadata: Dict[str, Any],
        infrastructure_warnings: List[Dict[str, Any]],
    ) -> bool:
        """대체 스냅샷 관측 시각이 보고 기간 안인지 검증한다.

        검증 실패 시 현재 또는 저장 payload를 노출하지 않도록 metadata를
        UNAVAILABLE로 바꾸고, 호출자가 서버·raw·인프라 데이터를 비우게 한다.
        """
        boundary_observed_at = collection_metadata["infrastructure"].get(
            "completed_at"
        )
        if self._period_contains_timestamp(period, boundary_observed_at):
            return True

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
        return False

    def _update_boundary_snapshot_coverage(
        self,
        *,
        collection_resource_categories: frozenset[str],
        boundary_infrastructure_metadata: Dict[str, Any],
        collection_metadata: Dict[str, Any],
        infrastructure_warnings: List[Dict[str, Any]],
    ) -> None:
        """요청 범주 coverage와 원본 수집 상태를 최종 completeness에 반영한다."""
        boundary_categories = (
            boundary_infrastructure_metadata.get("collected_categories")
            or boundary_infrastructure_metadata.get("resource_categories")
        )
        missing_boundary_categories = []
        coverage_unknown = not isinstance(boundary_categories, list)
        if not coverage_unknown:
            missing_boundary_categories = sorted(
                collection_resource_categories
                - {
                    str(category).upper()
                    for category in boundary_categories
                }
            )
        original_boundary_issue_count = (
            boundary_infrastructure_metadata.get("collection_issue_count")
        )
        try:
            original_boundary_issue_count = max(
                0,
                int(original_boundary_issue_count or 0),
            )
        except (TypeError, ValueError):
            original_boundary_issue_count = 1
        original_boundary_completeness = str(
            boundary_infrastructure_metadata.get("inventory_completeness")
            or "UNKNOWN"
        ).upper()
        coverage_issue_count = int(
            coverage_unknown or bool(missing_boundary_categories)
        )
        if coverage_unknown or missing_boundary_categories:
            infrastructure_warnings.append({
                "collector": "InfrastructureSnapshotRepository",
                "stage": "period_boundary_fallback_coverage",
                "target_type": "infrastructure",
                "severity": "warning",
                "code": (
                    "SNAPSHOT_CATEGORY_COVERAGE_UNKNOWN"
                    if coverage_unknown
                    else "SNAPSHOT_CATEGORY_COVERAGE_INCOMPLETE"
                ),
                "missing_categories": missing_boundary_categories,
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
                original_boundary_issue_count + coverage_issue_count
            ),
        })

    def _mark_missing_boundary_snapshot_unavailable(
        self,
        *,
        period: Dict[str, Any],
        completed_at: Any,
        collection_metadata: Dict[str, Any],
    ) -> tuple[
        List[Dict[str, Any]],
        List[Dict[str, Any]],
    ]:
        """경계 시각에 적합한 저장 스냅샷이 없음을 명시하고 데이터를 비운다."""
        collection_metadata["infrastructure"] = {
            "source": "UNAVAILABLE",
            "time_basis": "REPORT_PERIOD",
            "period_start": period.get("start_dt"),
            "period_end": period.get("end_dt"),
            "inventory_completeness": "UNAVAILABLE",
            "collection_issue_count": 1,
            **snapshot_window_metadata(
                self._snapshot_eligibility_window(
                    period,
                    completed_at,
                )
            ),
        }
        return [], []

    def _reselect_snapshot_after_period_boundary(
        self,
        *,
        period: Dict[str, Any],
        customer_snapshot: Dict[str, Any],
        collection_resource_categories: frozenset[str],
        live_snapshot_in_period: bool,
        collection_metadata: Dict[str, Any],
        server_data: List[Dict[str, Any]],
        infrastructure_collected_data: List[Dict[str, Any]],
        infrastructure_warnings: List[Dict[str, Any]],
    ) -> tuple[
        List[Dict[str, Any]],
        List[Dict[str, Any]],
    ]:
        """실시간 수집 완료가 기간 경계를 넘으면 저장 스냅샷을 다시 선택한다.

        조회와 경고 순서는 이 조율 메서드가 유지하고, payload 복원·관측시각
        검증·범주 coverage 판정은 각각 독립된 정책 helper에 위임한다.
        """
        completed_at = collection_metadata["infrastructure"].get(
            "completed_at"
        )
        if not (
            live_snapshot_in_period
            and not self._period_contains_timestamp(period, completed_at)
        ):
            return (
                server_data,
                infrastructure_collected_data,
            )

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
            infrastructure_warnings.append(boundary_lookup_warning)
        if boundary_snapshot is None:
            return self._mark_missing_boundary_snapshot_unavailable(
                period=period,
                completed_at=completed_at,
                collection_metadata=collection_metadata,
            )

        (
            server_data,
            infrastructure_collected_data,
            boundary_infrastructure_metadata,
            restored_metadata,
        ) = self._restore_boundary_snapshot_payload(
            period=period,
            boundary_snapshot=boundary_snapshot,
            completed_at=completed_at,
        )
        collection_metadata["infrastructure"] = restored_metadata
        if not self._validate_boundary_snapshot_observation(
            period=period,
            collection_metadata=collection_metadata,
            infrastructure_warnings=infrastructure_warnings,
        ):
            return [], []

        self._update_boundary_snapshot_coverage(
            collection_resource_categories=collection_resource_categories,
            boundary_infrastructure_metadata=(
                boundary_infrastructure_metadata
            ),
            collection_metadata=collection_metadata,
            infrastructure_warnings=infrastructure_warnings,
        )
        return (
            server_data,
            infrastructure_collected_data,
        )

    def _collect_live_resource_state(
        self,
        *,
        period: Dict[str, Any],
        collection_plan: ReportCollectionPlan,
        snapshot_decision: SnapshotDecision,
        customer_snapshot: Dict[str, Any],
        resource_result: ResourceCollectionResult,
    ) -> ResourceCollectionResult:
        """서버와 인프라의 실시간 수집 및 기간 보정 단계를 실행한다."""

        selected_resource_categories = (
            collection_plan.selected_resource_categories
        )
        collection_resource_categories = (
            collection_plan.collection_resource_categories
        )
        needs_infrastructure_collection = (
            collection_plan.needs_infrastructure_collection
        )
        collection_metadata = resource_result.collection_metadata
        server_data = resource_result.servers
        server_errors = resource_result.server_errors
        server_raw_data: Dict[str, Any] = {}
        infrastructure_collected_data = resource_result.infrastructure
        infrastructure_errors = resource_result.infrastructure_errors
        infrastructure_warnings = resource_result.infrastructure_warnings
        period_snapshot = snapshot_decision.period_snapshot
        live_snapshot_in_period = snapshot_decision.live_snapshot_in_period
        current_state_period_fallback = (
            snapshot_decision.current_state_period_fallback
        )
        capture_current_snapshot = period_snapshot is not None
        if capture_current_snapshot:
            server_data = []
            server_errors = []
            infrastructure_collected_data = []
            infrastructure_errors = []
            infrastructure_warnings = []
        needs_server_collection = (
            snapshot_decision.needs_server_collection
            or (
                capture_current_snapshot
                and "SERVER" in collection_resource_categories
            )
        )

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

        if (
            needs_infrastructure_collection
            and (
                capture_current_snapshot
                or live_snapshot_in_period
                or current_state_period_fallback
            )
        ):
            infrastructure_started_at = self._now_kst_iso()
            (
                infrastructure_collected_data,
                infrastructure_errors,
                collected_infrastructure_warnings,
            ) = self.collect_infrastructure(
                servers=server_data,
                server_raw_data=server_raw_data,
                categories=collection_resource_categories,
            )
            infrastructure_warnings = self._merge_error_lists(
                infrastructure_warnings,
                collected_infrastructure_warnings,
            )
            infrastructure_completed_at = self._now_kst_iso()
            if not self._period_contains_timestamp(
                period,
                infrastructure_completed_at,
            ):
                snapshot_categories = (
                    set(collection_resource_categories)
                    - set(NETWORK_CONFIGURATION_CATEGORY_OPTIONS)
                )
                snapshot_infrastructure = [
                    dict(item)
                    for item in self._dict_records(
                        infrastructure_collected_data
                    )
                    if str(item.get("category") or "").upper()
                    in ReportResult.PERSISTED_INFRASTRUCTURE_CATEGORIES
                ]
                snapshot_issue_count = (
                    len(server_errors)
                    + len(infrastructure_errors)
                    + len(collected_infrastructure_warnings)
                )
                resource_result.infrastructure_snapshot = {
                    "servers": self._dict_records(server_data),
                    "infrastructure": snapshot_infrastructure,
                    "metadata": {
                        "started_at": infrastructure_started_at,
                        "completed_at": infrastructure_completed_at,
                        "source": "LIVE_API_COLLECTION",
                        "time_basis": "POINT_IN_TIME",
                        "collected_categories": sorted(
                            snapshot_categories
                        ),
                        "persisted_resource_count": len(
                            snapshot_infrastructure
                        ),
                        "persisted_server_count": len(server_data),
                        "inventory_completeness": (
                            "PARTIAL"
                            if snapshot_issue_count
                            else "COMPLETE_FOR_SELECTED_SCOPE"
                        ),
                        "collection_issue_count": snapshot_issue_count,
                    },
                }
            if capture_current_snapshot:
                resource_result.server_errors = self._merge_error_lists(
                    resource_result.server_errors,
                    server_errors,
                )
                resource_result.infrastructure_errors = (
                    self._merge_error_lists(
                        resource_result.infrastructure_errors,
                        infrastructure_errors,
                    )
                )
                resource_result.infrastructure_warnings = (
                    self._merge_error_lists(
                        resource_result.infrastructure_warnings,
                        infrastructure_warnings,
                    )
                )
                return resource_result
            live_snapshot_window = self._snapshot_eligibility_window(
                period,
                infrastructure_completed_at,
            )
            parsed_live_completed_at = self._parse_kst_datetime(
                infrastructure_completed_at
            )
            historical_filter_stats: Dict[str, Any] = {}
            if current_state_period_fallback:
                (
                    server_data,
                    infrastructure_collected_data,
                    historical_filter_stats,
                ) = self._apply_current_state_period_fallback(
                    period=period,
                    server_data=server_data,
                    infrastructure_collected_data=(
                        infrastructure_collected_data
                    ),
                    infrastructure_warnings=infrastructure_warnings,
                )
            observation_metadata = (
                {
                    "reference_at": infrastructure_completed_at,
                    "eligible_start": None,
                    "eligible_end": None,
                    "snapshot_age_seconds": None,
                }
                if current_state_period_fallback
                else snapshot_window_metadata(
                    live_snapshot_window,
                    parsed_live_completed_at,
                )
            )
            collection_metadata["infrastructure"] = {
                "started_at": infrastructure_started_at,
                "completed_at": infrastructure_completed_at,
                "source": (
                    "CURRENT_API_COLLECTION"
                    if current_state_period_fallback
                    else "LIVE_API_COLLECTION"
                ),
                "time_basis": (
                    "CURRENT_STATE_FILTERED_BY_CREATE_TIME"
                    if current_state_period_fallback
                    else "REPORT_PERIOD"
                ),
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
                        current_state_period_fallback
                        or server_errors
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
                "historical_filter": historical_filter_stats,
                **observation_metadata,
            }

            (
                server_data,
                infrastructure_collected_data,
            ) = self._reselect_snapshot_after_period_boundary(
                period=period,
                customer_snapshot=customer_snapshot,
                collection_resource_categories=(
                    collection_resource_categories
                ),
                live_snapshot_in_period=live_snapshot_in_period,
                collection_metadata=collection_metadata,
                server_data=server_data,
                infrastructure_collected_data=(
                    infrastructure_collected_data
                ),
                infrastructure_warnings=infrastructure_warnings,
            )

        resource_result.collection_metadata = collection_metadata
        resource_result.servers = server_data
        resource_result.server_errors = server_errors
        resource_result.infrastructure = infrastructure_collected_data
        resource_result.infrastructure_errors = infrastructure_errors
        resource_result.infrastructure_warnings = infrastructure_warnings
        return resource_result

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
        customer = getattr(self, "customer", None)
        collection_plan = build_collection_plan(
            ReportOptions.from_value(getattr(customer, "report_options", None))
        )
        report_options = collection_plan.report_options
        customer_snapshot = customer.to_dict() if customer is not None else {}
        selected_resource_categories = (
            collection_plan.selected_resource_categories
        )
        selected_monitoring_categories = (
            collection_plan.selected_monitoring_categories
        )
        monitoring_enabled = collection_plan.monitoring_enabled
        monitored_infrastructure_categories = (
            collection_plan.monitored_infrastructure_categories
        )
        collection_resource_categories = (
            collection_plan.collection_resource_categories
        )
        snapshot_decision = self._resolve_snapshot_decision(
            period=period,
            collection_plan=collection_plan,
            customer_snapshot=customer_snapshot,
        )
        initial_warnings = (
            [snapshot_decision.lookup_warning]
            if snapshot_decision.lookup_warning
            else []
        )
        if snapshot_decision.period_snapshot is not None:
            resource_result = self._stored_snapshot_result(
                period=period,
                snapshot=snapshot_decision.period_snapshot,
                observation_check_at=(
                    snapshot_decision.observation_check_at
                ),
                requested_categories=(
                    collection_resource_categories
                    - set(NETWORK_CONFIGURATION_CATEGORY_OPTIONS)
                ),
                initial_warnings=initial_warnings,
            )
        elif (
            collection_plan.needs_resource_snapshot
            and not snapshot_decision.live_snapshot_in_period
            and not snapshot_decision.current_state_period_fallback
        ):
            resource_result = self._unavailable_snapshot_result(
                period=period,
                decision=snapshot_decision,
                initial_warnings=initial_warnings,
            )
        else:
            resource_result = ResourceCollectionResult(
                infrastructure_warnings=initial_warnings
            )

        resource_result = self._collect_live_resource_state(
            period=period,
            collection_plan=collection_plan,
            snapshot_decision=snapshot_decision,
            customer_snapshot=customer_snapshot,
            resource_result=resource_result,
        )
        network_configuration = self._resolve_network_configuration(
            period=period,
            collection_plan=collection_plan,
            customer_snapshot=customer_snapshot,
            resource_result=resource_result,
        )
        if network_configuration.generation_snapshot:
            resource_result.infrastructure = replace_configuration_records(
                resource_result.infrastructure,
                network_configuration.display_configuration,
            )
            resource_result.infrastructure_errors = self._merge_error_lists(
                resource_result.infrastructure_errors,
                network_configuration.errors,
            )
            resource_result.infrastructure_warnings = (
                self._merge_error_lists(
                    resource_result.infrastructure_warnings,
                    network_configuration.warnings,
                )
            )
            resource_result.collection_metadata[
                "network_configuration"
            ] = network_configuration.metadata
        collection_metadata = resource_result.collection_metadata
        server_data = resource_result.servers
        server_errors = resource_result.server_errors
        infrastructure_collected_data = resource_result.infrastructure
        infrastructure_errors = resource_result.infrastructure_errors
        infrastructure_warnings = resource_result.infrastructure_warnings

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

        observability = self._collect_observability(
            period=period,
            report_options=report_options,
            server_data=server_data,
            infrastructure_data=infrastructure_collected_data,
            monitoring_enabled=monitoring_enabled,
            selected_monitoring_categories=selected_monitoring_categories,
            monitored_infrastructure_categories=(
                monitored_infrastructure_categories
            ),
            base_errors=[server_errors, infrastructure_errors],
            base_warnings=[infrastructure_warnings],
        )
        insight_data = observability.server_metrics
        infrastructure_metric_data = observability.infrastructure_metrics
        insight_events = observability.insight_events
        insight_grouped_events = observability.grouped_insight_events
        activity_data = observability.activity_events
        all_collection_errors = observability.errors
        all_collection_warnings = observability.warnings

        self._write_prebilling_artifacts(
            period=period,
            observability=observability,
            infrastructure=infrastructure_data,
        )

        (
            billing_result,
            all_collection_errors,
            all_collection_warnings,
        ) = self._collect_billing(
            period=period,
            report_options=report_options,
            collection_errors=all_collection_errors,
            collection_warnings=all_collection_warnings,
        )

        comparison_baseline: Optional[Dict[str, Any]] = None
        if (
            self._operational_analysis_feature_enabled()
            and report_options.analysis_enabled()
        ):
            comparison_baseline, baseline_warning = (
                self._load_analysis_baseline(
                    period=period,
                    customer=customer_snapshot,
                )
            )
            all_collection_warnings = self._merge_error_lists(
                all_collection_warnings,
                [baseline_warning] if baseline_warning else [],
            )

            infrastructure_requested = (
                report_options.section_enabled("infrastructure_inventory")
            )
            monitoring_requested = report_options.section_enabled(
                "monitoring"
            )
            observability.dataset_statuses.extend((
                self._dataset_status_entry(
                    key="infrastructure",
                    label="인프라 자원",
                    requested=infrastructure_requested,
                    record_count=len(infrastructure_collected_data),
                    errors=self._merge_error_lists(
                        server_errors, infrastructure_errors
                    ),
                    warnings=infrastructure_warnings,
                    source="NCP_RESOURCE_APIS",
                ),
                self._dataset_status_entry(
                    key="monitoring",
                    label="모니터링 지표",
                    requested=monitoring_requested,
                    record_count=monitoring_observation_count(
                        insight_data, infrastructure_metric_data
                    ),
                    errors=self._issues_matching(
                        all_collection_errors,
                        "insightmetric",
                        "infrastructuremetric",
                    ),
                    source="NCP_CLOUD_INSIGHT",
                ),
                self._dataset_status_entry(
                    key="insight_events",
                    label="Cloud Insight 이벤트",
                    requested=report_options.section_enabled(
                        "insight_events"
                    ),
                    record_count=len(insight_events),
                    errors=observability.insight_event_errors,
                    source="NCP_CLOUD_INSIGHT",
                ),
                self._dataset_status_entry(
                    key="activity_events",
                    label="변경 이력",
                    requested=report_options.section_enabled(
                        "activity_history"
                    ),
                    record_count=self._grouped_record_count(activity_data),
                    errors=observability.activity_errors,
                    source="NCP_CLOUD_ACTIVITY_TRACER",
                ),
                self._dataset_status_entry(
                    key="billing",
                    label="비용",
                    requested=(
                        report_options.section_enabled("billing")
                        or report_options.section_enabled(
                            "organization_billing"
                        )
                    ),
                    record_count=self._billing_available_fact_count(
                        billing_result
                    ),
                    errors=self._issues_matching(
                        all_collection_errors, "billing"
                    ),
                    source="NCP_BILLING",
                ),
            ))

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
            service_availability=observability.service_availability,
            security_monitoring=observability.security_monitoring,
            dataset_statuses=observability.dataset_statuses,
            report_options=report_options.to_dict(),
            collection_metadata=collection_metadata,
            collection_errors=all_collection_errors,
            collection_warnings=all_collection_warnings,
            infrastructure_snapshot=(
                resource_result.infrastructure_snapshot
            ),
            network_configuration_snapshot=(
                network_configuration.generation_snapshot
            ),
            generated_at=self._now_kst_iso(),
        )
        if (
            self._operational_analysis_feature_enabled()
            and report_options.analysis_enabled()
        ):
            report.analysis = analyze_report(
                report,
                baseline=comparison_baseline,
                policy=report_options.operational_analysis,
            )
            report.analysis["report_generation"] = {
                "status": "SUCCESS",
                "status_label": "성공",
                "source_state": "OBSERVED",
                "generated_at": report.generated_at,
            }
        self._persist_report_artifacts(
            report,
            file_suffix=period["file_suffix"],
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
                retained_categories = set(normalized_categories)
                # Target Group은 사용자 선택 항목이 아니라 LB 상태와 기간
                # 메트릭을 구성하는 내부 보조 자원이므로 LB와 함께 보존한다.
                if "LOAD_BALANCER" in retained_categories:
                    retained_categories.add("TARGET_GROUP")
                normalized_data = [
                    item for item in normalized_data
                    if str(item.get("category") or "").upper()
                    in retained_categories
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
            normalized_resource_categories = set(normalized_categories)
            if "LOAD_BALANCER" in normalized_resource_categories:
                normalized_resource_categories.add("TARGET_GROUP")
            metric_infrastructure = (
                [
                    item for item in infrastructure
                    if str(item.get("category") or "").upper()
                    in normalized_resource_categories
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
                normalized_error = normalize_collection_issue(error)
                identity = json.dumps(
                    normalized_error,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )

                if identity in seen:
                    continue

                seen.add(identity)
                result.append(normalized_error)

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

from app.apifactory import APIFactory
from app.customer import CustomerProfile
from app.renderers import HtmlReportRenderer
from app.report_models import ReportResult
from collectors import (
    ServerCollector,
    InsightMetricCollector,
    ActivityTracerEventCollector,
    BillingCollector,
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
        start_text = start_kst.strftime("%Y-%m-%d %H:%M:%S")
        end_text = end_kst.strftime("%Y-%m-%d %H:%M:%S")

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

        server_collector = ServerCollector(api_factory=self.api_factory)
        server_data = server_collector.collect()
        server_errors = list(getattr(server_collector, "last_errors", []))

        insight_data, insight_metric_errors = self.collect_insight_metrics(
            server_data=server_data,
            period=period,
        )

        insight_events, insight_grouped_events, insight_event_errors = self.collect_insight_events(
            period=period,
        )

        activity_collector = ActivityTracerEventCollector(api_factory=self.api_factory)
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
            all_insight_errors,
            activity_errors,
        )
        all_collection_warnings: List[Dict[str, Any]] = []

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

        billing_collector = None
        billing_stage = "collection"

        try:
            billing_collector = BillingCollector(
                api_factory=self.api_factory
            )
            billing_raw = billing_collector.collect_raw(
                use_start_date=period["use_start_date"],
                use_end_date=period["usage_query_end_date"],
                demand_month=period["billing_month"],
                region_code="KR",
                pay_currency_code="KRW",
                confirmed_demand_month=period["confirmed_demand_month"],
                month_to_date_start=period["month_to_date_start"],
                month_to_date_end=period["month_to_date_end"],
            )
            billing_errors = list(
                getattr(billing_collector, "last_errors", [])
            )
            all_collection_errors = self._merge_error_lists(
                all_collection_errors,
                billing_errors,
            )
            all_collection_warnings = self._merge_error_lists(
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
        self.print_usage_summary(billing_result.get("usage_summary", []))

        report = ReportResult(
            period=period,
            customer=(
                getattr(self, "customer", None).to_dict()
                if getattr(self, "customer", None) is not None
                else {}
            ),
            servers=self._dict_records(server_data),
            server_metrics=self._dict_records(insight_data),
            insight_events=self._dict_records(insight_events),
            grouped_insight_events=insight_grouped_events,
            activity_events=activity_data,
            billing=billing_result,
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

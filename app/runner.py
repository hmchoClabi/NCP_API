from app.apifactory import APIFactory
from collectors import (
    ServerCollector,
    InsightMetricCollector,
    ActivityTracerEventCollector,
    BillingCollector,
)
from collectors.insighteventcollector import InsightEventCollector
from normalizers.billingnormalizer import BillingNormalizer
from utils.data_utils import get_unix_time_stamp

import json
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


class ReportRunner:

    def __init__(self):
        self.api_factory = APIFactory()

    def get_month_range(self) -> Dict[str, Any]:
        today = date.today()

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
    ) -> Dict[str, Any]:
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

    def build_period(
        self,
        start: date,
        end: date,
        period_type: str,
    ) -> Dict[str, Any]:
        start_dt = f"{start:%Y-%m-%d} 00:00:00"
        end_dt = f"{end:%Y-%m-%d} 23:59:59"

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
        }

    def run(
        self,
        target_month: Optional[str] = None,
        target_day: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> None:
        period = self.get_period(
            target_month=target_month,
            target_day=target_day,
            start_date=start_date,
            end_date=end_date,
        )

        self.print_period_summary(period)

        server_collector = ServerCollector(api_factory=self.api_factory)
        server_data = server_collector.collect()

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

        billing_collector = BillingCollector(api_factory=self.api_factory)

        billing_raw = billing_collector.collect_raw(
            use_start_date=period["use_start_date"],
            use_end_date=period["use_end_date"],
            demand_month=period["billing_month"],
            region_code="KR",
            pay_currency_code="KRW",
        )

        self.save_json_file(
            data=billing_raw,
            output_dir="./output/report",
            filename=f"billing_raw_{period['file_suffix']}.json",
        )

        billing_result = BillingNormalizer().normalize(
            raw_data=billing_raw,
            current_month=period["billing_month"],
            billing_month=period["billing_month"],
            use_end_date=period["use_end_date"],
        )

        self.save_json_file(
            data=billing_result,
            output_dir="./output/report",
            filename=f"billing_result_{period['file_suffix']}.json",
        )

        all_insight_errors = []
        all_insight_errors.extend(insight_metric_errors)
        all_insight_errors.extend(insight_event_errors)

        self.print_server_metric_summary(insight_data)
        self.print_insight_event_summary(insight_events)
        self.print_insight_error_summary(all_insight_errors)
        self.print_network_usage_summary(billing_result.get("network_usage_summary", []))
        self.print_billing_summary(billing_result)
        self.print_usage_summary(billing_result.get("usage_summary", []))

        self.save_json_file(
            data={
                "events": insight_events,
                "grouped_events": insight_grouped_events,
                "errors": insight_event_errors,
            },
            output_dir="./output/report",
            filename=f"cloud_insight_events_{period['file_suffix']}.json",
        )

        self.save_json_file(
            data=activity_data,
            output_dir="./output/report",
            filename=f"activity_tracer_events_{period['file_suffix']}.json",
        )

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
            insight_data = insight_result
            insight_errors = []

        return insight_data, insight_errors

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

        insight_events = insight_event_result.get("events", [])
        insight_grouped_events = insight_event_result.get("grouped_events", {})
        insight_event_errors = insight_event_result.get("errors", [])

        return insight_events, insight_grouped_events, insight_event_errors

    def print_server_metric_summary(
        self,
        insight_data: List[Dict[str, Any]],
    ) -> None:
        print()
        print("=" * 80)
        print("서버 메트릭")
        print("=" * 80)

        if not insight_data:
            print("서버 메트릭 없음")
            return

        summaries = []

        for item in insight_data:
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
            output_dir="./output/report",
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
    ) -> None:
        print()
        print("=" * 80)
        print("Cloud Insight 수집 오류")
        print("=" * 80)

        if not insight_errors:
            print("Cloud Insight 수집 오류 없음")
            return

        for error in insight_errors:
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
            data=insight_errors,
            output_dir="./output/report",
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
    ) -> None:
        summary = billing_result["summary"]

        print("\n" + "=" * 80)
        print("확정 청구 금액")
        print("=" * 80)
        print(f"청구월 : {summary['billing_month']}")
        print(f"확정 청구 금액 : {summary['confirmed_total_amount']:,.0f} 원")
        print(f"청구 항목 수 : {summary.get('row_count', summary.get('service_count', 0))} 건")

        print("\n" + "=" * 80)
        print("서비스별 청구 금액")
        print("=" * 80)

        for service in billing_result["service_summary"]:
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
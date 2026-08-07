import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple
from zoneinfo import ZoneInfo

from app.report_models import ReportResult
from utils.event_sort import sort_event_records


class HtmlReportRenderer:
    """Render a standalone, responsive HTML report without web dependencies."""

    KST = ZoneInfo("Asia/Seoul")
    CHART_COLORS = (
        "#03c75a",
        "#2563eb",
        "#f97316",
        "#8b5cf6",
        "#0891b2",
        "#dc2626",
        "#65a30d",
        "#db2777",
        "#4f46e5",
        "#0f766e",
        "#a16207",
        "#475569",
    )

    def render(self, report: ReportResult) -> str:
        period = report.period
        customer_name = str(report.customer.get("name") or "").strip()
        report_title = (
            f"{customer_name} · NCP 이용 보고서"
            if customer_name
            else "NCP 이용 보고서"
        )
        billing = report.billing or {}
        billing_summary = billing.get("summary", {})
        invoice_summary = self._mapping(billing.get("invoice_summary"))
        period_estimate = self._mapping(billing.get("period_estimate"))
        month_to_date_estimate = self._mapping(
            billing.get("month_to_date_estimate")
        )
        month_end_projection = self._mapping(
            billing.get("month_end_projection")
        )
        cost_facts = [
            fact for fact in (
                invoice_summary,
                period_estimate,
                month_to_date_estimate,
                month_end_projection,
            )
            if fact and fact.get("status") != "NOT_APPLICABLE"
        ]
        confirmed_service_summary = self._records(
            billing.get("service_summary")
        )
        use_estimated_cost = period.get("is_closed_month") is False
        if use_estimated_cost:
            service_summary = [
                {
                    "service_name": row.get("service_name"),
                    "amount": row.get("expected_amount"),
                    "row_count": row.get("row_count"),
                }
                for row in self._records(billing.get("expected_by_service"))
            ]
            billing_card_title = "기간 예상 비용"
            billing_card_amount = period_estimate.get(
                "total_amount", billing_summary.get("expected_total_amount")
            )
            billing_section_title = "서비스별 예상 비용"
            billing_section_description = (
                "선택한 기간의 사용량과 단가로 계산한 미확정 예상 비용입니다. "
                "시간 범위 보고서도 비용 API의 일 단위 사용량을 기준으로 합니다."
            )
        else:
            service_summary = confirmed_service_summary
            billing_card_title = "확정 청구 금액"
            billing_card_amount = invoice_summary.get(
                "total_amount", billing_summary.get("confirmed_total_amount")
            )
            billing_section_title = "서비스별 청구 금액"
            billing_section_description = (
                "NCP 서비스 단위로 집계한 확정 청구 금액입니다."
            )
        usage_summary = self._records(billing.get("usage_summary"))
        network_summary = self._records(
            billing.get("network_usage_summary")
        )
        activity_events = self._flatten_grouped(report.activity_events)

        return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="report-id" content="{self._text(report.report_id)}">
  <title>{self._text(report_title)} · {self._text(report.report_id)}</title>
  <style>{self._styles()}</style>
</head>
<body>
  <main class="report-shell">
    <header class="report-header">
      <div>
        <p class="eyebrow">NAVER CLOUD PLATFORM</p>
        <h1>{self._text(report_title)}</h1>
        <p class="subtitle">{self._text(self._display_period_start(period))}
          <span aria-hidden="true">→</span>
          {self._text(self._display_period_end(period))}</p>
      </div>
      <div class="report-meta">
        <span>보고서 ID</span>
        <strong>{self._text(report.report_id)}</strong>
        <span>생성 시각</span>
        <strong>{self._text(report.generated_at)}</strong>
      </div>
    </header>

    <section class="summary-grid" aria-label="주요 요약">
      {self._summary_card("서버", len(report.servers), "대")}
      {self._summary_card(
          "Cloud Insight 이벤트",
          len(report.insight_events),
          "건",
      )}
      {self._summary_card(
          "수집 오류",
          len(report.collection_errors),
          "건",
          warning=bool(report.collection_errors),
      )}
      {self._summary_card(
          billing_card_title,
          self._number(
              billing_card_amount,
              decimals=0,
          ),
          "원",
      )}
    </section>

    {self._section(
        "서버 목록",
        "보고서 생성 시점에 조회된 서버 인벤토리입니다.",
        self._table(
            self._records(report.servers),
            (
                ("server_name", "서버명"),
                ("status", "상태"),
                ("private_ip", "Private IP"),
                ("public_ip", "Public IP"),
                ("cpu_count", "vCPU", "number0"),
                ("memory_gb", "메모리 (GB)", "number3"),
                ("zone_code", "Zone"),
            ),
        ),
        len(report.servers),
    )}
    {self._section(
        "서버 메트릭",
        "기간 중 CPU, 메모리 및 파일시스템 사용률입니다.",
        self._metric_table(report.display_server_metrics),
        len(report.display_server_metrics),
    )}
    {self._metric_chart_section(report.server_metrics, report.period)}
    {self._section(
        "과금 데이터 기준",
        "확정·추정 데이터의 대상 기간, 실제 수집 범위와 계산 기준 시점을 구분합니다.",
        self._billing_fact_cards(cost_facts),
        len(cost_facts),
    )}
    {self._section(
        billing_section_title,
        billing_section_description,
        self._table(
            service_summary,
            (
                ("service_name", "서비스"),
                ("amount", "금액", "number0"),
                ("row_count", "항목", "number0"),
            ),
        ),
        len(service_summary),
    )}
    {self._section(
        "Cloud Insight 이벤트",
        "보고 기간에 수집된 Cloud Insight 이벤트입니다.",
        self._event_table(report.insight_events),
        len(report.insight_events),
    )}
    {self._section(
        "Cloud Activity Tracer",
        "보고 기간에 기록된 계정 및 리소스 작업 이력입니다.",
        self._activity_table(activity_events),
        len(activity_events),
    )}
    {self._section(
        "네트워크 사용량",
        "서비스와 전송 방향별 네트워크 사용량입니다.",
        self._table(
            network_summary,
            (
                ("service_name", "서비스"),
                ("direction", "방향"),
                ("name", "항목"),
                ("usage_gb", "사용량 (GB)", "number3"),
                ("row_count", "건수", "number0"),
            ),
        ),
        len(network_summary),
    )}
    {self._section(
        "서비스별 사용량",
        "서비스 및 과금 항목별 사용량입니다.",
        self._table(
            usage_summary,
            (
                ("service_name", "서비스"),
                ("item_name", "항목"),
                ("usage_quantity", "사용량", "number3"),
                ("unit_code", "단위"),
                ("row_count", "건수", "number0"),
            ),
        ),
        len(usage_summary),
    )}
    {self._section(
        "수집 경고",
        "보고서 생성을 중단하지 않는 제한 사항입니다.",
        self._error_table(report.collection_warnings),
        len(report.collection_warnings),
        warning=bool(report.collection_warnings),
    )}
    {self._section(
        "수집 오류",
        "부분 실패가 발생해도 완료된 데이터는 보고서에 포함됩니다.",
        self._error_table(report.collection_errors),
        len(report.collection_errors),
        warning=bool(report.collection_errors),
    )}

    <footer>
      <p>이 보고서는 구조화된 NCP 수집 결과로부터 생성되었습니다.</p>
    </footer>
  </main>
</body>
</html>
"""

    def write(self, report: ReportResult, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(report), encoding="utf-8")
        return path

    def _summary_card(
        self,
        label: str,
        value: Any,
        unit: str,
        warning: bool = False,
    ) -> str:
        status_class = " warning" if warning else ""
        return f"""
      <article class="summary-card{status_class}">
        <span>{self._text(label)}</span>
        <strong>{self._text(value)} <small>{self._text(unit)}</small></strong>
      </article>"""

    def _section(
        self,
        title: str,
        description: str,
        content: str,
        count: int,
        warning: bool = False,
    ) -> str:
        status_class = " warning" if warning else ""
        return f"""
    <section class="report-section{status_class}">
      <div class="section-heading">
        <div>
          <h2>{self._text(title)}</h2>
          <p>{self._text(description)}</p>
        </div>
        <span class="count">{count:,}건</span>
      </div>
      {content}
    </section>"""

    def _metric_table(self, rows: List[Dict[str, Any]]) -> str:
        prepared = []
        for row in rows:
            prepared.append(
                {
                    **row,
                    "os_fs": self._filesystem_text(
                        row.get("os_fs_details")
                    ),
                    "data_fs": self._filesystem_text(
                        row.get("data_fs_details")
                    ),
                }
            )

        return self._table(
            prepared,
            (
                ("server_name", "서버"),
                ("cpu_min", "CPU 최소", "percent"),
                ("cpu_avg", "CPU 평균", "percent"),
                ("cpu_max", "CPU 최대", "percent"),
                ("mem_min", "MEM 최소", "percent"),
                ("mem_avg", "MEM 평균", "percent"),
                ("mem_max", "MEM 최대", "percent"),
                ("os_fs", "OS 파일시스템"),
                ("data_fs", "DATA 파일시스템"),
            ),
        )

    def _metric_chart_section(
        self,
        server_metrics: List[Dict[str, Any]],
        period: Dict[str, Any],
    ) -> str:
        interval = self._report_metric_interval(
            server_metrics,
            period,
        )
        aggregation_label = self._metric_interval_label(interval)
        charts = (
            (
                "CPU 그룹",
                f"서버별 CPU {aggregation_label} 사용률",
                self._metric_series(
                    server_metrics,
                    metric_name="used_rto",
                    period=period,
                ),
                "auto",
            ),
            (
                "MEM 그룹",
                f"서버별 메모리 {aggregation_label} 사용률",
                self._metric_series(
                    server_metrics,
                    metric_name="mem_usert",
                    period=period,
                ),
                "auto",
            ),
            (
                "루트 디스크 그룹",
                f"서버별 루트 디스크 {aggregation_label} 사용률",
                self._metric_series(
                    server_metrics,
                    metric_name="fs_usert",
                    period=period,
                    filesystem_group="root",
                ),
                "fixed",
            ),
            (
                "DATA 디스크 그룹",
                (
                    "서버 및 마운트별 DATA 디스크 "
                    f"{aggregation_label} 사용률"
                ),
                self._metric_series(
                    server_metrics,
                    metric_name="fs_usert",
                    period=period,
                    filesystem_group="data",
                ),
                "fixed",
            ),
        )
        chart_cards = "".join(
            f"""
      <article class="chart-card">
        <div class="chart-heading">
          <h3>{self._text(title)}</h3>
          <p>{self._text(description)}</p>
        </div>
        {self._line_chart(title, series, period, y_axis, interval)}
      </article>"""
            for title, description, series, y_axis in charts
        )

        return f"""
    <section class="report-section metric-trends">
      <div class="section-heading">
        <div>
          <h2>보고 기간 메트릭 변화</h2>
          <p>보고서 기간 전체를 기준으로 KST {aggregation_label} 데이터를 표시합니다.</p>
        </div>
        <span class="count">4개 그룹</span>
      </div>
      <div class="chart-grid">{chart_cards}</div>
    </section>"""

    def _metric_series(
        self,
        server_metrics: List[Dict[str, Any]],
        metric_name: str,
        period: Dict[str, Any],
        filesystem_group: str | None = None,
    ) -> Dict[str, List[Tuple[int, float]]]:
        period_start, period_end = self._period_bounds(period)
        buckets: Dict[str, Dict[int, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )

        for server_metric in server_metrics:
            if not isinstance(server_metric, dict):
                continue

            raw_metrics = server_metric.get("raw_metrics")
            if not isinstance(raw_metrics, dict):
                continue

            metric_data = raw_metrics.get(metric_name)
            if not isinstance(metric_data, dict):
                continue

            entries = metric_data.get("avg")
            if not isinstance(entries, list):
                continue

            server_name = str(
                server_metric.get("server_name")
                or server_metric.get("server_id")
                or "unknown"
            )
            data_mounts = {
                str(detail.get("mount"))
                for detail in self._records(
                    server_metric.get("data_fs_details")
                )
                if detail.get("mount") is not None
            }

            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                dimensions = entry.get("dimensions")
                if not isinstance(dimensions, dict):
                    dimensions = {}
                mount = dimensions.get("mnt_nm")

                if filesystem_group == "root":
                    if not self._is_root_mount(mount):
                        continue
                elif filesystem_group == "data":
                    if mount is None or str(mount) not in data_mounts:
                        continue

                label = server_name
                if filesystem_group and mount is not None:
                    label = f"{server_name} · {mount}"

                for point_time, point_value in self._metric_points(entry):
                    if (
                        period_start is not None
                        and point_time < period_start
                    ):
                        continue
                    if period_end is not None and point_time > period_end:
                        continue

                    buckets[label][point_time].append(point_value)

        result = {}
        for label, daily_values in buckets.items():
            result[label] = [
                (
                    point_time,
                    sum(values) / len(values),
                )
                for point_time, values in sorted(daily_values.items())
                if values
            ]
        return result

    def _metric_interval_label(self, interval: str) -> str:
        return {
            "Min1": "1분 AVG",
            "Min5": "5분 AVG",
            "Min30": "30분 AVG",
            "Hour2": "2시간 AVG",
            "Day1": "1일 AVG",
        }[interval]

    def _report_metric_interval(
        self,
        server_metrics: List[Dict[str, Any]],
        period: Dict[str, Any],
    ) -> str:
        supported = {"Min1", "Min5", "Min30", "Hour2", "Day1"}
        for metric in server_metrics:
            if not isinstance(metric, dict):
                continue
            interval = metric.get("metric_interval")
            if interval in supported:
                return str(interval)

        # Backward-compatible fallback for results generated before
        # metric_interval became part of the report model.
        start, end = self._period_bounds(period)
        if start is None or end is None:
            return "Day1"

        duration = max(end - start, 0)
        day = 24 * 60 * 60 * 1000
        if duration <= day:
            return "Min5"
        if duration <= 7 * day:
            return "Min30"
        if duration <= 31 * day:
            return "Hour2"
        return "Day1"

    def _metric_interval_millis(self, interval: str) -> int:
        return {
            "Min1": 60 * 1000,
            "Min5": 5 * 60 * 1000,
            "Min30": 30 * 60 * 1000,
            "Hour2": 2 * 60 * 60 * 1000,
            "Day1": 24 * 60 * 60 * 1000,
        }[interval]

    def _period_bounds(
        self,
        period: Dict[str, Any],
    ) -> Tuple[int | None, int | None]:
        start = self._timestamp_millis(period.get("start_time"))
        end = self._timestamp_millis(period.get("end_time"))

        if start is None:
            start = self._datetime_text_millis(period.get("start_dt"))
        if end is None:
            end = self._datetime_text_millis(period.get("end_dt"))
        return start, end

    def _timestamp_millis(self, value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            return None
        if abs(timestamp) < 100_000_000_000:
            timestamp *= 1000
        return int(timestamp)

    def _datetime_text_millis(self, value: Any) -> int | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.strptime(
                value.strip(),
                "%Y-%m-%d %H:%M:%S",
            ).replace(tzinfo=self.KST)
        except ValueError:
            return None
        return int(parsed.timestamp() * 1000)

    def _is_single_day_period(self, period: Dict[str, Any]) -> bool:
        if period.get("period_type") == "day":
            return True
        start, end = self._period_bounds(period)
        if start is None or end is None:
            return False
        start_date = datetime.fromtimestamp(
            start / 1000,
            tz=self.KST,
        ).date()
        end_date = datetime.fromtimestamp(
            end / 1000,
            tz=self.KST,
        ).date()
        return start_date == end_date

    def _metric_points(
        self,
        entry: Dict[str, Any],
    ) -> List[Tuple[int, float]]:
        points = entry.get("points")
        if not isinstance(points, list):
            raw = entry.get("raw")
            points = raw.get("dps") if isinstance(raw, dict) else []

        result = []
        for point in points or []:
            if isinstance(point, dict):
                timestamp = point.get("timestamp")
                value = point.get("value")
            elif isinstance(point, (list, tuple)) and len(point) >= 2:
                timestamp, value = point[0], point[1]
            else:
                continue

            try:
                normalized_time = float(timestamp)
                normalized_value = float(value)
            except (TypeError, ValueError):
                continue

            if abs(normalized_time) < 100_000_000_000:
                normalized_time *= 1000
            result.append((int(normalized_time), normalized_value))

        return result

    def _is_root_mount(self, mount: Any) -> bool:
        if mount is None:
            return False
        normalized = str(mount).strip().replace("\\", "/")
        if len(normalized) > 1:
            normalized = normalized.rstrip("/")
        return normalized == "/" or normalized.upper() == "C:"

    def _line_chart(
        self,
        title: str,
        series: Dict[str, List[Tuple[int, float]]],
        period: Dict[str, Any],
        y_axis: str,
        interval: str,
    ) -> str:
        populated = {
            label: points
            for label, points in series.items()
            if points
        }
        if not populated:
            return (
                '<p class="empty-state chart-empty">'
                "표시할 시계열 데이터가 없습니다."
                "</p>"
            )

        all_times = sorted(
            {
                point_time
                for points in populated.values()
                for point_time, _ in points
            }
        )
        period_start, period_end = self._period_bounds(period)
        first_time = period_start if period_start is not None else all_times[0]
        last_time = period_end if period_end is not None else all_times[-1]
        time_span = max(last_time - first_time, 1)
        single_day = self._is_single_day_period(period)
        aggregation_label = self._metric_interval_label(interval)
        y_max = (
            100.0
            if y_axis == "fixed"
            else self._auto_axis_max(populated)
        )

        width = 1000
        height = 300
        left = 58
        right = 20
        top = 18
        bottom = 42
        plot_width = width - left - right
        plot_height = height - top - bottom

        grid_parts = []
        for tick_index in range(5):
            tick = y_max * tick_index / 4
            y = top + plot_height - (tick / y_max * plot_height)
            tick_label = (
                f"{tick:.0f}%"
                if tick >= 1
                else f"{tick:.1f}%"
            )
            grid_parts.append(
                f'<line x1="{left}" y1="{y:.2f}" '
                f'x2="{width - right}" y2="{y:.2f}" '
                'class="chart-grid-line"/>'
                f'<text x="{left - 10}" y="{y + 4:.2f}" '
                'class="chart-axis-label" text-anchor="end">'
                f"{self._text(tick_label)}</text>"
            )

        x_ticks = (first_time, first_time + time_span // 2, last_time)
        for tick_time in x_ticks:
            x = (
                left
                + ((tick_time - first_time) / time_span * plot_width)
            )
            tick_dt = datetime.fromtimestamp(
                tick_time / 1000,
                tz=self.KST,
            )
            tick_label = tick_dt.strftime(
                "%H:%M" if single_day else "%m-%d"
            )
            grid_parts.append(
                f'<text x="{x:.2f}" y="{height - 12}" '
                'class="chart-axis-label" text-anchor="middle">'
                f"{self._text(tick_label)}</text>"
            )

        line_parts = []
        legend_parts = []
        expected_interval = self._metric_interval_millis(interval)
        for index, (label, points) in enumerate(populated.items()):
            color = self.CHART_COLORS[index % len(self.CHART_COLORS)]
            for segment in self._split_chart_points(
                points,
                expected_interval=expected_interval,
            ):
                coordinates = []
                circles = []
                show_markers = len(segment) <= 60
                for point_time, value in segment:
                    x = (
                        left
                        + (
                            (point_time - first_time)
                            / time_span
                            * plot_width
                        )
                    )
                    clamped_value = min(max(value, 0), y_max)
                    y = top + plot_height - (
                        clamped_value / y_max * plot_height
                    )
                    coordinates.append(f"{x:.2f},{y:.2f}")
                    if show_markers:
                        circles.append(
                            f'<circle cx="{x:.2f}" cy="{y:.2f}" '
                            f'r="2.4" fill="{color}"><title>'
                            f"{self._text(label)} · "
                            f"{self._text(self._chart_point_label(point_time))} · "
                            f"{self._text(f'{value:.2f}%')}"
                            "</title></circle>"
                        )

                line_parts.append(
                    f'<polyline points="{" ".join(coordinates)}" '
                    f'stroke="{color}" class="chart-line"><title>'
                    f"{self._text(label)}</title></polyline>"
                    + "".join(circles)
                )
            legend_parts.append(
                '<span class="chart-legend-item">'
                f'<i style="background:{color}"></i>'
                f"{self._text(label)}</span>"
            )

        return (
            f'<div class="chart" role="img" '
            f'aria-label="{self._text(title)} '
            f'{self._text(aggregation_label)} 변화 그래프">'
            f'<svg viewBox="0 0 {width} {height}" '
            'preserveAspectRatio="xMidYMid meet">'
            + "".join(grid_parts)
            + "".join(line_parts)
            + "</svg><div class=\"chart-legend\">"
            + "".join(legend_parts)
            + "</div></div>"
        )

    def _chart_point_label(
        self,
        timestamp: int,
    ) -> str:
        point_dt = datetime.fromtimestamp(
            timestamp / 1000,
            tz=self.KST,
        )
        return point_dt.strftime("%Y-%m-%d %H:%M KST")

    def _auto_axis_max(
        self,
        series: Dict[str, List[Tuple[int, float]]],
    ) -> float:
        maximum = max(
            value
            for points in series.values()
            for _, value in points
        )
        target = max(maximum * 1.1, 1)
        magnitude = 10 ** math.floor(math.log10(target))
        normalized = target / magnitude

        for step in (1, 1.25, 1.5, 2, 2.5, 5, 10):
            if normalized <= step:
                return float(step * magnitude)
        return float(10 * magnitude)

    def _split_chart_points(
        self,
        points: List[Tuple[int, float]],
        expected_interval: int,
    ) -> List[List[Tuple[int, float]]]:
        if not points:
            return []

        segments = [[points[0]]]
        gap_limit = expected_interval * 2.5
        for point in points[1:]:
            if point[0] - segments[-1][-1][0] > gap_limit:
                segments.append([point])
            else:
                segments[-1].append(point)
        return segments

    def _event_table(self, rows: Any) -> str:
        prepared = []
        sorted_rows = sort_event_records(
            self._records(rows),
            ("event_time", "start_time", "time", "timestamp"),
        )
        for row in sorted_rows:
            prepared.append(
                {
                    "time": self._first(
                        row,
                        "start_time_kst",
                        "event_time",
                        "time",
                        "timestamp",
                        "start_time",
                    ),
                    "severity": self._first(
                        row,
                        "severity",
                        "level",
                        "event_level",
                        "status",
                    ),
                    "resource": self._first(
                        row,
                        "resource_name",
                        "resource_id",
                        "target_name",
                        "target_id",
                        "nrn",
                    ),
                    "type": self._first(
                        row,
                        "event_type",
                        "type",
                        "rule_name",
                        "metric",
                    ),
                    "message": self._first(
                        row,
                        "message",
                        "description",
                        "reason",
                        "event_message",
                        "condition",
                    ),
                    "condition": self._insight_event_condition(row),
                    "details": self._insight_event_details(row),
                }
            )

        return self._table(
            prepared,
            (
                ("time", "시각"),
                ("severity", "심각도"),
                ("resource", "리소스"),
                ("type", "유형"),
                ("condition", "발생 조건/감지값"),
                ("message", "설명"),
                ("details", "상세", "html"),
            ),
        )

    def _insight_event_condition(self, row: Dict[str, Any]) -> str:
        metric = self._first_present(row.get("metric"))
        detected = self._first_present(row.get("detect_value"))
        operator = self._first_present(
            row.get("operator_symbol"),
            row.get("operator"),
        )
        criteria = self._first_present(row.get("criteria"))
        unit = self._first_present(row.get("unit"))

        condition = " ".join(
            part for part in (metric, operator, criteria) if part
        )
        if detected:
            condition = (
                f"{condition} / 감지 {detected}{unit}"
                if condition
                else f"감지 {detected}{unit}"
            )
        return condition or "-"

    def _insight_event_details(self, row: Dict[str, Any]) -> str:
        fields = (
            ("이벤트 ID", row.get("event_id")),
            ("이벤트 룰", row.get("rule_name")),
            ("룰 ID", row.get("rule_id")),
            ("설명", row.get("description")),
            ("메트릭", row.get("metric")),
            ("메트릭 그룹 항목 ID", row.get("metric_group_item_id")),
            ("이벤트 상세 키", row.get("calc_sliding_group_key")),
            ("집계 함수", row.get("calc")),
            ("집계 주기", row.get("interval")),
            ("발생 시각", row.get("start_time_kst")),
            ("종료 시각", row.get("end_time_kst")),
            ("상품", row.get("prod_name")),
            ("리소스 ID", row.get("resource_id")),
            ("리전", row.get("region_code")),
            ("존", row.get("zone_code")),
            ("차원", row.get("dimension")),
            ("통보 그룹", row.get("notification_groups")),
            ("통보 상태", row.get("notification_status")),
            ("유지보수 중", row.get("in_maintenance")),
            ("삭제된 리소스", row.get("resource_deleted")),
        )
        items = []
        for label, value in fields:
            if value is None or value == "" or value == [] or value == {}:
                continue
            if isinstance(value, (dict, list)):
                rendered_value = json.dumps(
                    value,
                    ensure_ascii=False,
                    default=str,
                )
            elif isinstance(value, bool):
                rendered_value = "예" if value else "아니오"
            else:
                rendered_value = str(value)
            if len(rendered_value) > 300:
                rendered_value = rendered_value[:297] + "..."
            items.append(
                "<div><dt>"
                + self._text(label)
                + "</dt><dd>"
                + self._text(rendered_value)
                + "</dd></div>"
            )

        if not items:
            return "-"
        return (
            '<details class="event-details"><summary>'
            f"상세 {len(items):,}개"
            "</summary><dl>"
            + "".join(items)
            + "</dl></details>"
        )

    def _error_table(self, rows: Any) -> str:
        prepared = []
        for row in self._records(rows):
            prepared.append(
                {
                    "collector": row.get("collector"),
                    "stage": row.get("stage"),
                    "target": self._first(
                        row,
                        "target_name",
                        "target_id",
                        "resource_id",
                    ),
                    "status": row.get("status_code"),
                    "code": row.get("error_code"),
                    "message": row.get("message"),
                }
            )

        return self._table(
            prepared,
            (
                ("collector", "수집기"),
                ("stage", "단계"),
                ("target", "대상"),
                ("status", "상태"),
                ("code", "코드"),
                ("message", "메시지"),
            ),
        )

    def _activity_table(self, rows: Any) -> str:
        prepared = []
        sorted_rows = sort_event_records(
            self._records(rows),
            ("event_time", "event_time_kst", "time", "timestamp"),
        )
        for row in sorted_rows:
            prepared.append(
                {
                    **row,
                    "display_event_time": (
                        row.get("event_time_kst")
                        or row.get("event_time")
                    ),
                    "actor": self._activity_actor(row),
                    "target": self._activity_target(row),
                    "details": self._activity_details(row),
                }
            )

        return self._table(
            prepared,
            (
                ("display_event_time", "발생 시각 (KST)"),
                ("actor", "수행 계정"),
                ("product_display_name", "서비스"),
                ("target", "대상 객체"),
                ("action_name", "작업"),
                ("result", "결과"),
                ("source_ip", "접속 IP"),
                ("details", "상세", "html"),
            ),
        )

    def _activity_actor(self, row: Dict[str, Any]) -> str:
        product_data = row.get("product_data")
        if not isinstance(product_data, dict):
            product_data = {}

        actor = self._first_present(
            row.get("user_name"),
            product_data.get("userName"),
            product_data.get("subAccountId"),
            row.get("sub_account_no"),
            row.get("member_no"),
        )
        user_type = self._first_present(
            row.get("user_type"),
            product_data.get("userType"),
        )

        if actor and user_type:
            return f"{actor} ({user_type})"
        return actor or user_type or "-"

    def _activity_target(self, row: Dict[str, Any]) -> str:
        product_data = row.get("product_data")
        if not isinstance(product_data, dict):
            product_data = {}

        target = self._first_present(
            row.get("resource_name"),
            product_data.get("resourceName"),
            product_data.get("serverName"),
            product_data.get("computeInstanceName"),
            product_data.get("dbServerName"),
            product_data.get("dbServiceName"),
            product_data.get("vpcName"),
            product_data.get("name"),
            row.get("resource_id"),
            row.get("nrn"),
        )
        resource_type = self._first_present(row.get("resource_type"))

        if target and resource_type:
            return f"{resource_type}: {target}"
        return target or resource_type or "-"

    def _activity_details(self, row: Dict[str, Any]) -> str:
        product_data = row.get("product_data")
        if not isinstance(product_data, dict):
            return "-"

        items = []
        for key, value in product_data.items():
            if self._is_sensitive_detail_key(str(key)):
                continue
            if value is None or value == "" or value == [] or value == {}:
                continue

            if isinstance(value, (dict, list)):
                rendered_value = json.dumps(
                    value,
                    ensure_ascii=False,
                    default=str,
                )
            else:
                rendered_value = str(value)

            if len(rendered_value) > 300:
                rendered_value = rendered_value[:297] + "..."

            items.append(
                "<div><dt>"
                + self._text(key)
                + "</dt><dd>"
                + self._text(rendered_value)
                + "</dd></div>"
            )

        if not items:
            return "-"

        visible_items = items[:30]
        remaining = len(items) - len(visible_items)
        remaining_text = (
            f'<p class="detail-more">외 {remaining:,}개 필드</p>'
            if remaining
            else ""
        )
        return (
            '<details class="event-details"><summary>'
            f"상세 {len(items):,}개"
            "</summary><dl>"
            + "".join(visible_items)
            + "</dl>"
            + remaining_text
            + "</details>"
        )

    def _is_sensitive_detail_key(self, key: str) -> bool:
        normalized = "".join(
            character
            for character in key.lower()
            if character.isalnum()
        )
        sensitive_terms = (
            "password",
            "secret",
            "token",
            "credential",
            "authorization",
            "cookie",
            "accesskey",
            "apikey",
            "privatekey",
            "mfainfo",
            "otp",
        )
        return any(term in normalized for term in sensitive_terms)

    def _first_present(self, *values: Any) -> str:
        for value in values:
            if value is not None and str(value).strip():
                return str(value)
        return ""

    def _table(
        self,
        rows: List[Dict[str, Any]],
        columns: Sequence[Tuple[str, str] | Tuple[str, str, str]],
    ) -> str:
        if not rows:
            return '<p class="empty-state">표시할 데이터가 없습니다.</p>'

        header = "".join(
            f"<th scope=\"col\">{self._text(column[1])}</th>"
            for column in columns
        )
        body_rows = []

        for row in rows:
            cells = []
            for column in columns:
                key = column[0]
                format_name = column[2] if len(column) > 2 else "text"
                value = self._format_value(row.get(key), format_name)
                numeric_class = (
                    ' class="numeric"'
                    if format_name.startswith("number")
                    or format_name == "percent"
                    else ""
                )
                cells.append(f"<td{numeric_class}>{value}</td>")
            body_rows.append("<tr>" + "".join(cells) + "</tr>")

        return (
            '<div class="table-wrap"><table><thead><tr>'
            + header
            + "</tr></thead><tbody>"
            + "".join(body_rows)
            + "</tbody></table></div>"
        )

    def _format_value(self, value: Any, format_name: str) -> str:
        if format_name == "number0":
            return self._text(self._number(value, decimals=0))
        if format_name == "number3":
            return self._text(self._number(value, decimals=3))
        if format_name == "percent":
            if value is None or value == "":
                return "-"
            return self._text(f"{self._number(value, decimals=2)}%")
        if format_name == "html":
            return value if isinstance(value, str) else self._text(value)
        return self._text(value)

    def _filesystem_text(self, value: Any) -> str:
        if not isinstance(value, list):
            return "-"

        items = []
        for entry in value:
            if not isinstance(entry, dict):
                continue
            mount = entry.get("mount") or "-"
            average = self._number(entry.get("avg"), decimals=2)
            maximum = self._number(entry.get("max"), decimals=2)
            items.append(f"{mount}: 평균 {average}% / 최대 {maximum}%")
        return ", ".join(items) or "-"

    def _first(self, row: Dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = row.get(key)
            if value is not None and str(value).strip():
                return value
        return "-"

    @staticmethod
    def _mapping(value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _display_period_start(self, period: Dict[str, Any]) -> str:
        value = str(period.get("start_dt") or "-")
        if period.get("period_type") != "datetime_range":
            return value[:10]
        return value

    def _display_period_end(self, period: Dict[str, Any]) -> str:
        value = str(period.get("end_dt") or "-")
        if value == "-":
            return value
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if period.get("end_exclusive"):
                parsed -= timedelta(microseconds=1)
            if period.get("period_type") != "datetime_range":
                return parsed.strftime("%Y-%m-%d")
            return parsed.isoformat(sep=" ", timespec="seconds")
        except ValueError:
            return value

    def _billing_fact_cards(self, facts: List[Dict[str, Any]]) -> str:
        labels = {
            "CONFIRMED": "확정 청구 데이터",
            "PERIOD_ESTIMATE": "보고 기간 추정 데이터",
            "MONTH_TO_DATE_ESTIMATE": "월 누적 추정 데이터",
            "MONTH_END_PROJECTION": "월말 추정 데이터",
        }
        basis_labels = {
            "INVOICE_TOTAL": "NCP 발행 청구서 총액",
            "CURRENT_MONTH_INVOICE_TOTAL": "NCP 해당 월 확정 금액 (VAT 포함)",
            "PRE_DISCOUNT_LIST_PRICE": "사용량 × 단가 (할인·VAT 전)",
            "DAILY_RUN_RATE_PROJECTION": "월 누적 일평균 추세 예측",
        }
        cards = []
        for fact in facts:
            status = str(fact.get("status") or "UNAVAILABLE")
            amount = (
                self._number(fact.get("total_amount"), 0) + "원"
                if fact.get("total_amount") is not None else "조회 불가"
            )
            period_text = (
                f"{fact.get('period_start') or '-'} ~ "
                f"{fact.get('period_end') or '-'}"
            )
            coverage_text = (
                f"{fact.get('coverage_start') or '-'} ~ "
                f"{fact.get('coverage_end') or '-'}"
            )
            invoice_breakdown = ""
            if fact.get("cost_type") == "CONFIRMED" and status == "AVAILABLE":
                invoice_breakdown = (
                    "<li><span>공급가액 / VAT</span><strong>"
                    f"{self._number(fact.get('subtotal_amount'), 0)}원 / "
                    f"{self._number(fact.get('vat_amount'), 0)}원"
                    "</strong></li>"
                )
            included = (
                f"할인 {'포함' if fact.get('includes_discount') else '미포함'}, "
                f"VAT {'포함' if fact.get('includes_vat') else '미포함'}"
            )
            cards.append(
                '<article class="billing-fact">'
                f"<h3>{self._text(labels.get(str(fact.get('cost_type')), fact.get('cost_type')))}</h3>"
                f'<strong class="billing-amount">{self._text(amount)}</strong>'
                "<ul>"
                f"<li><span>대상 기간</span><strong>{self._text(period_text)}</strong></li>"
                f"<li><span>실제 수집 범위</span><strong>{self._text(coverage_text)}</strong></li>"
                f"<li><span>계산 기준 시각</span><strong>{self._text(fact.get('calculated_at'))}</strong></li>"
                f"<li><span>금액 기준</span><strong>{self._text(basis_labels.get(str(fact.get('amount_basis')), fact.get('amount_basis')))}</strong></li>"
                f"<li><span>포함 범위</span><strong>{self._text(included)}</strong></li>"
                f"<li><span>신뢰도</span><strong>{self._text(fact.get('confidence'))}</strong></li>"
                f"{invoice_breakdown}"
                "</ul></article>"
            )
        return '<div class="billing-facts">' + "".join(cards) + "</div>"

    def _records(self, value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [row for row in value if isinstance(row, dict)]

    def _flatten_grouped(self, value: Any) -> List[Dict[str, Any]]:
        if isinstance(value, list):
            return sort_event_records(
                self._records(value),
                ("event_time", "event_time_kst", "time", "timestamp"),
            )
        if not isinstance(value, dict):
            return []

        result = []
        seen = set()
        for rows in value.values():
            for row in self._records(rows):
                identity = (
                    row.get("event_id")
                    or row.get("historyId")
                    or id(row)
                )
                if identity in seen:
                    continue
                seen.add(identity)
                result.append(row)
        return sort_event_records(
            result,
            ("event_time", "event_time_kst", "time", "timestamp"),
        )

    def _number(self, value: Any, decimals: int) -> str:
        try:
            return f"{float(value or 0):,.{decimals}f}"
        except (TypeError, ValueError):
            return "-"

    def _text(self, value: Any) -> str:
        if value is None or value == "":
            return "-"
        return escape(str(value), quote=True)

    def _styles(self) -> str:
        return """
:root {
  color-scheme: light;
  --ink: #14213d;
  --muted: #64748b;
  --line: #dbe4ee;
  --surface: #ffffff;
  --canvas: #f3f6fa;
  --brand: #03c75a;
  --brand-dark: #008f43;
  --warning: #b45309;
  font-family: Inter, Pretendard, "Noto Sans KR", system-ui, sans-serif;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  color: var(--ink);
  background: var(--canvas);
  line-height: 1.55;
}
.report-shell {
  width: min(1440px, calc(100% - 32px));
  margin: 32px auto;
}
.report-header {
  display: flex;
  justify-content: space-between;
  gap: 32px;
  padding: 36px;
  color: #fff;
  background: linear-gradient(135deg, #0f172a, #164e3b);
  border-radius: 20px;
  box-shadow: 0 16px 40px rgba(15, 23, 42, .16);
}
.eyebrow {
  margin: 0 0 8px;
  color: #86efac;
  font-size: .78rem;
  font-weight: 800;
  letter-spacing: .14em;
}
h1 { margin: 0; font-size: clamp(2rem, 4vw, 3.4rem); line-height: 1.1; }
.subtitle { margin: 18px 0 0; color: #d1fae5; }
.report-meta {
  display: grid;
  grid-template-columns: auto;
  align-content: end;
  min-width: 210px;
}
.report-meta span { color: #a7f3d0; font-size: .75rem; }
.report-meta strong { margin-bottom: 10px; font-size: .88rem; }
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin: 20px 0;
}
.summary-card {
  padding: 22px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 14px;
}
.summary-card span { display: block; color: var(--muted); font-size: .84rem; }
.summary-card strong { display: block; margin-top: 8px; font-size: 1.75rem; }
.summary-card small { color: var(--muted); font-size: .8rem; font-weight: 600; }
.summary-card.warning { border-color: #fed7aa; }
.summary-card.warning strong { color: var(--warning); }
.report-section {
  margin-top: 20px;
  padding: 26px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 16px;
}
.report-section.warning { border-color: #fed7aa; }
.section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 18px;
}
h2 { margin: 0; font-size: 1.22rem; }
.section-heading p { margin: 5px 0 0; color: var(--muted); font-size: .88rem; }
.count {
  flex: none;
  padding: 5px 10px;
  color: var(--brand-dark);
  background: #dcfce7;
  border-radius: 999px;
  font-size: .78rem;
  font-weight: 800;
}
.billing-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.billing-fact {
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #f8fafc;
}
.billing-fact h3 { margin: 0; font-size: 1rem; }
.billing-amount { display: block; margin: 8px 0 14px; font-size: 1.45rem; }
.billing-fact ul { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.billing-fact li { display: flex; justify-content: space-between; gap: 16px; font-size: .82rem; }
.billing-fact li span { color: var(--muted); }
.billing-fact li strong { text-align: right; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: .84rem; }
th {
  padding: 11px 12px;
  color: #475569;
  background: #f8fafc;
  border-bottom: 1px solid var(--line);
  text-align: left;
  white-space: nowrap;
}
td {
  padding: 11px 12px;
  border-bottom: 1px solid #edf2f7;
  vertical-align: top;
}
tbody tr:hover { background: #f8fffb; }
.numeric { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.chart-card {
  min-width: 0;
  padding: 18px;
  background: #fbfdff;
  border: 1px solid var(--line);
  border-radius: 12px;
}
.chart-heading h3 { margin: 0; font-size: 1rem; }
.chart-heading p { margin: 3px 0 12px; color: var(--muted); font-size: .78rem; }
.chart svg { display: block; width: 100%; height: auto; overflow: visible; }
.chart-grid-line { stroke: #e2e8f0; stroke-width: 1; }
.chart-axis-label { fill: #64748b; font-size: 11px; }
.chart-line {
  fill: none;
  stroke-width: 2.4;
  stroke-linejoin: round;
  stroke-linecap: round;
}
.chart-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  margin-top: 6px;
}
.chart-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #475569;
  font-size: .72rem;
}
.chart-legend-item i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}
.chart-empty { min-height: 180px; align-content: center; }
.event-details { min-width: 160px; }
.event-details summary {
  color: var(--brand-dark);
  cursor: pointer;
  font-weight: 700;
  white-space: nowrap;
}
.event-details dl { margin: 10px 0 0; }
.event-details dl div {
  display: grid;
  grid-template-columns: minmax(90px, .8fr) minmax(140px, 1.4fr);
  gap: 8px;
  padding: 5px 0;
  border-bottom: 1px solid #edf2f7;
}
.event-details dt { color: var(--muted); font-size: .74rem; overflow-wrap: anywhere; }
.event-details dd { margin: 0; font-size: .74rem; overflow-wrap: anywhere; }
.detail-more { margin: 8px 0 0; color: var(--muted); font-size: .72rem; }
.empty-state {
  margin: 0;
  padding: 28px;
  color: var(--muted);
  background: #f8fafc;
  border-radius: 10px;
  text-align: center;
}
footer { padding: 22px 4px; color: var(--muted); font-size: .78rem; text-align: center; }
@media (max-width: 900px) {
  .report-header { flex-direction: column; padding: 28px; }
  .report-meta { grid-template-columns: auto 1fr; gap: 4px 14px; }
  .summary-grid, .billing-facts { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .chart-grid { grid-template-columns: 1fr; }
}
@media (max-width: 560px) {
  .report-shell { width: min(100% - 20px, 1440px); margin: 10px auto; }
  .report-header, .report-section { border-radius: 12px; }
  .summary-grid, .billing-facts { grid-template-columns: 1fr; gap: 10px; }
  .section-heading { flex-direction: column; gap: 10px; }
}
@media print {
  @page { size: A4 landscape; margin: 12mm; }
  body { background: #fff; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .report-shell { width: 100%; margin: 0; }
  .report-header { box-shadow: none; break-after: avoid; }
  .summary-grid, .report-section { break-inside: avoid; }
  .metric-trends { break-inside: auto; }
  .chart-card { break-inside: avoid; }
  .report-section { padding: 18px; }
  table { font-size: 8pt; }
  tr { break-inside: avoid; }
}
"""

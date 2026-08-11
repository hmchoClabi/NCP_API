import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple
from zoneinfo import ZoneInfo

from app.renderers.html_styles import HTML_REPORT_STYLES
from app.renderers.html_view_models import (
    BillingDisplayData,
    EventDiagnosticSectionHtml,
    InfrastructureSectionHtml,
    ReportDisplayData,
    ReportSectionHtml,
)
from app.report_branding import normalize_customer_logo_data_uri
from app.report_options import (
    MONITORING_CATEGORY_OPTIONS,
    NETWORK_CONFIGURATION_CATEGORY_OPTIONS,
    RESOURCE_CATEGORY_LABELS,
)
from app.report_models import ReportResult
from utils.event_sort import sort_event_records


class HtmlReportRenderer:
    """웹 프레임워크 의존성 없이 독립형 반응형 HTML 보고서를 만든다."""

    KST = ZoneInfo("Asia/Seoul")
    MAX_CHART_POINTS_PER_SEGMENT = 600
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
    INFRASTRUCTURE_CATEGORIES = tuple(
        RESOURCE_CATEGORY_LABELS.items()
    )

    def render(self, report: ReportResult) -> str:
        display = self._prepare_display_data(report)
        sections = self._render_report_sections(report, display)
        return self._render_document(report, display, sections)

    def _prepare_display_data(
        self,
        report: ReportResult,
    ) -> ReportDisplayData:
        """보고서 원본과 섹션 옵션을 HTML 표시 모델로 정규화한다.

        각 section option은 여기서 한 번만 판정한다. 이후 조립 단계는 비활성
        섹션을 빈 문자열로 유지해 기존 문서 순서와 공개 렌더링 경계를 보존한다.
        """
        period = report.period
        report_options = report.selected_report_options
        customer_name = str(report.customer.get("name") or "").strip()
        report_title = (
            f"{customer_name} · NCP 이용 보고서"
            if customer_name
            else "NCP 이용 보고서"
        )
        billing_display = self._prepare_billing_display(
            period,
            report.billing or {},
        )
        activity_events = self._flatten_grouped(report.activity_events)
        infrastructure = report.display_infrastructure
        load_balancer_target_groups = (
            report.display_load_balancer_target_groups
        )
        inventory_enabled = report_options.section_enabled(
            "infrastructure_inventory"
        )
        monitoring_enabled = report_options.section_enabled("monitoring")
        billing_enabled = report_options.section_enabled("billing")
        organization_billing_enabled = report_options.section_enabled(
            "organization_billing"
        )
        collection_metadata = self._mapping(report.collection_metadata)
        infrastructure_metadata = self._mapping(
            collection_metadata.get("infrastructure")
        )
        network_configuration_metadata = self._mapping(
            collection_metadata.get("network_configuration")
        )
        customer_logo_data_uri = self._safe_customer_logo_data_uri(
            report.customer.get("logo_data_uri")
        )
        return ReportDisplayData(
            period=period,
            report_options=report_options,
            report_title=report_title,
            customer_name=customer_name,
            customer_logo_data_uri=customer_logo_data_uri,
            customer_initials=self._customer_initials(customer_name),
            billing=billing_display,
            activity_events=activity_events,
            infrastructure=infrastructure,
            load_balancer_target_groups=load_balancer_target_groups,
            inventory_enabled=inventory_enabled,
            monitoring_enabled=monitoring_enabled,
            billing_enabled=billing_enabled,
            organization_billing_enabled=organization_billing_enabled,
            infrastructure_metadata=infrastructure_metadata,
            network_configuration_metadata=(
                network_configuration_metadata
            ),
        )

    def _prepare_billing_display(
        self,
        period: Dict[str, Any],
        billing: Dict[str, Any],
    ) -> BillingDisplayData:
        """확정 월은 청구액, 진행 중인 기간은 추정액을 표시 기준으로 삼는다.

        미마감 기간에서 기간 추정치가 적용 불가하면 월 누적 추정치를 사용하며,
        금액 basis에 따라 실제 사용액 또는 예상 금액 서비스 집계를 선택한다.
        """
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
        account_costs = self._records(billing.get("account_costs"))
        confirmed_service_summary = self._records(
            billing.get("service_summary")
        )
        use_estimated_cost = period.get("is_closed_month") is False
        if use_estimated_cost:
            use_month_to_date = (
                period_estimate.get("status") == "NOT_APPLICABLE"
                and month_to_date_estimate.get("status") == "AVAILABLE"
            )
            if use_month_to_date and month_to_date_estimate.get(
                "amount_basis"
            ) in {
                "NCP_PRODUCT_DEMAND_USE_AMOUNT",
                "NCP_CURRENT_USE_AMOUNT_FALLBACK",
            }:
                service_summary = [
                    {
                        "service_name": row.get("service_name"),
                        "amount": row.get("use_amount"),
                        "row_count": row.get("row_count"),
                    }
                    for row in self._records(
                        billing.get("target_service_summary")
                    )
                ]
            elif use_month_to_date:
                service_summary = [
                    {
                        "service_name": row.get("service_name"),
                        "amount": row.get("expected_amount"),
                        "row_count": row.get("row_count"),
                    }
                    for row in self._records(
                        billing.get("month_to_date_by_service")
                    )
                ]
            else:
                service_summary = [
                    {
                        "service_name": row.get("service_name"),
                        "amount": row.get("expected_amount"),
                        "row_count": row.get("row_count"),
                    }
                    for row in self._records(billing.get("expected_by_service"))
                ]
            billing_card_title = (
                "보고 기준일까지 누적 추정 비용"
                if use_month_to_date
                else "기간 예상 비용"
            )
            billing_card_amount = (
                month_to_date_estimate.get("total_amount")
                if use_month_to_date
                else period_estimate.get("total_amount")
            )
            if billing_card_amount is None:
                billing_card_amount = billing_summary.get(
                    "expected_total_amount"
                )
            billing_section_title = "서비스별 예상 비용"
            billing_section_description = (
                "보고 기준일까지 수집한 사용량과 단가로 계산한 미확정 예상 비용입니다. "
                if use_month_to_date
                else "선택한 기간의 사용량과 단가로 계산한 미확정 예상 비용입니다. "
            ) + (
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
        return BillingDisplayData(
            cost_facts=cost_facts,
            account_costs=account_costs,
            service_summary=service_summary,
            card_title=billing_card_title,
            card_amount=billing_card_amount,
            section_title=billing_section_title,
            section_description=billing_section_description,
            usage_summary=usage_summary,
            network_summary=network_summary,
        )

    def _render_historical_notice(
        self,
        display: ReportDisplayData,
    ) -> str:
        if (
            (display.inventory_enabled or display.monitoring_enabled)
            and display.infrastructure_metadata.get("time_basis")
            == "CURRENT_STATE_FILTERED_BY_CREATE_TIME"
        ):
            return self._historical_inventory_notice(
                display.infrastructure_metadata
            )
        return ""

    def _render_summary_section(
        self,
        report: ReportResult,
        display: ReportDisplayData,
    ) -> str:
        report_options = display.report_options
        if report_options.section_enabled("executive_summary"):
            summary_cards = []
            if display.inventory_enabled:
                summary_cards.append(
                    self._summary_card(
                        "대표 인프라",
                        len(display.infrastructure),
                        "개",
                    )
                )
            if report_options.section_enabled("insight_events"):
                summary_cards.append(
                    self._summary_card(
                        "Cloud Insight 이벤트",
                        len(report.insight_events),
                        "건",
                    )
                )
            if report_options.section_enabled("collection_diagnostics"):
                summary_cards.append(
                    self._summary_card(
                        "수집 오류",
                        len(report.collection_errors),
                        "건",
                        warning=bool(report.collection_errors),
                    )
                )
            if (
                display.billing_enabled
                or display.organization_billing_enabled
            ):
                summary_cards.append(
                    self._summary_card(
                        display.billing.card_title,
                        self._number(
                            display.billing.card_amount,
                            decimals=0,
                        ),
                        "원",
                    )
                )
            return (
                '<section class="summary-grid" aria-label="주요 요약">'
                + "".join(summary_cards)
                + "</section>"
            )
        return ""

    def _render_infrastructure_sections(
        self,
        report: ReportResult,
        display: ReportDisplayData,
    ) -> InfrastructureSectionHtml:
        network_categories = set(NETWORK_CONFIGURATION_CATEGORY_OPTIONS)
        inventory_resources = [
            resource
            for resource in display.infrastructure
            if str(resource.get("category") or "").upper()
            not in network_categories
        ]
        inventory_html = (
            self._infrastructure_section(inventory_resources)
            if display.inventory_enabled and inventory_resources else ""
        )
        network_configuration_html = (
            self._network_configuration_section(
                display.infrastructure,
                display.network_configuration_metadata,
            )
            if (
                display.inventory_enabled
                and any(
                    display.report_options.resource_enabled(category)
                    for category in network_categories
                )
            )
            else ""
        )
        target_group_html = ""
        if display.inventory_enabled and (
            display.load_balancer_target_groups
            or any(
                str(resource.get("category") or "").upper()
                == "LOAD_BALANCER"
                for resource in display.infrastructure
            )
        ):
            target_group_html = self._load_balancer_target_group_section(
                display.load_balancer_target_groups,
                display.infrastructure_metadata,
            )
        server_detail_html = ""
        if (
            display.inventory_enabled
            and display.report_options.resource_enabled("SERVER")
        ):
            server_rows = [
                {
                    **server,
                    "historical_presence_text": (
                        self._historical_confidence_text(
                            server.get("historical_presence_confidence")
                        )
                    ),
                }
                for server in self._records(report.servers)
            ]
            server_columns = [
                ("server_name", "서버명"),
                ("status", "상태"),
                ("private_ip", "Private IP"),
                ("public_ip", "Public IP"),
                ("cpu_count", "vCPU", "number0"),
                ("memory_gb", "메모리(GB)", "number3"),
                ("zone_code", "Zone"),
            ]
            if any(
                server.get("historical_presence_confidence")
                for server in server_rows
            ):
                server_columns.append(
                    ("historical_presence_text", "기간 존재 판단")
                )
            server_detail_html = self._section(
                "서버 상세",
                (
                    "생성 시각으로 선별한 현재 서버 구성입니다. 상태와 "
                    "IP는 보고서 생성 시점의 값입니다."
                    if display.infrastructure_metadata.get("time_basis")
                    == "CURRENT_STATE_FILTERED_BY_CREATE_TIME"
                    else "보고서 기준 시점에 저장된 서버 구성입니다."
                ),
                self._table(
                    server_rows,
                    tuple(server_columns),
                ),
                len(server_rows),
            )
        return InfrastructureSectionHtml(
            inventory=inventory_html,
            network_configuration=network_configuration_html,
            target_groups=target_group_html,
            server_details=server_detail_html,
        )

    def _render_monitoring_sections(
        self,
        report: ReportResult,
        display: ReportDisplayData,
    ) -> str:
        if display.monitoring_enabled:
            monitoring_parts = []
            if display.report_options.monitoring_enabled("SERVER"):
                monitoring_parts.extend((
                    self._section(
                        "서버 메트릭",
                        "보고 기간의 CPU, 메모리 및 파일시스템 사용률입니다.",
                        self._metric_table(report.display_server_metrics),
                        len(report.display_server_metrics),
                    ),
                    self._metric_chart_section(
                        report.server_metrics,
                        report.period,
                    ),
                ))
            monitoring_parts.append(
                self._infrastructure_metric_section(
                    report.display_infrastructure_metrics,
                    report.period,
                    display.infrastructure,
                )
            )
            return "".join(monitoring_parts)
        return ""

    def _render_billing_sections(
        self,
        display: ReportDisplayData,
    ) -> tuple[str, str]:
        billing_html = ""
        if display.billing_enabled:
            billing = display.billing
            billing_html = "".join((
                self._section(
                    "과금 데이터 기준",
                    "확정·추정 데이터의 대상 기간, 실제 수집 범위와 계산 기준 시점을 구분합니다.",
                    self._billing_fact_cards(billing.cost_facts),
                    len(billing.cost_facts),
                ),
                self._section(
                    billing.section_title,
                    billing.section_description,
                    self._table(
                        billing.service_summary,
                        (
                            ("service_name", "서비스"),
                            ("amount", "금액", "number0"),
                            ("row_count", "항목", "number0"),
                        ),
                    ),
                    len(billing.service_summary),
                ),
                self._section(
                    "네트워크 사용량",
                    "서비스와 전송 방향별 네트워크 사용량입니다.",
                    self._table(
                        billing.network_summary,
                        (
                            ("service_name", "서비스"),
                            ("direction", "방향"),
                            ("name", "항목"),
                            ("usage_gb", "사용량(GB)", "number3"),
                            ("row_count", "건수", "number0"),
                        ),
                    ),
                    len(billing.network_summary),
                ),
                self._section(
                    "서비스별 사용량",
                    "서비스 및 과금 항목별 사용량입니다.",
                    self._table(
                        billing.usage_summary,
                        (
                            ("service_name", "서비스"),
                            ("item_name", "항목"),
                            ("usage_quantity", "사용량", "number3"),
                            ("unit_code", "단위"),
                            ("row_count", "건수", "number0"),
                        ),
                    ),
                    len(billing.usage_summary),
                ),
            ))

        organization_billing_html = (
            self._organization_cost_sections(display.billing.account_costs)
            if display.organization_billing_enabled else ""
        )
        return billing_html, organization_billing_html

    def _render_event_diagnostic_sections(
        self,
        report: ReportResult,
        display: ReportDisplayData,
    ) -> EventDiagnosticSectionHtml:
        insight_events_html = (
            self._section(
                "Cloud Insight 이벤트",
                "보고 기간에 수집된 Cloud Insight 이벤트입니다.",
                self._event_table(report.insight_events),
                len(report.insight_events),
            )
            if display.report_options.section_enabled("insight_events")
            else ""
        )
        activity_html = (
            self._section(
                "Cloud Activity Tracer",
                "보고 기간에 기록된 계정 및 리소스 작업 이력입니다.",
                self._activity_table(display.activity_events),
                len(display.activity_events),
            )
            if display.report_options.section_enabled("activity_history")
            else ""
        )
        diagnostics_html = ""
        if display.report_options.section_enabled("collection_diagnostics"):
            diagnostics_html = "".join((
                self._section(
                    "수집 경고",
                    "보고서 생성을 중단하지 않는 제한 사항입니다.",
                    self._error_table(report.collection_warnings),
                    len(report.collection_warnings),
                    warning=bool(report.collection_warnings),
                ),
                self._section(
                    "수집 오류",
                    "부분 실패가 발생해도 완료된 데이터는 보고서에 포함합니다.",
                    self._error_table(report.collection_errors),
                    len(report.collection_errors),
                    warning=bool(report.collection_errors),
                ),
            ))
        return EventDiagnosticSectionHtml(
            insight_events=insight_events_html,
            activity=activity_html,
            diagnostics=diagnostics_html,
        )

    def _render_report_sections(
        self,
        report: ReportResult,
        display: ReportDisplayData,
    ) -> ReportSectionHtml:
        historical_notice = self._render_historical_notice(display)
        summary = self._render_summary_section(report, display)
        infrastructure = self._render_infrastructure_sections(
            report,
            display,
        )
        monitoring = self._render_monitoring_sections(report, display)
        billing, organization_billing = self._render_billing_sections(display)
        event_diagnostics = self._render_event_diagnostic_sections(
            report,
            display,
        )
        return ReportSectionHtml(
            summary=summary,
            historical_notice=historical_notice,
            inventory=infrastructure.inventory,
            network_configuration=(
                infrastructure.network_configuration
            ),
            target_groups=infrastructure.target_groups,
            server_details=infrastructure.server_details,
            monitoring=monitoring,
            billing=billing,
            organization_billing=organization_billing,
            insight_events=event_diagnostics.insight_events,
            activity=event_diagnostics.activity,
            diagnostics=event_diagnostics.diagnostics,
        )

    def _render_document(
        self,
        report: ReportResult,
        display: ReportDisplayData,
        sections: ReportSectionHtml,
    ) -> str:
        period = display.period
        report_title = display.report_title
        logo = (
            f'<img src="{self._text(display.customer_logo_data_uri)}" '
            f'alt="{self._text(display.customer_name)} 로고">'
            if display.customer_logo_data_uri
            else (
                f'<span aria-hidden="true">'
                f'{self._text(display.customer_initials)}</span>'
            )
        )

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
      <div class="report-identity">
        <div class="customer-logo-plate">{logo}</div>
        <div class="report-heading">
          <p class="eyebrow">NAVER CLOUD PLATFORM</p>
          <h1>{self._text(report_title)}</h1>
          <p class="subtitle">{self._text(self._display_period_start(period))}
            <span aria-hidden="true">→</span>
            {self._text(self._display_period_end(period))}</p>
        </div>
      </div>
      <div class="report-meta">
        <span>보고서 ID</span>
        <strong>{self._text(report.report_id)}</strong>
        <span>생성 시각</span>
        <strong>{self._text(report.generated_at)}</strong>
      </div>
    </header>

    {sections.summary}
    {sections.historical_notice}
    {sections.inventory}
    {sections.network_configuration}
    {sections.target_groups}
    {sections.server_details}
    {sections.monitoring}
    {sections.billing}
    {sections.organization_billing}
    {sections.insight_events}
    {sections.activity}
    {sections.diagnostics}

    <footer>
      <p>이 보고서는 구조화된 NCP 수집 결과로부터 생성되었습니다.</p>
    </footer>
  </main>
</body>
</html>
"""

    @staticmethod
    def _safe_customer_logo_data_uri(value: Any) -> str | None:
        try:
            return normalize_customer_logo_data_uri(value)
        except ValueError:
            # 변조되었거나 과거 형식인 스냅샷은 active content 대신 문자 로고로 대체한다.
            return None

    @staticmethod
    def _customer_initials(customer_name: str) -> str:
        words = [
            "".join(character for character in word if character.isalnum())
            for word in customer_name.split()
        ]
        words = [word for word in words if word]
        if len(words) >= 2:
            return "".join(word[0] for word in words[:2]).upper()
        if words:
            return words[0][:2].upper()
        return "NR"

    def write(self, report: ReportResult, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(report), encoding="utf-8")
        return path

    def _historical_inventory_notice(
        self,
        infrastructure_metadata: Mapping[str, Any],
    ) -> str:
        historical_filter = self._mapping(
            infrastructure_metadata.get("historical_filter")
        )
        infrastructure_filter = self._mapping(
            historical_filter.get("infrastructure")
        )
        excluded_count = infrastructure_filter.get(
            "excluded_after_period_count",
            0,
        )
        unknown_count = historical_filter.get(
            "unknown_create_time_count",
            infrastructure_filter.get("unknown_create_time_count", 0),
        )
        collected_at = self._infrastructure_create_time(
            infrastructure_metadata.get("completed_at")
            or infrastructure_metadata.get("started_at")
        )

        return f"""
    <section class="report-section warning historical-basis-notice" role="note">
      <div class="section-heading">
        <div>
          <h2>인프라 시간 기준 안내</h2>
          <p>보고 기간 안에 저장된 인프라 스냅샷이 없어 현재 자원 목록을 생성 시각으로 선별했습니다.</p>
        </div>
        <span class="count">PARTIAL</span>
      </div>
      <div class="historical-basis-grid">
        <div><span>목록 포함 기준</span><strong>보고 종료 전에 생성된 현재 자원</strong></div>
        <div><span>상태·IP·연결 정보</span><strong>보고서 생성 시점의 현재 값</strong></div>
        <div><span>시계열 그래프</span><strong>선별된 현재 자원의 보고 기간 메트릭</strong></div>
        <div><span>구성도</span><strong>현재 관계 기반 추정 · 보고 기간 당시 구성 아님</strong></div>
        <div><span>현재 목록 수집 시각</span><strong>{self._text(collected_at)}</strong></div>
        <div><span>기간 종료 후 생성 제외</span><strong>{self._text(excluded_count)}개</strong></div>
        <div><span>생성 시각 미확인</span><strong>{self._text(unknown_count)}개</strong></div>
      </div>
      <p class="historical-basis-caveat">보고 종료 후 삭제된 자원이나 변경 전 상태·IP·연결 관계는 복원되지 않으므로 정확한 과거 구성으로 해석해서는 안 됩니다.</p>
    </section>"""

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

    def _infrastructure_section(
        self,
        resources: List[Dict[str, Any]],
    ) -> str:
        allowed = {
            category for category, _ in self.INFRASTRUCTURE_CATEGORIES
        }
        counts = defaultdict(int)
        prepared = []

        for resource in self._records(resources):
            category = str(resource.get("category") or "").upper()
            if category not in allowed:
                continue
            counts[category] += 1
            details = resource.get("details")
            if not isinstance(details, dict):
                details = {}
            region_zone = " / ".join(
                str(value)
                for value in (
                    resource.get("region_code"),
                    resource.get("zone_code"),
                )
                if value
            )
            prepared.append({
                **resource,
                "location": region_zone or "-",
                "details_text": self._infrastructure_details_text(
                    details
                ),
                "create_time_text": self._infrastructure_create_time(
                    resource.get("create_time")
                ),
                "historical_presence_text": (
                    self._historical_confidence_text(
                        details.get("historical_presence_confidence")
                    )
                ),
            })

        summary_categories = [
            (category, label)
            for category, label in self.INFRASTRUCTURE_CATEGORIES
            if counts.get(category)
        ]
        summary_cards = "".join(
            f"""
      <article class="infra-summary-card">
        <span>{self._text(label)}</span>
        <strong>{counts.get(category, 0):,}</strong>
      </article>"""
            for category, label in summary_categories
        )
        columns = [
            ("category_label", "구분"),
            ("resource_name", "리소스명"),
            ("service_name", "서비스"),
            ("resource_type", "유형"),
            ("status", "상태"),
            ("location", "리전 / Zone"),
            ("details_text", "주요 구성"),
            ("create_time_text", "생성 시각 (KST)"),
        ]
        if any(
            self._mapping(resource.get("details")).get(
                "historical_presence_confidence"
            )
            for resource in prepared
        ):
            columns.append(
                ("historical_presence_text", "기간 존재 판단")
            )
        table = self._table(prepared, tuple(columns))
        summary = (
            f'<div class="infra-summary-grid">{summary_cards}</div>'
            if summary_cards else ""
        )
        content = summary + table
        return self._section(
            "대표 인프라 현황",
            (
                "실제 서비스 트래픽과 데이터를 처리하는 핵심 리소스만 "
                "표시합니다. IAM 서브계정과 알람·이벤트·정책 객체는 "
                "포함하지 않습니다."
            ),
            content,
            len(prepared),
        )

    def _network_configuration_section(
        self,
        resources: List[Dict[str, Any]],
        metadata: Mapping[str, Any],
    ) -> str:
        """Route Table·ACG·Network ACL을 단일 시점 백업으로 표시한다."""
        categories = set(NETWORK_CONFIGURATION_CATEGORY_OPTIONS)
        configurations = [
            resource
            for resource in self._records(resources)
            if str(resource.get("category") or "").upper() in categories
        ]
        captured_at = self._infrastructure_create_time(
            metadata.get("captured_at")
        )
        backup_captured_at = self._infrastructure_create_time(
            metadata.get("backup_captured_at")
        )
        in_period = metadata.get("is_report_period_snapshot") is True
        period_basis = (
            "보고 기간 내 단일 시점 관측"
            if in_period
            else "보고 기간 외 · 생성시점 현재 상태"
        )
        source_label = {
            "STORED_NETWORK_CONFIGURATION_SNAPSHOT": (
                "별도 저장된 과거 네트워크 스냅샷"
            ),
            "REPORT_GENERATION_SNAPSHOT": (
                "이번 보고서 생성 과정의 네트워크 스냅샷"
            ),
        }.get(str(metadata.get("source") or ""), "네트워크 구성 스냅샷")
        metadata_html = f"""
      <div class="network-snapshot-basis">
        <div><span>데이터 성격</span><strong>단일 시점 구성 백업</strong></div>
        <div><span>실제 수집 시각</span><strong>{self._text(captured_at)}</strong></div>
        <div><span>보고 기간과의 관계</span><strong>{self._text(period_basis)}</strong></div>
        <div><span>수집 계기</span><strong>보고서 생성 과정</strong></div>
        <div><span>표시 데이터 출처</span><strong>{self._text(source_label)}</strong></div>
        <div><span>이번 생성시점 백업 시각</span><strong>{self._text(backup_captured_at)}</strong></div>
      </div>"""

        summary_rows = []
        route_rows = []
        acg_rule_rows = []
        network_acl_rule_rows = []
        for resource in configurations:
            category = str(resource.get("category") or "").upper()
            details = self._mapping(resource.get("details"))
            summary_rows.append({
                "category": resource.get("category_label") or category,
                "name": resource.get("resource_name"),
                "id": resource.get("resource_id"),
                "vpc_no": details.get("vpc_no"),
                "status": resource.get("status"),
                "default": "기본" if details.get("default") is True else "-",
                "association_count": details.get(
                    "associated_subnet_count"
                ),
                "rule_count": details.get("rule_count")
                if category != "ROUTE_TABLE"
                else details.get("route_count"),
            })
            if category == "ROUTE_TABLE":
                subnet_names = ", ".join(
                    str(subnet.get("subnet_name") or subnet.get("subnet_no"))
                    for subnet in self._records(
                        details.get("associated_subnets")
                    )
                ) or "-"
                for route in self._records(details.get("routes")):
                    route_rows.append({
                        "route_table": resource.get("resource_name"),
                        "vpc_no": details.get("vpc_no"),
                        "subnets": subnet_names,
                        "destination": route.get("destination_cidr"),
                        "target_type": route.get("target_type"),
                        "target": route.get("target_name")
                        or route.get("target_no"),
                        "default": "기본" if route.get("default") is True else "-",
                    })
            elif category == "ACCESS_CONTROL_GROUP":
                for rule in self._records(details.get("rules")):
                    acg_rule_rows.append({
                        "group": resource.get("resource_name"),
                        "vpc_no": details.get("vpc_no"),
                        "direction": rule.get("direction"),
                        "protocol": rule.get("protocol"),
                        "source": rule.get("source_ip_block")
                        or rule.get("source_access_control_group_no"),
                        "port": rule.get("port_range"),
                        "description": rule.get("description"),
                    })
            elif category == "NETWORK_ACL":
                for rule in self._records(details.get("rules")):
                    network_acl_rule_rows.append({
                        "network_acl": resource.get("resource_name"),
                        "vpc_no": details.get("vpc_no"),
                        "priority": rule.get("priority"),
                        "direction": rule.get("direction"),
                        "protocol": rule.get("protocol"),
                        "source": rule.get("source_ip_block")
                        or rule.get("deny_allow_group_no"),
                        "port": rule.get("port_range"),
                        "action": rule.get("action"),
                        "description": rule.get("description"),
                    })

        tables = "".join((
            '<div class="network-config-group"><h3>구성 객체</h3>',
            self._table(
                summary_rows,
                (
                    ("category", "구분"),
                    ("name", "이름"),
                    ("id", "ID"),
                    ("vpc_no", "VPC No."),
                    ("status", "상태"),
                    ("default", "기본 여부"),
                    ("association_count", "연결 Subnet", "number0"),
                    ("rule_count", "규칙", "number0"),
                ),
            ),
            '</div><div class="network-config-group"><h3>Route 규칙</h3>',
            self._table(
                route_rows,
                (
                    ("route_table", "Route Table"),
                    ("vpc_no", "VPC No."),
                    ("subnets", "연결 Subnet"),
                    ("destination", "Destination CIDR"),
                    ("target_type", "Target 유형"),
                    ("target", "Target"),
                    ("default", "기본 여부"),
                ),
            ),
            '</div><div class="network-config-group"><h3>ACG 규칙</h3>',
            self._table(
                acg_rule_rows,
                (
                    ("group", "ACG"),
                    ("vpc_no", "VPC No."),
                    ("direction", "방향"),
                    ("protocol", "프로토콜"),
                    ("source", "접근 소스"),
                    ("port", "포트"),
                    ("description", "설명"),
                ),
            ),
            '</div><div class="network-config-group"><h3>Network ACL 규칙</h3>',
            self._table(
                network_acl_rule_rows,
                (
                    ("network_acl", "Network ACL"),
                    ("vpc_no", "VPC No."),
                    ("priority", "우선순위", "number0"),
                    ("direction", "방향"),
                    ("protocol", "프로토콜"),
                    ("source", "IP / Deny-Allow Group"),
                    ("port", "포트"),
                    ("action", "동작"),
                    ("description", "설명"),
                ),
            ),
            "</div>",
        ))
        description = (
            "보고 기간 안에 저장된 단일 시점의 Route Table·ACG·Network ACL "
            "구성입니다. 기간 전체의 변경 이력을 의미하지 않습니다."
            if in_period
            else (
                "보고 기간에 저장된 네트워크 스냅샷이 없어 이번 보고서 생성 "
                "과정에서 조회한 현재 설정을 별도로 백업했습니다. 아래 값은 "
                "보고 대상 기간의 과거 상태가 아닙니다."
            )
        )
        return self._section(
            "네트워크 구성 스냅샷",
            description,
            metadata_html + tables,
            len(configurations),
            warning=not in_period,
        )

    def _load_balancer_target_group_section(
        self,
        target_groups: List[Dict[str, Any]],
        infrastructure_metadata: Mapping[str, Any],
    ) -> str:
        collected_at = self._infrastructure_create_time(
            infrastructure_metadata.get("completed_at")
            or infrastructure_metadata.get("started_at")
        )
        rows = []
        for target_group in self._records(target_groups):
            details = self._mapping(target_group.get("details"))
            snapshot_available = details.get("health_snapshot_available")
            rows.append({
                "target_group_name": (
                    target_group.get("resource_name") or "-"
                ),
                "target_group_no": (
                    details.get("target_group_no")
                    or target_group.get("resource_id")
                ),
                "load_balancer_no": details.get(
                    "load_balancer_instance_no"
                ),
                "protocol_port": " / ".join(
                    str(value)
                    for value in (
                        details.get("protocol"),
                        details.get("port"),
                    )
                    if value is not None and str(value).strip()
                ) or "-",
                "registered": details.get("registered_target_count"),
                "ready": (
                    details.get("ready_target_count")
                    if snapshot_available is True else None
                ),
                "unready": (
                    details.get("unready_target_count")
                    if snapshot_available is True else None
                ),
                "unused": (
                    details.get("unused_target_count")
                    if snapshot_available is True else None
                ),
                "unknown": (
                    details.get("unknown_target_count")
                    if snapshot_available is True else None
                ),
                "snapshot_status": (
                    "수집됨"
                    if snapshot_available is True
                    else "수집 실패 또는 권한 없음"
                ),
                "collected_at": collected_at,
            })

        return self._section(
            "LB Target Group 상태",
            (
                "getTargetList의 현재 헬스체크 결과입니다. UP만 Ready, "
                "DOWN은 Unready, UNUSED는 헬스체크 미사용·미평가로 "
                "구분합니다. 보고 기간 추이는 아래 Cloud Insight 그래프의 "
                "Ready 최소값과 Unready 최대값으로 표시합니다."
            ),
            self._table(
                rows,
                (
                    ("target_group_name", "Target Group"),
                    ("target_group_no", "Target Group No."),
                    ("load_balancer_no", "LB No."),
                    ("protocol_port", "프로토콜 / 포트"),
                    ("registered", "등록", "number0"),
                    ("ready", "Ready (UP)", "number0"),
                    ("unready", "Unready (DOWN)", "number0"),
                    ("unused", "미평가 (UNUSED)", "number0"),
                    ("unknown", "알 수 없음", "number0"),
                    ("snapshot_status", "상태 수집"),
                    ("collected_at", "관측 시각"),
                ),
            ),
            len(rows),
            warning=any(
                self._mapping(group.get("details")).get(
                    "health_snapshot_available"
                ) is not True
                for group in self._records(target_groups)
            ),
        )

    def _infrastructure_details_text(self, value: Any) -> str:
        if not isinstance(value, dict):
            return "-"
        labels = (
            ("load_balancer_type", "LB 유형", ""),
            ("network_type", "네트워크", ""),
            ("protocol", "프로토콜", ""),
            ("engine", "엔진", ""),
            ("version", "버전", ""),
            ("server_count", "DB 서버", "개"),
            ("cpu_count_total", "총 vCPU", ""),
            ("memory_gb_total", "총 메모리", " GB"),
            ("data_storage_gb_total", "데이터 용량", " GB"),
            ("cpu_count", "vCPU", ""),
            ("memory_gb", "메모리", " GB"),
            ("size_gb", "용량", " GB"),
            ("storage_size_gb", "용량", " GB"),
            ("kubernetes_version", "Kubernetes", ""),
            ("node_count", "노드", "개"),
            ("node_pool_count", "노드풀", "개"),
            ("domain_count", "도메인", "개"),
            ("attached_server_name", "연결 서버", ""),
            ("high_availability", "HA", ""),
            ("multi_zone", "Multi Zone", ""),
        )
        parts = []
        for key, label, suffix in labels:
            item = value.get(key)
            if item is None or item == "":
                continue
            if isinstance(item, bool):
                item = "사용" if item else "미사용"
            parts.append(f"{label}: {item}{suffix}")
            if len(parts) == 5:
                break
        return " · ".join(parts) or "-"

    @staticmethod
    def _historical_confidence_text(value: Any) -> str:
        return {
            "INFERRED_FROM_CREATE_TIME": "생성 시각 기반 추정",
            "UNKNOWN": "생성 시각 미확인",
        }.get(str(value or "").upper(), "-")

    def _infrastructure_create_time(self, value: Any) -> str:
        timestamp = self._timestamp_millis(value)
        if timestamp is not None:
            parsed = datetime.fromtimestamp(timestamp / 1000, tz=self.KST)
            return parsed.strftime("%Y-%m-%d %H:%M KST")

        if not isinstance(value, str) or not value.strip():
            return "-"
        try:
            parsed = datetime.fromisoformat(
                value.strip().replace("Z", "+00:00")
            )
        except ValueError:
            return value.strip()
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=self.KST)
        return parsed.astimezone(self.KST).strftime("%Y-%m-%d %H:%M KST")

    def _infrastructure_metric_section(
        self,
        metric_groups: List[Dict[str, Any]],
        period: Dict[str, Any],
        infrastructure: List[Dict[str, Any]],
    ) -> str:
        monitored_categories = {
            category: (
                "Kubernetes"
                if category == "KUBERNETES"
                else RESOURCE_CATEGORY_LABELS.get(
                    category,
                    category.replace("_", " ").title(),
                )
            )
            for category in MONITORING_CATEGORY_OPTIONS
            if category != "SERVER"
        }
        present_categories = {
            str(item.get("category") or "").upper()
            for item in self._records(infrastructure)
        } & set(monitored_categories)
        groups = [
            group for group in self._records(metric_groups)
            if str(group.get("category") or "").upper()
            in monitored_categories
        ]

        if not present_categories and not groups:
            return ""

        cards = []
        rendered_categories = set()
        for group in groups:
            category = str(group.get("category") or "").upper()
            series = self._infrastructure_metric_series(group)
            interval = str(group.get("interval") or "Min5")
            aggregation = str(group.get("aggregation") or "AVG")
            unit = str(group.get("unit") or "")
            metric_label = str(
                group.get("metric_label")
                or group.get("metric")
                or "Metric"
            )
            resource_label = (
                "LB Target Group"
                if str(group.get("metric_scope") or "").upper()
                == "TARGET_GROUP"
                else monitored_categories[category]
            )
            title = f"{resource_label} · {metric_label}"
            product_name = str(group.get("product_name") or "Cloud Insight")
            description = (
                f"{product_name} · {self._metric_interval_label(interval)} "
                f"{aggregation}"
            )
            if unit:
                description += f" · 단위 {unit}"
            y_axis = (
                "fixed"
                if self._is_percent_unit(unit)
                else "auto"
            )
            cards.append(f"""
      <article class="chart-card">
        <div class="chart-heading">
          <h3>{self._text(title)}</h3>
          <p>{self._text(description)}</p>
        </div>
        {self._line_chart(
            title,
            series,
            period,
            y_axis,
            interval,
            unit=unit,
        )}
      </article>""")
            rendered_categories.add(category)

        for category in sorted(
            present_categories - rendered_categories,
            key=lambda item: tuple(monitored_categories).index(item),
        ):
            cards.append(f"""
      <article class="chart-card">
        <div class="chart-heading">
          <h3>{self._text(monitored_categories[category])}</h3>
          <p>Cloud Insight 모니터링 데이터 상태</p>
        </div>
        <p class="empty-state chart-empty">표시할 시계열이 없습니다. 권한, 모니터링 활성화 여부와 데이터 보관 기간을 확인하십시오.</p>
      </article>""")

        return f"""
    <section class="report-section infrastructure-trends">
      <div class="section-heading">
        <div>
          <h2>주요 인프라 모니터링</h2>
          <p>선택한 대표 인프라의 보고 기간 Cloud Insight 시계열입니다.</p>
        </div>
        <span class="count">{len(groups):,}개 그래프</span>
      </div>
      <div class="chart-grid">{''.join(cards)}</div>
    </section>"""

    def _infrastructure_metric_series(
        self,
        group: Dict[str, Any],
    ) -> Dict[str, List[Tuple[int, float]]]:
        result: Dict[str, List[Tuple[int, float]]] = {}
        for index, item in enumerate(self._records(group.get("series"))):
            points = sorted(self._metric_points(item), key=lambda point: point[0])
            if not points:
                continue
            label = str(
                item.get("resource_name")
                or item.get("resource_id")
                or f"resource-{index + 1}"
            )
            dimensions = item.get("dimensions")
            if isinstance(dimensions, dict):
                qualifier = (
                    dimensions.get("loadBalancerPort")
                    or dimensions.get("instanceName")
                    or dimensions.get("pod")
                    or dimensions.get("podName")
                    or dimensions.get("controller")
                    or dimensions.get("role")
                )
                if qualifier:
                    label = f"{label} · {qualifier}"
            unique_label = label
            suffix = 2
            while unique_label in result:
                unique_label = f"{label} ({suffix})"
                suffix += 1
            result[unique_label] = points
        return result

    @staticmethod
    def _is_percent_unit(unit: str) -> bool:
        return unit.strip().casefold() in {"%", "percent", "percentage"}

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
        }.get(interval, str(interval or "집계 주기 미상"))

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
        }.get(interval, 5 * 60 * 1000)

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
        unit: str = "%",
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
            tick_label = self._chart_value_text(tick, unit, compact=True)
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
                segment = self._downsample_chart_points(
                    segment,
                    max_points=self.MAX_CHART_POINTS_PER_SEGMENT,
                )
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
                            f"{self._text(self._chart_value_text(value, unit))}"
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

    def _chart_value_text(
        self,
        value: float,
        unit: str,
        compact: bool = False,
    ) -> str:
        unit_text = str(unit or "").strip()
        normalized = unit_text.casefold().replace(" ", "")

        if normalized in {"%", "percent", "percentage"}:
            precision = 0 if compact or abs(value) >= 1 else 1
            return f"{value:.{precision}f}%"

        byte_rate_units = {
            "b/s", "byte/s", "bytes/s", "byte/sec", "bytes/sec",
            "bps",
        }
        byte_units = {"b", "byte", "bytes"}
        if normalized in byte_rate_units or normalized in byte_units:
            suffix = "/s" if normalized in byte_rate_units else ""
            scaled = float(value)
            prefix = "B"
            for candidate in ("KiB", "MiB", "GiB", "TiB"):
                if abs(scaled) < 1024:
                    break
                scaled /= 1024
                prefix = candidate
            precision = 0 if compact and abs(scaled) >= 10 else 1
            return f"{scaled:,.{precision}f} {prefix}{suffix}"

        if compact:
            absolute = abs(value)
            for divisor, suffix in (
                (1_000_000_000, "B"),
                (1_000_000, "M"),
                (1_000, "K"),
            ):
                if absolute >= divisor:
                    return f"{value / divisor:.1f}{suffix}"

        number = (
            f"{value:,.0f}"
            if abs(value) >= 1 or value == 0
            else f"{value:,.2f}"
        )
        if normalized in {"", "num", "number", "count", "ea"}:
            return number
        if normalized in {"num/s", "number/s", "count/s", "count/sec"}:
            return f"{number}/s"
        return f"{number} {unit_text}"

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

    @staticmethod
    def _downsample_chart_points(
        points: List[Tuple[int, float]],
        max_points: int,
    ) -> List[Tuple[int, float]]:
        """Bound SVG size while preserving the first, last, min and max."""
        if max_points <= 0:
            return []
        if len(points) <= max_points:
            return list(points)
        if max_points == 1:
            return [points[0]]
        if max_points == 2:
            return [points[0], points[-1]]

        bucket_count = max((max_points - 2) // 2, 1)
        interior = points[1:-1]
        bucket_size = max(math.ceil(len(interior) / bucket_count), 1)
        selected = [points[0]]
        for start in range(0, len(interior), bucket_size):
            bucket = interior[start:start + bucket_size]
            extrema = {
                min(range(len(bucket)), key=lambda index: bucket[index][1]),
                max(range(len(bucket)), key=lambda index: bucket[index][1]),
            }
            selected.extend(bucket[index] for index in sorted(extrema))
        selected.append(points[-1])
        if len(selected) <= max_points:
            return selected

        # Rounding can create one extra bucket. Keep the temporal endpoints.
        interior_limit = max_points - 2
        return [selected[0], *selected[1:-1][:interior_limit], selected[-1]]

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
            "MONTH_TO_DATE_ESTIMATE": "보고 기준일까지 누적 추정 데이터",
            "MONTH_END_PROJECTION": "월 전체 금액 (1일~말일)",
        }
        basis_labels = {
            "INVOICE_TOTAL": "NCP 발행 청구서 총액",
            "CURRENT_MONTH_INVOICE_TOTAL": "NCP 해당 월 확정 금액 (VAT 포함)",
            "PRE_DISCOUNT_LIST_PRICE": "사용량 × 단가 (할인·VAT 전)",
            "DAILY_RUN_RATE_PROJECTION": "월 누적 일평균 추세 예측",
            "NCP_PRODUCT_DEMAND_USE_AMOUNT": "NCP 서비스별 누적 사용금액 (할인·VAT 전)",
            "NCP_CONTRACT_DEMAND_USE_AMOUNT": (
                "NCP 계약별 사용금액 fallback (할인·VAT 전)"
            ),
            "NCP_CURRENT_USE_AMOUNT_FALLBACK": (
                "NCP 현재월 반환 사용금액 (복합요금 fallback)"
            ),
            "PROJECTED_USAGE_RERATED": "월말 예상 사용량에 요금제를 다시 적용",
            "NCP_ACCRUED_PLUS_USAGE_FORECAST": "NCP 누적 사용금액 + 월말 사용량 예측",
            "NCP_ACCRUED_LOWER_BOUND": (
                "NCP 현재 누적 사용금액 (복합요금 월말 하한)"
            ),
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
            estimate_quality = ""
            if fact.get("cost_type") != "CONFIRMED":
                details = self._mapping(fact.get("details"))
                estimate_quality = (
                    "<li><span>계산 품질</span><strong>"
                    f"제외 {self._number(fact.get('excluded_item_count') or 0, 0)}개 / "
                    f"추론 {self._number(details.get('inferred_item_count') or 0, 0)}개"
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
                f"{estimate_quality}"
                f"{invoice_breakdown}"
                "</ul></article>"
            )
        return '<div class="billing-facts">' + "".join(cards) + "</div>"

    def _organization_cost_sections(
        self, accounts: List[Dict[str, Any]]
    ) -> str:
        if not accounts:
            return ""
        articles = []
        for account in accounts:
            facts = {
                str(item.get("cost_type")): item
                for item in self._records(account.get("cost_facts"))
            }
            confirmed = facts.get("CONFIRMED", {})
            current_provisional = facts.get("CURRENT_PROVISIONAL", {})
            projection = facts.get("MONTH_END_PROJECTION", {})
            confirmed_services = self._records(account.get("service_summary"))
            expected_services = self._records(
                account.get("current_service_summary")
            )
            confirmed_text = (
                self._number(confirmed.get("total_amount"), 0) + "원"
                if confirmed.get("total_amount") is not None else "조회 불가"
            )
            provisional_text = (
                self._number(current_provisional.get("total_amount"), 0) + "원"
                if current_provisional.get("total_amount") is not None
                else "해당 없음"
            )
            projection_text = (
                self._number(projection.get("total_amount"), 0) + "원"
                if projection.get("total_amount") is not None else "해당 없음"
            )
            metrics = (
                f"<li><span>확정 청구액</span><strong>{confirmed_text}</strong></li>"
                f"<li><span>NCP 현재월 누적 예상(VAT 전)</span><strong>{provisional_text}</strong></li>"
                f"<li><span>월말 단순 예측(참고)</span><strong>{projection_text}</strong></li>"
            )
            articles.append(
                '<article class="billing-fact organization-account">'
                f"<h3>{self._text(account.get('display_name') or account.get('member_no'))}"
                f" <small>{self._text(account.get('member_no'))}</small></h3>"
                f"<ul>{metrics}</ul>"
                "<h4>확정 서비스별 비용</h4>"
                + self._table(confirmed_services, (
                    ("service_name", "서비스"), ("amount", "금액", "number0"),
                    ("row_count", "항목", "number0"),
                ))
                + "<h4>NCP 현재월 서비스별 예상 비용</h4>"
                + self._table(expected_services, (
                    ("service_name", "서비스"), ("amount", "금액(VAT 전)", "number0"),
                    ("row_count", "항목", "number0"),
                ))
                + "</article>"
            )
        return self._section(
            "Organization 계정별 비용",
            "Organization 마스터 계정으로 확인된 경우에만 하위 계정별 비용을 표시합니다.",
            '<div class="billing-facts">' + "".join(articles) + "</div>",
            len(accounts),
        )

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
        return HTML_REPORT_STYLES

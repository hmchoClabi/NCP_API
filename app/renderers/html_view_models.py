"""HTML 렌더링 단계 사이에 전달하는 불변 표시 모델."""

from dataclasses import dataclass
from typing import Any, Dict, List

from app.report_options import ReportOptions


@dataclass(frozen=True, slots=True)
class BillingDisplayData:
    """HTML 과금 섹션에 필요한 표시 기준과 집계 결과."""

    cost_facts: List[Dict[str, Any]]
    account_costs: List[Dict[str, Any]]
    service_summary: List[Dict[str, Any]]
    card_title: str
    card_amount: Any
    section_title: str
    section_description: str
    usage_summary: List[Dict[str, Any]]
    network_summary: List[Dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ReportDisplayData:
    """보고서 원본에서 HTML 조립에 필요한 값만 정규화한 표시 모델."""

    period: Dict[str, Any]
    report_options: ReportOptions
    report_title: str
    customer_name: str
    customer_logo_data_uri: str | None
    customer_initials: str
    billing: BillingDisplayData
    activity_events: List[Dict[str, Any]]
    infrastructure: List[Dict[str, Any]]
    inventory_enabled: bool
    monitoring_enabled: bool
    billing_enabled: bool
    organization_billing_enabled: bool
    network_configuration_metadata: Dict[str, Any]


@dataclass(frozen=True, slots=True)
class InfrastructureSectionHtml:
    """인프라 관련 섹션을 최종 문서 순서대로 보관한다."""

    inventory: str = ""
    network_configuration: str = ""


@dataclass(frozen=True, slots=True)
class EventDiagnosticSectionHtml:
    """이벤트·활동 이력·수집 진단 섹션 묶음."""

    insight_events: str = ""
    activity: str = ""
    diagnostics: str = ""


@dataclass(frozen=True, slots=True)
class ReportSectionHtml:
    """최종 HTML 본문에 삽입되는 모든 섹션."""

    summary: str = ""
    inventory: str = ""
    network_configuration: str = ""
    monitoring: str = ""
    billing: str = ""
    organization_billing: str = ""
    insight_events: str = ""
    activity: str = ""
    diagnostics: str = ""

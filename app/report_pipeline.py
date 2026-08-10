"""보고서 실행 파이프라인에서 단계 사이에 전달하는 명시적 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, FrozenSet, List, Optional

from app.report_options import ReportOptions


@dataclass(frozen=True)
class ReportCollectionPlan:
    """고객별 보고서 옵션을 실제 수집 범위로 해석한 불변 계획."""

    report_options: ReportOptions
    report_options_snapshot: Dict[str, Any]
    selected_resource_categories: FrozenSet[str]
    selected_monitoring_categories: FrozenSet[str]
    diagram_enabled: bool
    monitoring_enabled: bool
    monitored_infrastructure_categories: FrozenSet[str]
    collection_resource_categories: FrozenSet[str]
    needs_infrastructure_collection: bool
    needs_resource_snapshot: bool


@dataclass(frozen=True)
class SnapshotDecision:
    """보고 기간에 사용할 저장/실시간 스냅샷 선택 결과."""

    observation_check_at: str
    request_window: Optional[Dict[str, datetime]]
    live_snapshot_in_period: bool
    current_state_period_fallback: bool
    period_snapshot: Optional[Dict[str, Any]]
    lookup_warning: Optional[Dict[str, Any]]
    needs_server_collection: bool


@dataclass
class ResourceCollectionResult:
    """서버와 대표 인프라 수집 단계에서 만들어지는 상태."""

    servers: List[Dict[str, Any]] = field(default_factory=list)
    server_errors: List[Dict[str, Any]] = field(default_factory=list)
    server_raw_data: Dict[str, Any] = field(default_factory=dict)
    infrastructure: List[Dict[str, Any]] = field(default_factory=list)
    infrastructure_errors: List[Dict[str, Any]] = field(default_factory=list)
    infrastructure_warnings: List[Dict[str, Any]] = field(default_factory=list)
    collection_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ObservabilityResult:
    """모니터링과 이벤트 수집 단계의 결과 묶음."""

    server_metrics: List[Dict[str, Any]] = field(default_factory=list)
    infrastructure_metrics: List[Dict[str, Any]] = field(default_factory=list)
    insight_events: List[Dict[str, Any]] = field(default_factory=list)
    grouped_insight_events: Dict[str, List[Dict[str, Any]]] = field(
        default_factory=dict
    )
    activity_events: Dict[str, Any] = field(default_factory=dict)
    activity_errors: List[Dict[str, Any]] = field(default_factory=list)
    insight_event_errors: List[Dict[str, Any]] = field(default_factory=list)
    insight_errors: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)


def build_collection_plan(report_options: ReportOptions) -> ReportCollectionPlan:
    """표시 옵션을 수집기 실행 여부와 자원 범주로 변환한다.

    표시 범위와 수집 범위는 같지 않다. 예를 들어 구성도에만 필요한 자원과
    모니터링에 필요한 TARGET_GROUP은 화면 옵션에 직접 노출되지 않아도 먼저
    수집해야 하므로 이 판단을 렌더러가 아니라 파이프라인 입구에서 고정한다.
    """
    snapshot = report_options.to_dict()
    selected_resources = frozenset(snapshot["resource_categories"])
    selected_monitoring = frozenset(snapshot["monitoring_categories"])
    inventory_enabled = report_options.section_enabled(
        "infrastructure_inventory"
    )
    diagram_enabled = (
        report_options.section_enabled("infrastructure_diagram")
        and bool(report_options.diagram_option("enabled", True))
    )
    monitoring_enabled = report_options.section_enabled("monitoring")
    active_monitoring = (
        selected_monitoring if monitoring_enabled else frozenset()
    )
    monitored_infrastructure = active_monitoring - {"SERVER"}
    collection_resources = set(active_monitoring)
    if inventory_enabled or diagram_enabled:
        collection_resources.update(selected_resources)

    collection_resource_categories = frozenset(collection_resources)
    needs_infrastructure = bool(collection_resource_categories)
    needs_snapshot = needs_infrastructure or (
        monitoring_enabled and "SERVER" in selected_monitoring
    )
    return ReportCollectionPlan(
        report_options=report_options,
        report_options_snapshot=snapshot,
        selected_resource_categories=selected_resources,
        selected_monitoring_categories=selected_monitoring,
        diagram_enabled=diagram_enabled,
        monitoring_enabled=monitoring_enabled,
        monitored_infrastructure_categories=frozenset(
            monitored_infrastructure
        ),
        collection_resource_categories=collection_resource_categories,
        needs_infrastructure_collection=needs_infrastructure,
        needs_resource_snapshot=needs_snapshot,
    )

"""보고서에 표시할 인프라 토폴로지의 시간·신뢰도 정책을 관리한다.

과거 기간의 삭제·변경된 자원 관계는 현재 API 응답만으로 복원할 수 없다.
따라서 검증된 기간 스냅샷이 없으면 과거 상태를 임의로 만들지 않고 명시적인
현재 상태 fallback 또는 UNAVAILABLE 결과만 반환한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Mapping
from zoneinfo import ZoneInfo

from app.infrastructure_topology import (
    InfrastructureTopologyBuilder,
    apply_topology_presentation_policy,
)
from app.report_period import (
    build_snapshot_eligibility_window,
    normalize_period_bounds,
    snapshot_window_metadata,
)

if TYPE_CHECKING:
    from app.report_models import ReportResult


class ReportTopologyPolicy:
    """저장 토폴로지와 fallback 중 표시 가능한 결과를 보수적으로 선택한다."""

    CURRENT_STATE_TOPOLOGY_TIME_BASIS = (
        "CURRENT_STATE_FILTERED_BY_CREATE_TIME"
    )

    def __init__(self, report: ReportResult) -> None:
        self._report = report

    @property
    def display_infrastructure_topology(self) -> Dict[str, Any]:
        """명시적으로 수집된 리소스 ID만 사용해 표시할 토폴로지를 선택한다."""
        options = self._report.selected_report_options
        if (
            not options.section_enabled("infrastructure_diagram")
            or not bool(options.diagram_option("enabled", True))
        ):
            return {}
        metadata = (
            self._report.collection_metadata
            if isinstance(self._report.collection_metadata, dict)
            else {}
        )
        infrastructure_metadata = metadata.get("infrastructure")
        if not isinstance(infrastructure_metadata, dict):
            infrastructure_metadata = {}
        metadata_time_basis = str(
            infrastructure_metadata.get("time_basis") or "REPORT_PERIOD"
        ).strip().upper()
        if (
            isinstance(self._report.infrastructure_topology, dict)
            and isinstance(self._report.infrastructure_topology.get("nodes"), list)
            and isinstance(self._report.infrastructure_topology.get("edges"), list)
            and isinstance(self._report.infrastructure_topology.get("summary"), dict)
        ):
            topology_summary = self._report.infrastructure_topology["summary"]
            topology_confidence = str(
                topology_summary.get("confidence") or ""
            ).strip().upper()
            topology_time_basis = str(
                topology_summary.get("time_basis") or metadata_time_basis
            ).strip().upper()
            if (
                topology_confidence == "UNAVAILABLE"
                and metadata_time_basis
                == self.CURRENT_STATE_TOPOLOGY_TIME_BASIS
            ):
                topology_time_basis = metadata_time_basis
            reference_at = (
                topology_summary.get("reference_at")
                or self._infrastructure_reference_at()
            )
            if topology_time_basis == self.CURRENT_STATE_TOPOLOGY_TIME_BASIS:
                if not self._current_state_topology_is_valid(
                    topology_summary,
                    infrastructure_metadata,
                ):
                    return self._period_snapshot_unavailable_topology(
                        collected_at=topology_summary.get("collected_at"),
                        source=str(
                            topology_summary.get("snapshot_source")
                            or infrastructure_metadata.get("source")
                            or "UNAVAILABLE"
                        ),
                        max_nodes=options.diagram_option("max_nodes"),
                        reference_at=reference_at,
                    )
                if (
                    str(topology_summary.get("confidence") or "").upper()
                    != "UNAVAILABLE"
                    and self._report.infrastructure_topology.get("nodes")
                ):
                    return apply_topology_presentation_policy(
                        self._report.infrastructure_topology
                    )
                # 이전 버전이 저장한 UNAVAILABLE 자리표시자만 현재 상태 fallback으로
                # 다시 계산한다. 검증된 과거 구성을 현재 값으로 덮어쓰지는 않는다.
            elif (
                self._has_period_bounds()
                and str(
                    topology_summary.get("confidence") or ""
                ).upper() != "UNAVAILABLE"
                and not self._observed_inside_reference_window(
                    topology_summary.get("collected_at"),
                    reference_at,
                )
            ):
                return self._period_snapshot_unavailable_topology(
                    collected_at=topology_summary.get("collected_at"),
                    source=str(
                        topology_summary.get("snapshot_source")
                        or "UNAVAILABLE"
                    ),
                    max_nodes=options.diagram_option("max_nodes"),
                    reference_at=reference_at,
                )
            else:
                return apply_topology_presentation_policy(
                    self._report.infrastructure_topology
                )

        collected_at = (
            infrastructure_metadata.get("completed_at")
            or infrastructure_metadata.get("started_at")
        )
        reference_at = (
            infrastructure_metadata.get("reference_at")
            or self._report.generated_at
        )
        current_state_fallback = (
            metadata_time_basis == self.CURRENT_STATE_TOPOLOGY_TIME_BASIS
        )
        if current_state_fallback:
            if not self._current_state_topology_is_valid(
                {
                    "time_basis": metadata_time_basis,
                    "snapshot_source": infrastructure_metadata.get("source"),
                    "collected_at": collected_at,
                },
                infrastructure_metadata,
            ):
                return self._period_snapshot_unavailable_topology(
                    collected_at=collected_at,
                    source=str(
                        infrastructure_metadata.get("source") or "UNAVAILABLE"
                    ),
                    max_nodes=options.diagram_option("max_nodes"),
                    reference_at=reference_at,
                )
        elif (
            self._has_period_bounds()
            and not self._observed_inside_reference_window(
                collected_at,
                reference_at,
            )
        ):
            return self._period_snapshot_unavailable_topology(
                collected_at=collected_at,
                source=str(
                    infrastructure_metadata.get("source") or "UNAVAILABLE"
                ),
                max_nodes=options.diagram_option("max_nodes"),
                reference_at=reference_at,
            )
        topology = InfrastructureTopologyBuilder().build(
            self._report.display_infrastructure,
            collected_at=(str(collected_at) if collected_at else None),
            max_nodes=options.diagram_option("max_nodes"),
            allowed_reference_categories=options.to_dict()[
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
        if current_state_fallback:
            summary.update({
                "time_basis": self.CURRENT_STATE_TOPOLOGY_TIME_BASIS,
                "snapshot_source": "CURRENT_API_COLLECTION",
                "period_start": self._report.period.get("start_dt"),
                "period_end": self._report.period.get("end_dt"),
                "reference_at": infrastructure_metadata.get("reference_at"),
                "eligible_start": None,
                "eligible_end": None,
                "snapshot_age_seconds": None,
                "confidence": "PARTIAL",
            })
            topology.setdefault("warnings", []).insert(
                0,
                self._current_state_topology_warning(),
            )
        else:
            summary.update(
                self._snapshot_window_metadata(reference_at, collected_at)
            )
            summary["time_basis"] = "REPORT_PERIOD"
            summary["snapshot_source"] = str(
                infrastructure_metadata.get("source") or "UNAVAILABLE"
            )
        return apply_topology_presentation_policy(topology)

    def _has_period_bounds(self) -> bool:
        return bool(
            self._report.period.get("start_dt")
            and self._report.period.get("end_dt")
        )

    def _current_state_topology_is_valid(
        self,
        topology_summary: Mapping[str, Any],
        infrastructure_metadata: Mapping[str, Any],
    ) -> bool:
        """현재 상태 fallback이 명시된 동일 수집 결과인지 검증한다.

        수집 시각과 메타데이터가 정확히 일치하지 않으면 현재 관계를 과거 관계로
        오인할 수 있으므로 사용할 수 없는 토폴로지로 처리한다.
        """
        metadata_time_basis = str(
            infrastructure_metadata.get("time_basis") or ""
        ).strip().upper()
        if metadata_time_basis != self.CURRENT_STATE_TOPOLOGY_TIME_BASIS:
            return False

        summary_time_basis = str(
            topology_summary.get("time_basis") or metadata_time_basis
        ).strip().upper()
        summary_confidence = str(
            topology_summary.get("confidence") or ""
        ).strip().upper()
        if (
            summary_time_basis != self.CURRENT_STATE_TOPOLOGY_TIME_BASIS
            and summary_confidence != "UNAVAILABLE"
        ):
            return False

        metadata_source = str(
            infrastructure_metadata.get("source") or ""
        ).strip().upper()
        summary_source = str(
            topology_summary.get("snapshot_source") or metadata_source
        ).strip().upper()
        if (
            metadata_source != "CURRENT_API_COLLECTION"
            or summary_source != "CURRENT_API_COLLECTION"
        ):
            return False

        observed_at = topology_summary.get("collected_at")
        metadata_observed_at = (
            infrastructure_metadata.get("completed_at")
            or infrastructure_metadata.get("started_at")
        )
        if not observed_at or not metadata_observed_at:
            return False
        try:
            observed = self._parse_kst_datetime(observed_at)
            metadata_observed = self._parse_kst_datetime(
                metadata_observed_at
            )
            generated = self._parse_kst_datetime(self._report.generated_at)
        except (TypeError, ValueError):
            return False
        return observed == metadata_observed and observed <= generated

    @staticmethod
    def _current_state_topology_warning() -> Dict[str, str]:
        return {
            "code": "CURRENT_STATE_TOPOLOGY_FALLBACK",
            "message": (
                "보고 기간 안에 저장된 인프라 스냅샷이 없어, 보고 종료 "
                "전에 생성된 것으로 확인되는 현재 자원의 연결 관계를 "
                "표시합니다. 삭제되었거나 변경된 과거 구성은 복원되지 "
                "않으므로 보고 기간 당시의 정확한 구성으로 해석해서는 "
                "안 됩니다."
            ),
            "source": "current_api_collection",
            "confidence": "PARTIAL",
        }

    def _infrastructure_reference_at(self) -> Any:
        metadata = (
            self._report.collection_metadata
            if isinstance(self._report.collection_metadata, dict)
            else {}
        )
        infrastructure_metadata = metadata.get("infrastructure")
        if isinstance(infrastructure_metadata, dict):
            reference_at = infrastructure_metadata.get("reference_at")
            if reference_at:
                return reference_at
        return self._report.generated_at

    def _period_bounds_kst(self) -> tuple[datetime, datetime]:
        start = self._parse_kst_datetime(self._report.period["start_dt"])
        end = self._parse_kst_datetime(self._report.period["end_dt"])
        return normalize_period_bounds(
            start,
            end,
            end_exclusive=bool(self._report.period.get("end_exclusive")),
        )

    def _snapshot_eligibility_window(
        self,
        reference_at: Any,
    ) -> Dict[str, datetime] | None:
        try:
            start, end = self._period_bounds_kst()
            reference = self._parse_kst_datetime(reference_at)
        except (KeyError, TypeError, ValueError):
            return None
        return build_snapshot_eligibility_window(start, end, reference)

    def _observed_inside_reference_window(
        self,
        observed_at: Any,
        reference_at: Any,
    ) -> bool:
        if not observed_at:
            return False
        try:
            observed = self._parse_kst_datetime(observed_at)
        except (TypeError, ValueError):
            return False
        window = self._snapshot_eligibility_window(reference_at)
        return bool(
            window
            and window["eligible_start"] <= observed < window["eligible_end"]
        )

    def _snapshot_window_metadata(
        self,
        reference_at: Any,
        observed_at: Any = None,
    ) -> Dict[str, Any]:
        window = self._snapshot_eligibility_window(reference_at)
        try:
            observed = self._parse_kst_datetime(observed_at)
        except (TypeError, ValueError):
            observed = None
        return snapshot_window_metadata(window, observed)

    @staticmethod
    def _parse_kst_datetime(value: Any) -> datetime:
        normalized = str(value).strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        parsed = datetime.fromisoformat(normalized)
        kst = ZoneInfo("Asia/Seoul")
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=kst)
        return parsed.astimezone(kst)

    def _period_snapshot_unavailable_topology(
        self,
        *,
        collected_at: Any,
        source: str,
        max_nodes: Any,
        reference_at: Any = None,
    ) -> Dict[str, Any]:
        window_metadata = self._snapshot_window_metadata(
            reference_at or self._report.generated_at,
            collected_at,
        )
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
                "collected_at": collected_at,
                "max_nodes": max_nodes,
                "truncated": False,
                "omitted_node_count": 0,
                "confidence": "UNAVAILABLE",
                "time_basis": "REPORT_PERIOD",
                "snapshot_source": source,
                "period_start": self._report.period.get("start_dt"),
                "period_end": self._report.period.get("end_dt"),
                **window_metadata,
            },
        }

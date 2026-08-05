from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping
from zoneinfo import ZoneInfo


@dataclass
class ReportResult:
    """Delivery-neutral result produced by the NCP report pipeline."""

    period: Dict[str, Any]
    customer: Dict[str, Any] = field(default_factory=dict)
    servers: List[Dict[str, Any]] = field(default_factory=list)
    server_metrics: List[Dict[str, Any]] = field(default_factory=list)
    insight_events: List[Dict[str, Any]] = field(default_factory=list)
    grouped_insight_events: Dict[str, List[Dict[str, Any]]] = field(
        default_factory=dict
    )
    activity_events: Any = field(default_factory=dict)
    billing: Dict[str, Any] = field(default_factory=dict)
    collection_errors: List[Dict[str, Any]] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.now(
            ZoneInfo("Asia/Seoul")
        ).isoformat(timespec="seconds")
    )

    @property
    def report_id(self) -> str:
        return str(self.period.get("file_suffix", "report"))

    @property
    def display_server_metrics(self) -> List[Dict[str, Any]]:
        return [
            {
                key: value
                for key, value in metric.items()
                if key != "raw_metrics"
            }
            for metric in self.server_metrics
            if isinstance(metric, dict)
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "1.0",
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "customer": self.customer,
            "period": self.period,
            "servers": self.servers,
            "server_metrics": self.display_server_metrics,
            "insight_events": self.insight_events,
            "grouped_insight_events": self.grouped_insight_events,
            "activity_events": self.activity_events,
            "billing": self.billing,
            "collection_errors": self.collection_errors,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReportResult":
        """Rehydrate a persisted normalized snapshot for deterministic rendering."""
        if not isinstance(payload, Mapping):
            raise ValueError("Report snapshot must be an object.")
        period = payload.get("period")
        if not isinstance(period, dict):
            raise ValueError("Report snapshot does not contain a valid period.")
        return cls(
            period=period,
            customer=payload.get("customer") or {},
            servers=payload.get("servers") or [],
            server_metrics=payload.get("server_metrics") or [],
            insight_events=payload.get("insight_events") or [],
            grouped_insight_events=(
                payload.get("grouped_insight_events") or {}
            ),
            activity_events=payload.get("activity_events") or {},
            billing=payload.get("billing") or {},
            collection_errors=payload.get("collection_errors") or [],
            generated_at=str(payload.get("generated_at") or "-"),
        )

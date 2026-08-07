from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Dict, List, Mapping
from zoneinfo import ZoneInfo


@dataclass
class ReportResult:
    """Delivery-neutral result produced by the NCP report pipeline."""

    DISPLAY_INFRASTRUCTURE_CATEGORIES: ClassVar[frozenset[str]] = frozenset({
        "SERVER",
        "LOAD_BALANCER",
        "BLOCK_STORAGE",
        "OBJECT_STORAGE",
        "NAS",
        "CLOUD_DB",
        "CDN",
        "KUBERNETES",
    })
    MONITORED_INFRASTRUCTURE_CATEGORIES: ClassVar[frozenset[str]] = (
        frozenset({"LOAD_BALANCER", "CLOUD_DB", "KUBERNETES"})
    )

    period: Dict[str, Any]
    customer: Dict[str, Any] = field(default_factory=dict)
    servers: List[Dict[str, Any]] = field(default_factory=list)
    server_metrics: List[Dict[str, Any]] = field(default_factory=list)
    infrastructure: List[Dict[str, Any]] = field(default_factory=list)
    infrastructure_metrics: List[Dict[str, Any]] = field(default_factory=list)
    insight_events: List[Dict[str, Any]] = field(default_factory=list)
    grouped_insight_events: Dict[str, List[Dict[str, Any]]] = field(
        default_factory=dict
    )
    activity_events: Any = field(default_factory=dict)
    billing: Dict[str, Any] = field(default_factory=dict)
    collection_errors: List[Dict[str, Any]] = field(default_factory=list)
    collection_warnings: List[Dict[str, Any]] = field(default_factory=list)
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

    @property
    def display_infrastructure(self) -> List[Dict[str, Any]]:
        """Return the infrastructure inventory with legacy server fallback."""
        filtered = [
            item for item in self.infrastructure
            if (
                isinstance(item, dict)
                and str(item.get("category") or "").upper()
                in self.DISPLAY_INFRASTRUCTURE_CATEGORIES
            )
        ]
        if filtered:
            return filtered

        return [
            {
                "category": "SERVER",
                "category_label": "서버",
                "service_name": "Server",
                "resource_type": "ServerInstance",
                "resource_id": server.get("server_id"),
                "resource_name": server.get("server_name"),
                "status": server.get("status"),
                "region_code": server.get("region_code"),
                "zone_code": server.get("zone_code"),
                "platform": "VPC",
                "create_time": server.get("create_date"),
                "details": {},
            }
            for server in self.servers
            if isinstance(server, dict)
        ]

    @property
    def display_infrastructure_metrics(self) -> List[Dict[str, Any]]:
        """Return only metric groups supported by the infrastructure report."""
        return [
            item for item in self.infrastructure_metrics
            if (
                isinstance(item, dict)
                and str(item.get("category") or "").upper()
                in self.MONITORED_INFRASTRUCTURE_CATEGORIES
            )
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "1.2",
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "customer": self.customer,
            "period": self.period,
            "servers": self.servers,
            "server_metrics": self.display_server_metrics,
            "infrastructure": self.display_infrastructure,
            "infrastructure_metrics": self.display_infrastructure_metrics,
            "insight_events": self.insight_events,
            "grouped_insight_events": self.grouped_insight_events,
            "activity_events": self.activity_events,
            "billing": self.billing,
            "collection_errors": self.collection_errors,
            "collection_warnings": self.collection_warnings,
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
            infrastructure=payload.get("infrastructure") or [],
            infrastructure_metrics=(
                payload.get("infrastructure_metrics") or []
            ),
            insight_events=payload.get("insight_events") or [],
            grouped_insight_events=(
                payload.get("grouped_insight_events") or {}
            ),
            activity_events=payload.get("activity_events") or {},
            billing=payload.get("billing") or {},
            collection_errors=payload.get("collection_errors") or [],
            collection_warnings=payload.get("collection_warnings") or [],
            generated_at=str(payload.get("generated_at") or "-"),
        )

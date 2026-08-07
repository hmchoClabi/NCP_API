from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, ClassVar, Dict, List, Mapping
from zoneinfo import ZoneInfo

from app.infrastructure_topology import (
    InfrastructureTopologyBuilder,
    REPRESENTATIVE_CATEGORIES,
)
from app.report_options import (
    MONITORING_CATEGORY_OPTIONS,
    ReportOptions,
    legacy_report_options,
)


@dataclass
class ReportResult:
    """Delivery-neutral result produced by the NCP report pipeline."""

    DISPLAY_INFRASTRUCTURE_CATEGORIES: ClassVar[frozenset[str]] = frozenset(
        REPRESENTATIVE_CATEGORIES
    )
    MONITORED_INFRASTRUCTURE_CATEGORIES: ClassVar[frozenset[str]] = (
        frozenset(MONITORING_CATEGORY_OPTIONS) - {"SERVER"}
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
    report_options: Dict[str, Any] = field(default_factory=dict)
    collection_metadata: Dict[str, Any] = field(default_factory=dict)
    infrastructure_topology: Dict[str, Any] = field(default_factory=dict)
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
    def selected_report_options(self) -> ReportOptions:
        raw_options: Any = self.report_options
        if not raw_options and isinstance(self.customer, dict):
            raw_options = self.customer.get("report_options")
        return ReportOptions.from_value(raw_options)

    @property
    def display_server_metrics(self) -> List[Dict[str, Any]]:
        options = self.selected_report_options
        if (
            not options.section_enabled("monitoring")
            or not options.monitoring_enabled("SERVER")
        ):
            return []
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
        options = self.selected_report_options
        diagram_enabled = (
            options.section_enabled("infrastructure_diagram")
            and bool(options.diagram_option("enabled", True))
        )
        if not (
            options.section_enabled("infrastructure_inventory")
            or diagram_enabled
        ):
            return []
        filtered = [
            item for item in self.infrastructure
            if (
                isinstance(item, dict)
                and str(item.get("category") or "").upper()
                in self.DISPLAY_INFRASTRUCTURE_CATEGORIES
                and options.resource_enabled(
                    str(item.get("category") or "")
                )
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
            if isinstance(server, dict) and options.resource_enabled("SERVER")
        ]

    @property
    def display_infrastructure_metrics(self) -> List[Dict[str, Any]]:
        """Return only metric groups supported by the infrastructure report."""
        options = self.selected_report_options
        if not options.section_enabled("monitoring"):
            return []
        return [
            item for item in self.infrastructure_metrics
            if (
                isinstance(item, dict)
                and str(item.get("category") or "").upper()
                in self.MONITORED_INFRASTRUCTURE_CATEGORIES
                and options.monitoring_enabled(
                    str(item.get("category") or "")
                )
            )
        ]

    @property
    def display_infrastructure_topology(self) -> Dict[str, Any]:
        """Build a topology from collected IDs without heuristic matching."""
        options = self.selected_report_options
        if (
            not options.section_enabled("infrastructure_diagram")
            or not bool(options.diagram_option("enabled", True))
        ):
            return {}
        if (
            isinstance(self.infrastructure_topology, dict)
            and isinstance(self.infrastructure_topology.get("nodes"), list)
            and isinstance(self.infrastructure_topology.get("edges"), list)
            and isinstance(self.infrastructure_topology.get("summary"), dict)
        ):
            topology_summary = self.infrastructure_topology["summary"]
            reference_at = (
                topology_summary.get("reference_at")
                or self._infrastructure_reference_at()
            )
            if (
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
            return self.infrastructure_topology

        metadata = (
            self.collection_metadata
            if isinstance(self.collection_metadata, dict)
            else {}
        )
        infrastructure_metadata = metadata.get("infrastructure")
        if not isinstance(infrastructure_metadata, dict):
            infrastructure_metadata = {}
        collected_at = (
            infrastructure_metadata.get("completed_at")
            or infrastructure_metadata.get("started_at")
        )
        reference_at = (
            infrastructure_metadata.get("reference_at")
            or self.generated_at
        )
        if (
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
            self.display_infrastructure,
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
        topology.setdefault("summary", {}).update(
            self._snapshot_window_metadata(reference_at, collected_at)
        )
        topology["summary"]["time_basis"] = "REPORT_PERIOD"
        return topology

    def _has_period_bounds(self) -> bool:
        return bool(self.period.get("start_dt") and self.period.get("end_dt"))

    def _infrastructure_reference_at(self) -> Any:
        metadata = (
            self.collection_metadata
            if isinstance(self.collection_metadata, dict)
            else {}
        )
        infrastructure_metadata = metadata.get("infrastructure")
        if isinstance(infrastructure_metadata, dict):
            reference_at = infrastructure_metadata.get("reference_at")
            if reference_at:
                return reference_at
        return self.generated_at

    def _period_bounds_kst(self) -> tuple[datetime, datetime]:
        start = self._parse_kst_datetime(self.period["start_dt"])
        end = self._parse_kst_datetime(self.period["end_dt"])
        if not self.period.get("end_exclusive"):
            end += timedelta(seconds=1)
        if start >= end:
            raise ValueError("Report period is invalid.")
        return start, end

    def _snapshot_eligibility_window(
        self,
        reference_at: Any,
    ) -> Dict[str, datetime] | None:
        try:
            start, end = self._period_bounds_kst()
            reference = self._parse_kst_datetime(reference_at)
        except (KeyError, TypeError, ValueError):
            return None
        if reference < start:
            return None
        reference = min(reference, end - timedelta(microseconds=1))
        eligible_start = start
        eligible_end = min(
            end,
            reference + timedelta(microseconds=1),
        )
        if eligible_start >= eligible_end:
            return None
        return {
            "reference_at": reference,
            "eligible_start": eligible_start,
            "eligible_end": eligible_end,
        }

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
        if not window:
            return {
                "reference_at": None,
                "eligible_start": None,
                "eligible_end": None,
                "snapshot_age_seconds": None,
            }
        result: Dict[str, Any] = {
            key: window[key].isoformat()
            for key in ("reference_at", "eligible_start", "eligible_end")
        }
        result["snapshot_age_seconds"] = None
        try:
            observed = self._parse_kst_datetime(observed_at)
        except (TypeError, ValueError):
            observed = None
        if observed is not None:
            result["snapshot_age_seconds"] = max(
                0,
                int((window["reference_at"] - observed).total_seconds()),
            )
        return result

    def _observed_inside_period(self, observed_at: Any) -> bool:
        if not observed_at:
            return False
        try:
            observed = self._parse_kst_datetime(observed_at)
            start = self._parse_kst_datetime(self.period["start_dt"])
            end = self._parse_kst_datetime(self.period["end_dt"])
        except (KeyError, TypeError, ValueError):
            return False
        if not self.period.get("end_exclusive"):
            end += timedelta(seconds=1)
        return start <= observed < end

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
            reference_at or self.generated_at,
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
                "period_start": self.period.get("start_dt"),
                "period_end": self.period.get("end_dt"),
                **window_metadata,
            },
        }

    @property
    def persisted_infrastructure(self) -> List[Dict[str, Any]]:
        """Keep collected resources needed for later period-accurate reuse."""
        return [
            item
            for item in self.infrastructure
            if (
                isinstance(item, dict)
                and str(item.get("category") or "").upper()
                in self.DISPLAY_INFRASTRUCTURE_CATEGORIES
            )
        ]

    @property
    def public_servers(self) -> List[Dict[str, Any]]:
        options = self.selected_report_options
        if not (
            options.section_enabled("infrastructure_inventory")
            and options.resource_enabled("SERVER")
        ):
            return []
        allowed_fields = [
            "server_name",
            "status",
            "cpu_count",
            "memory_gb",
            "region_code",
            "zone_code",
            "create_date",
        ]
        if bool(options.diagram_option("show_resource_id", True)):
            allowed_fields.append("server_id")
        if bool(options.diagram_option("show_private_ip", True)):
            allowed_fields.append("private_ip")
        if bool(options.diagram_option("show_public_ip", True)):
            allowed_fields.append("public_ip")
        return [
            {
                key: server.get(key)
                for key in allowed_fields
                if key in server
            }
            for server in self.servers
            if isinstance(server, dict)
        ]

    @property
    def public_customer(self) -> Dict[str, Any]:
        if not isinstance(self.customer, dict):
            return {}
        allowed_fields = (
            "id",
            "name",
            "api_type",
            "region",
            "cloud_account_code",
        )
        return {
            key: self.customer.get(key)
            for key in allowed_fields
            if key in self.customer
        }

    @property
    def public_infrastructure(self) -> List[Dict[str, Any]]:
        options = self.selected_report_options
        if not options.section_enabled("infrastructure_inventory"):
            return []
        allowed_fields = [
            "category",
            "category_label",
            "service_name",
            "resource_type",
            "resource_name",
            "status",
            "region_code",
            "zone_code",
            "platform",
            "create_time",
        ]
        if bool(options.diagram_option("show_resource_id", True)):
            allowed_fields.append("resource_id")
        safe_detail_fields = (
            "load_balancer_type",
            "network_type",
            "protocol",
            "engine",
            "version",
            "server_count",
            "cpu_count_total",
            "memory_gb_total",
            "data_storage_gb_total",
            "cpu_count",
            "memory_gb",
            "size_gb",
            "storage_size_gb",
            "kubernetes_version",
            "node_count",
            "node_pool_count",
            "domain_count",
            "attached_server_name",
            "high_availability",
            "multi_zone",
        )
        result = []
        for resource in self.display_infrastructure:
            item = {
                key: resource.get(key)
                for key in allowed_fields
                if key in resource
            }
            details = resource.get("details")
            if isinstance(details, dict):
                safe_details = {
                    key: details.get(key)
                    for key in safe_detail_fields
                    if key in details
                }
                if safe_details:
                    item["details"] = safe_details
            result.append(item)
        return result

    @property
    def public_infrastructure_topology(self) -> Dict[str, Any]:
        topology = self.display_infrastructure_topology
        if not topology:
            return {}
        options = self.selected_report_options
        nodes = [
            dict(node)
            for node in topology.get("nodes", [])
            if isinstance(node, dict)
        ]
        node_id_map = {
            str(node.get("node_id")): f"node-{index:03d}"
            for index, node in enumerate(nodes, start=1)
        }
        field_options = {
            "name": "show_resource_name",
            "resource_id": "show_resource_id",
            "private_ips": "show_private_ip",
            "public_ips": "show_public_ip",
            "network_cidrs": "show_network_cidr",
            "status": "show_status",
            "zone": "show_zone",
            "platform": "show_platform",
        }
        public_nodes = []
        for node in nodes:
            original_id = str(node.get("node_id"))
            node["node_id"] = node_id_map.get(original_id, "node")
            for field_name, option_name in field_options.items():
                if not bool(options.diagram_option(option_name, True)):
                    node.pop(field_name, None)
            public_nodes.append(node)

        public_edges = []
        for edge in topology.get("edges", []):
            if not isinstance(edge, dict):
                continue
            source_id = node_id_map.get(str(edge.get("source_node_id")))
            target_id = node_id_map.get(str(edge.get("target_node_id")))
            if not source_id or not target_id:
                continue
            public_edge = dict(edge)
            public_edge["source_node_id"] = source_id
            public_edge["target_node_id"] = target_id
            public_edge["edge_id"] = (
                f"{source_id}|{edge.get('relationship') or 'RELATED'}|"
                f"{target_id}"
            )
            public_edges.append(public_edge)

        public_topology = dict(topology)
        public_topology["nodes"] = public_nodes
        public_topology["edges"] = public_edges
        for key in ("unmapped_node_ids", "unresolved_node_ids"):
            public_topology[key] = [
                node_id_map[str(node_id)]
                for node_id in topology.get(key, [])
                if str(node_id) in node_id_map
            ]
        return public_topology

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "1.3",
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "customer": self.public_customer,
            "period": self.period,
            "servers": self.public_servers,
            "server_metrics": self.display_server_metrics,
            "infrastructure": self.public_infrastructure,
            "infrastructure_metrics": self.display_infrastructure_metrics,
            "insight_events": self.insight_events,
            "grouped_insight_events": self.grouped_insight_events,
            "activity_events": self.activity_events,
            "billing": self.billing,
            "report_options": self.selected_report_options.to_dict(),
            "collection_metadata": self.collection_metadata,
            "infrastructure_topology": self.public_infrastructure_topology,
            "collection_errors": self.collection_errors,
            "collection_warnings": self.collection_warnings,
        }

    def to_persistence_dict(self) -> Dict[str, Any]:
        """Serialize the tenant-isolated snapshot used for period reuse.

        The downloadable JSON returned by :meth:`to_dict` contains only the
        selected inventory.  PostgreSQL keeps monitoring-only resources so a
        future historical report can resolve the resource IDs observed during
        that period without querying today's inventory.
        """
        snapshot = self.to_dict()
        snapshot["customer"] = self.customer
        snapshot["servers"] = self.servers
        snapshot["infrastructure"] = self.persisted_infrastructure
        snapshot["infrastructure_topology"] = (
            self.display_infrastructure_topology
        )
        return snapshot

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReportResult":
        """Rehydrate a persisted normalized snapshot for deterministic rendering."""
        if not isinstance(payload, Mapping):
            raise ValueError("Report snapshot must be an object.")
        period = payload.get("period")
        if not isinstance(period, dict):
            raise ValueError("Report snapshot does not contain a valid period.")
        report_options = payload.get("report_options")
        if not isinstance(report_options, dict) or not report_options:
            report_options = (
                legacy_report_options()
                if str(payload.get("schema_version") or "") != "1.3"
                else {}
            )
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
            report_options=report_options,
            collection_metadata=payload.get("collection_metadata") or {},
            infrastructure_topology=(
                payload.get("infrastructure_topology") or {}
            ),
            collection_errors=payload.get("collection_errors") or [],
            collection_warnings=payload.get("collection_warnings") or [],
            generated_at=str(payload.get("generated_at") or "-"),
        )

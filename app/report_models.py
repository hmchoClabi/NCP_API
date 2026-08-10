from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Dict, List, Mapping
from zoneinfo import ZoneInfo

from app.infrastructure_topology import REPRESENTATIVE_CATEGORIES
from app.report_branding import normalize_customer_logo_data_uri
from app.report_options import (
    MONITORING_CATEGORY_OPTIONS,
    ReportOptions,
    legacy_report_options,
)
from app.report_topology_policy import ReportTopologyPolicy


@dataclass
class ReportResult:
    """Delivery-neutral result produced by the NCP report pipeline."""

    DISPLAY_INFRASTRUCTURE_CATEGORIES: ClassVar[frozenset[str]] = frozenset(
        REPRESENTATIVE_CATEGORIES
    )
    PERSISTED_INFRASTRUCTURE_CATEGORIES: ClassVar[frozenset[str]] = (
        DISPLAY_INFRASTRUCTURE_CATEGORIES | {"TARGET_GROUP"}
    )
    MONITORED_INFRASTRUCTURE_CATEGORIES: ClassVar[frozenset[str]] = (
        frozenset(MONITORING_CATEGORY_OPTIONS) - {"SERVER"}
    )
    CURRENT_STATE_TOPOLOGY_TIME_BASIS: ClassVar[str] = (
        ReportTopologyPolicy.CURRENT_STATE_TOPOLOGY_TIME_BASIS
    )
    PUBLIC_TOPOLOGY_NODE_FIELDS: ClassVar[tuple[str, ...]] = (
        "category",
        "category_label",
        "resource_type",
        "resource_id",
        "name",
        "private_ips",
        "public_ips",
        "network_cidrs",
        "status",
        "zone",
        "platform",
        "kind",
        "reference_kind",
        "count_as_infrastructure",
        "confidence",
        "resolution",
        "is_mapped",
        "storage_size_gb",
        "storage_type",
        "disk_type",
        "volume_type",
        "subnet_usage_type",
        "placement_hint",
        "network_interface_count",
        "attached_disk_count",
        "attached_disk_capacity_known_count",
        "attached_disk_total_gb",
        "public_ip_resource_count",
    )
    PUBLIC_TOPOLOGY_EDGE_FIELDS: ClassVar[tuple[str, ...]] = (
        "relationship",
        "confidence",
    )
    PUBLIC_TOPOLOGY_WARNING_FIELDS: ClassVar[tuple[str, ...]] = (
        "code",
        "message",
        "confidence",
    )
    PUBLIC_TOPOLOGY_SUMMARY_FIELDS: ClassVar[tuple[str, ...]] = (
        "representative_node_count",
        "supporting_node_count",
        "verified_edge_count",
        "total_verified_edge_count",
        "unmapped_resource_count",
        "unresolved_reference_count",
        "collected_at",
        "max_nodes",
        "truncated",
        "omitted_node_count",
        "confidence",
        "relationship_confidence",
        "relationship_coverage",
        "inventory_completeness",
        "collection_issue_count",
        "presentation_policy_version",
        "presentation_policy_mode",
        "time_basis",
        "snapshot_source",
        "period_start",
        "period_end",
        "reference_at",
        "eligible_start",
        "eligible_end",
        "snapshot_age_seconds",
    )
    PUBLIC_TOPOLOGY_PRESENTATION_FIELDS: ClassVar[tuple[str, ...]] = (
        "embedded_node_count",
        "embedded_block_storage_count",
        "embedded_network_interface_count",
        "embedded_public_ip_count",
        "excluded_category_node_count",
        "excluded_nat_subnet_count",
        "excluded_orphan_reference_count",
        "retained_ambiguous_auxiliary_count",
        "retained_unverified_nat_subnet_count",
        "removed_edge_count",
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
    def display_load_balancer_target_groups(self) -> List[Dict[str, Any]]:
        """Return supporting Target Group health snapshots for the report."""
        options = self.selected_report_options
        if (
            not options.section_enabled("infrastructure_inventory")
            or not options.resource_enabled("LOAD_BALANCER")
        ):
            return []
        return [
            item for item in self.infrastructure
            if (
                isinstance(item, dict)
                and str(item.get("category") or "").upper()
                == "TARGET_GROUP"
            )
        ]

    def _topology_policy(self) -> ReportTopologyPolicy:
        return ReportTopologyPolicy(self)

    @property
    def display_infrastructure_topology(self) -> Dict[str, Any]:
        return self._topology_policy().display_infrastructure_topology

    def _has_period_bounds(self) -> bool:
        return self._topology_policy()._has_period_bounds()

    def _current_state_topology_is_valid(
        self,
        topology_summary: Mapping[str, Any],
        infrastructure_metadata: Mapping[str, Any],
    ) -> bool:
        return self._topology_policy()._current_state_topology_is_valid(
            topology_summary,
            infrastructure_metadata,
        )

    @staticmethod
    def _current_state_topology_warning() -> Dict[str, str]:
        return ReportTopologyPolicy._current_state_topology_warning()

    def _infrastructure_reference_at(self) -> Any:
        return self._topology_policy()._infrastructure_reference_at()

    def _period_bounds_kst(self) -> tuple[datetime, datetime]:
        return self._topology_policy()._period_bounds_kst()

    def _snapshot_eligibility_window(
        self,
        reference_at: Any,
    ) -> Dict[str, datetime] | None:
        return self._topology_policy()._snapshot_eligibility_window(
            reference_at
        )

    def _observed_inside_reference_window(
        self,
        observed_at: Any,
        reference_at: Any,
    ) -> bool:
        return self._topology_policy()._observed_inside_reference_window(
            observed_at,
            reference_at,
        )

    def _snapshot_window_metadata(
        self,
        reference_at: Any,
        observed_at: Any = None,
    ) -> Dict[str, Any]:
        return self._topology_policy()._snapshot_window_metadata(
            reference_at,
            observed_at,
        )

    @staticmethod
    def _parse_kst_datetime(value: Any) -> datetime:
        return ReportTopologyPolicy._parse_kst_datetime(value)

    def _period_snapshot_unavailable_topology(
        self,
        *,
        collected_at: Any,
        source: str,
        max_nodes: Any,
        reference_at: Any = None,
    ) -> Dict[str, Any]:
        return self._topology_policy()._period_snapshot_unavailable_topology(
            collected_at=collected_at,
            source=source,
            max_nodes=max_nodes,
            reference_at=reference_at,
        )

    @property
    def persisted_infrastructure(self) -> List[Dict[str, Any]]:
        """Keep collected resources needed for later period-accurate reuse."""
        return [
            item
            for item in self.infrastructure
            if (
                isinstance(item, dict)
                and str(item.get("category") or "").upper()
                in self.PERSISTED_INFRASTRUCTURE_CATEGORIES
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
            "create_time_source",
            "historical_presence_confidence",
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
            "logo_data_uri",
        )
        customer = {
            key: self.customer.get(key)
            for key in allowed_fields
            if key in self.customer
        }
        if "logo_data_uri" in customer:
            try:
                logo_data_uri = normalize_customer_logo_data_uri(
                    customer["logo_data_uri"]
                )
            except ValueError:
                customer.pop("logo_data_uri", None)
            else:
                if logo_data_uri:
                    customer["logo_data_uri"] = logo_data_uri
                else:
                    customer.pop("logo_data_uri", None)
        return customer

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
            "create_time_source",
            "historical_presence_confidence",
            "historical_presence_basis",
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
            public_node = {
                field_name: node[field_name]
                for field_name in self.PUBLIC_TOPOLOGY_NODE_FIELDS
                if field_name in node
            }
            public_node["node_id"] = node_id_map.get(original_id, "node")
            for field_name, option_name in field_options.items():
                if not bool(options.diagram_option(option_name, True)):
                    public_node.pop(field_name, None)
            public_nodes.append(public_node)

        public_edges = []
        for edge in topology.get("edges", []):
            if not isinstance(edge, dict):
                continue
            source_id = node_id_map.get(str(edge.get("source_node_id")))
            target_id = node_id_map.get(str(edge.get("target_node_id")))
            if not source_id or not target_id:
                continue
            public_edge = {
                field_name: edge[field_name]
                for field_name in self.PUBLIC_TOPOLOGY_EDGE_FIELDS
                if field_name in edge
            }
            public_edge["source_node_id"] = source_id
            public_edge["target_node_id"] = target_id
            public_edge["edge_id"] = (
                f"{source_id}|{edge.get('relationship') or 'RELATED'}|"
                f"{target_id}"
            )
            public_edges.append(public_edge)

        public_topology = {
            "nodes": public_nodes,
            "edges": public_edges,
            "warnings": [
                {
                    field_name: warning[field_name]
                    for field_name in self.PUBLIC_TOPOLOGY_WARNING_FIELDS
                    if field_name in warning
                }
                for warning in topology.get("warnings", [])
                if isinstance(warning, Mapping)
            ],
        }
        for key in ("unmapped_node_ids", "unresolved_node_ids"):
            public_topology[key] = [
                node_id_map[str(node_id)]
                for node_id in topology.get(key, [])
                if str(node_id) in node_id_map
            ]
        raw_summary = topology.get("summary")
        summary = raw_summary if isinstance(raw_summary, Mapping) else {}
        public_summary = {
            field_name: summary[field_name]
            for field_name in self.PUBLIC_TOPOLOGY_SUMMARY_FIELDS
            if field_name in summary
        }
        presentation = summary.get("presentation_policy")
        if isinstance(presentation, Mapping):
            public_summary["presentation_policy"] = {
                field_name: presentation[field_name]
                for field_name in self.PUBLIC_TOPOLOGY_PRESENTATION_FIELDS
                if field_name in presentation
            }
        public_topology["summary"] = public_summary
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
        """저장된 정규화 스냅샷을 현재 표시 정책으로 복원한다.

        원본 수집 데이터는 바꾸지 않고, 구성도 표시 계층만 버전이 명시된
        멱등 마이그레이션을 적용한다.
        """
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

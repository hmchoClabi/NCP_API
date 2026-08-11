from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Dict, List, Mapping
from zoneinfo import ZoneInfo

from app.report_branding import normalize_customer_logo_data_uri
from app.report_options import (
    MONITORING_CATEGORY_OPTIONS,
    NETWORK_CONFIGURATION_CATEGORY_OPTIONS,
    RESOURCE_CATEGORY_OPTIONS,
    ReportOptions,
    legacy_report_options,
)


@dataclass
class ReportResult:
    """Delivery-neutral result produced by the NCP report pipeline."""

    DISPLAY_INFRASTRUCTURE_CATEGORIES: ClassVar[frozenset[str]] = frozenset(
        RESOURCE_CATEGORY_OPTIONS
    )
    PERSISTED_INFRASTRUCTURE_CATEGORIES: ClassVar[frozenset[str]] = (
        (
            DISPLAY_INFRASTRUCTURE_CATEGORIES
            - frozenset(NETWORK_CONFIGURATION_CATEGORY_OPTIONS)
        )
        | {"TARGET_GROUP"}
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
    collection_errors: List[Dict[str, Any]] = field(default_factory=list)
    collection_warnings: List[Dict[str, Any]] = field(default_factory=list)
    # Route Table·ACG·Network ACL 원본은 일반 보고서 JSON과 분리해
    # 전용 PostgreSQL 스냅샷 테이블에만 저장한다.
    network_configuration_snapshot: Dict[str, Any] = field(
        default_factory=dict,
        repr=False,
    )
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
        if not options.section_enabled("infrastructure_inventory"):
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
                "details": {
                    key: value
                    for key, value in {
                        "server_product_code": server.get(
                            "server_product_code"
                        ),
                        "server_product_name": server.get(
                            "server_product_name"
                        ),
                        "cpu_count": server.get("cpu_count"),
                        "memory_gb": server.get("memory_gb"),
                        "storage_count": len(server.get("storages") or []),
                        "private_ip": server.get("private_ip"),
                        "public_ip": server.get("public_ip"),
                    }.items()
                    if value not in (None, "", [])
                },
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
            "server_product_code",
            "server_product_name",
            "storage_count",
            "storage_size_gb_total",
            "size_gb",
            "storage_size_gb",
            "storage_type",
            "disk_type",
            "volume_type",
            "iops",
            "throughput_mbps",
            "throughput_type",
            "snapshot_volume_size_gb",
            "block_storage_size_gb",
            "kubernetes_version",
            "cluster_type",
            "node_count",
            "node_max_count",
            "node_pool_count",
            "generation",
            "domain_count",
            "record_count",
            "endpoint_count",
            "api_count",
            "request_count",
            "object_count",
            "outbound_traffic_gb",
            "broker_count",
            "partition_count",
            "retention_hours",
            "retention_days",
            "backup_size_gb",
            "desired_capacity",
            "min_size",
            "max_size",
            "gateway_type",
            "public_ip_count",
            "associated",
            "attached_server_name",
            "high_availability",
            "multi_zone",
            "is_default",
            "route_count",
            "associated_subnet_count",
            "rule_count",
            "inbound_rule_count",
            "outbound_rule_count",
            "supported_subnet_type",
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "1.4",
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
        return snapshot

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReportResult":
        """저장된 정규화 스냅샷을 현재 표시 정책으로 복원한다."""
        if not isinstance(payload, Mapping):
            raise ValueError("Report snapshot must be an object.")
        period = payload.get("period")
        if not isinstance(period, dict):
            raise ValueError("Report snapshot does not contain a valid period.")
        report_options = payload.get("report_options")
        if not isinstance(report_options, dict) or not report_options:
            report_options = (
                legacy_report_options()
                if str(payload.get("schema_version") or "")
                not in {"1.3", "1.4"}
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
            collection_errors=payload.get("collection_errors") or [],
            collection_warnings=payload.get("collection_warnings") or [],
            generated_at=str(payload.get("generated_at") or "-"),
        )

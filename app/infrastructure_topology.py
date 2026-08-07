"""Build a deterministic topology from explicitly collected relationships."""

from __future__ import annotations

from dataclasses import dataclass, fields
from hashlib import sha256
from ipaddress import ip_address, ip_network
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from app.report_options import (
    RESOURCE_CATEGORY_LABELS,
    RESOURCE_CATEGORY_OPTIONS,
)

REPRESENTATIVE_CATEGORY_LABELS = dict(RESOURCE_CATEGORY_LABELS)
REPRESENTATIVE_CATEGORIES = tuple(RESOURCE_CATEGORY_OPTIONS)
SUPPORTING_CATEGORIES = frozenset({"NETWORK_INTERFACE", "TARGET_GROUP"})


@dataclass(frozen=True)
class TopologyDisplayOptions:
    """Select which optional resource attributes can appear in the diagram."""

    enabled: bool = True
    show_resource_name: bool = True
    show_resource_id: bool = True
    show_private_ip: bool = True
    show_public_ip: bool = True
    show_network_cidr: bool = True
    show_status: bool = True
    show_zone: bool = True
    show_platform: bool = True
    include_unmapped_resources: bool = True
    group_by_vpc: bool = True

    @classmethod
    def from_mapping(
        cls,
        value: Optional[Mapping[str, Any]],
    ) -> "TopologyDisplayOptions":
        if not isinstance(value, Mapping):
            return cls()
        defaults = cls()
        options = {}
        for field in fields(cls):
            candidate = value.get(field.name, getattr(defaults, field.name))
            options[field.name] = (
                candidate
                if isinstance(candidate, bool)
                else getattr(defaults, field.name)
            )
        return cls(**options)


class InfrastructureTopologyBuilder:
    """Create nodes and verified edges without name/IP/CIDR inference."""

    DEFAULT_MAX_NODES = 120
    CATEGORY_ALIASES = {
        "CDB": "CLOUD_DB",
        "NKS": "KUBERNETES",
        "K8S": "KUBERNETES",
        "LB": "LOAD_BALANCER",
        "LOADBALANCER": "LOAD_BALANCER",
        "NATGW": "NAT_GATEWAY",
        "PUBLICIP": "PUBLIC_IP",
        "VPCPEERING": "VPC_PEERING",
        "NETWORKINTERFACE": "NETWORK_INTERFACE",
        "NIC": "NETWORK_INTERFACE",
        "TARGETGROUP": "TARGET_GROUP",
        "SNAPSHOT": "BLOCK_STORAGE_SNAPSHOT",
    }
    ID_FIELDS = {
        "SERVER": ("server_instance_no", "server_id"),
        "LOAD_BALANCER": ("load_balancer_instance_no",),
        "BLOCK_STORAGE": ("block_storage_instance_no", "storage_id"),
        "KUBERNETES": ("cluster_uuid", "cluster_no", "instance_no"),
        "VPC": ("vpc_no",),
        "SUBNET": ("subnet_no",),
        "NAT_GATEWAY": ("nat_gateway_instance_no",),
        "PUBLIC_IP": ("public_ip_instance_no",),
        "VPC_PEERING": ("vpc_peering_instance_no",),
        "NETWORK_INTERFACE": ("network_interface_no",),
        "TARGET_GROUP": ("target_group_no",),
        "BLOCK_STORAGE_SNAPSHOT": (
            "block_storage_snapshot_instance_no",
            "snapshot_instance_no",
        ),
    }
    PRIVATE_IP_FIELDS = (
        "private_ip",
        "private_ips",
        "all_private_ips",
    )
    PUBLIC_IP_FIELDS = (
        "public_ip",
        "public_ips",
        "load_balancer_ip",
        "domain_ip",
    )
    CIDR_FIELDS = (
        "ipv4_cidr_block",
        "cidr",
        "network_cidr",
    )
    PUBLIC_NETWORK_TYPES = frozenset({
        "PUBLIC",
        "PUBLIC_IP",
        "PUBLICIP",
        "PBLIP",
    })
    PRIVATE_NETWORK_TYPES = frozenset({
        "PRIVATE",
        "PRIVATE_IP",
        "PRIVATEIP",
        "PRVT",
    })
    WORKLOAD_CATEGORIES = frozenset({
        "SERVER",
        "LOAD_BALANCER",
        "KUBERNETES",
        "CLOUD_DB",
        "NAT_GATEWAY",
        "AUTO_SCALING",
        "SEARCH_ENGINE",
        "DATA_STREAMING",
        "CLOUD_HADOOP",
    })

    def build(
        self,
        resources: Iterable[Mapping[str, Any]],
        *,
        collected_at: Optional[str] = None,
        max_nodes: Optional[int] = None,
        allowed_reference_categories: Optional[Iterable[str]] = None,
        inventory_completeness: str = "UNKNOWN",
        collection_issue_count: int = 0,
    ) -> Dict[str, Any]:
        limit = self._max_nodes(max_nodes)
        allowed_categories = (
            frozenset(REPRESENTATIVE_CATEGORIES)
            if allowed_reference_categories is None
            else frozenset(
                category
                for category in (
                    self._category(value)
                    for value in allowed_reference_categories
                )
                if category in REPRESENTATIVE_CATEGORY_LABELS
            )
        )
        allowed_references = allowed_categories | SUPPORTING_CATEGORIES
        nodes: Dict[str, Dict[str, Any]] = {}
        lookup: Dict[tuple[str, str], str] = {}
        resource_nodes: List[tuple[Dict[str, Any], Mapping[str, Any]]] = []
        warnings: List[Dict[str, Any]] = []
        resource_items = self._mapping_items(resources)
        identity_counts: Dict[tuple[str, str], int] = {}
        for resource in resource_items:
            category = self._category(resource.get("category"))
            if category not in allowed_categories:
                continue
            details = self._mapping(resource.get("details"))
            resource_id = self._resource_id(category, resource, details)
            if resource_id:
                identity_key = (category, resource_id)
                identity_counts[identity_key] = (
                    identity_counts.get(identity_key, 0) + 1
                )

        for index, resource in enumerate(resource_items):
            category = self._category(resource.get("category"))
            if (
                category not in REPRESENTATIVE_CATEGORY_LABELS
                or category not in allowed_categories
            ):
                continue
            details = self._mapping(resource.get("details"))
            resource_id = self._resource_id(category, resource, details)
            identity_key = (category, resource_id) if resource_id else None
            identity_collision = bool(
                identity_key
                and identity_counts.get(identity_key, 0) > 1
            )
            discriminator = None
            if identity_collision:
                discriminator = (
                    self._string(details.get("source_nrn"))
                    or self._string(resource.get("platform"))
                    or self._string(resource.get("zone_code"))
                    or f"inventory-index-{index}"
                )
            node_id = self._node_id(
                category,
                resource_id,
                index=index,
                discriminator=discriminator,
            )
            node = self._inventory_node(
                node_id,
                category,
                resource_id,
                resource,
                details,
            )
            existing = nodes.get(node_id)
            if existing is None:
                nodes[node_id] = node
                existing = node
            else:
                self._merge_node(existing, node)
            if resource_id and not identity_collision:
                lookup[(category, resource_id)] = node_id
            resource_nodes.append((existing, resource))

        edges: Dict[tuple[str, str, str], Dict[str, Any]] = {}
        for node, resource in resource_nodes:
            details = self._mapping(resource.get("details"))
            self._add_explicit_relations(
                node,
                details,
                nodes,
                lookup,
                edges,
                warnings,
                allowed_references,
            )
            self._add_field_relations(
                node,
                details,
                nodes,
                lookup,
                edges,
                allowed_references,
            )

        full_edges = list(edges.values())
        degree = {node_id: 0 for node_id in nodes}
        for edge in full_edges:
            degree[edge["source_node_id"]] += 1
            degree[edge["target_node_id"]] += 1
        for node_id, node in nodes.items():
            node["is_mapped"] = degree.get(node_id, 0) > 0
            if not node["is_mapped"] and node["kind"] == "representative":
                node["confidence"] = "UNMAPPED"

        full_nodes = list(nodes.values())
        selected_nodes, selected_edges = self._truncate(
            full_nodes,
            full_edges,
            limit,
        )
        selected_ids = {node["node_id"] for node in selected_nodes}
        unmapped_nodes = [
            node for node in selected_nodes
            if (
                node["kind"] == "representative"
                and not node.get("is_mapped")
            )
        ]
        unresolved_nodes = [
            node for node in selected_nodes
            if node.get("resolution") == "UNRESOLVED"
        ]
        full_unmapped_count = sum(
            1 for node in full_nodes
            if (
                node["kind"] == "representative"
                and not node.get("is_mapped")
            )
        )
        full_unresolved_count = sum(
            1 for node in full_nodes
            if node.get("resolution") == "UNRESOLVED"
        )
        omitted_node_count = len(full_nodes) - len(selected_nodes)
        normalized_inventory_completeness = str(
            inventory_completeness or "UNKNOWN"
        ).strip().upper()[:60]
        try:
            normalized_issue_count = max(
                int(collection_issue_count or 0),
                0,
            )
        except (TypeError, ValueError):
            normalized_issue_count = 0
        relation_coverage = (
            "PARTIAL"
            if full_unmapped_count or full_unresolved_count
            else "COMPLETE"
        )
        overall_confidence = (
            "PARTIAL"
            if (
                full_unmapped_count
                or full_unresolved_count
                or omitted_node_count
                or normalized_issue_count
                or normalized_inventory_completeness
                not in {
                    "COMPLETE",
                    "COMPLETE_FOR_SELECTED_SCOPE",
                    "COMPLETE_FOR_SNAPSHOT_SCOPE",
                }
            )
            else "VERIFIED"
        )

        if full_unmapped_count:
            warnings.append({
                "code": "UNMAPPED_RESOURCES",
                "message": (
                    "명시적인 리소스 ID 관계가 없어 미매핑 그룹에 "
                    f"{full_unmapped_count}개 자원을 표시합니다."
                ),
                "source": "normalized_inventory",
                "confidence": "UNMAPPED",
            })
        if full_unresolved_count:
            warnings.append({
                "code": "UNRESOLVED_REFERENCES",
                "message": (
                    "관계 대상 ID는 확인되었지만 인벤토리에서 상세 자원을 "
                    f"찾지 못한 참조가 {full_unresolved_count}개 있습니다."
                ),
                "source": "explicit_resource_id_relation",
                "confidence": "VERIFIED",
            })
        if omitted_node_count:
            warnings.append({
                "code": "TOPOLOGY_TRUNCATED",
                "message": (
                    f"구성도 노드 제한({limit}개)으로 "
                    f"{omitted_node_count}개 노드를 생략했습니다."
                ),
                "source": "renderer_limit",
                "confidence": "VERIFIED",
            })

        selected_nodes.sort(key=self._node_sort_key)
        selected_edges.sort(key=self._edge_sort_key)
        return {
            "nodes": selected_nodes,
            "edges": selected_edges,
            "unmapped_node_ids": [
                node["node_id"] for node in unmapped_nodes
                if node["node_id"] in selected_ids
            ],
            "unresolved_node_ids": [
                node["node_id"] for node in unresolved_nodes
                if node["node_id"] in selected_ids
            ],
            "warnings": warnings,
            "summary": {
                "representative_node_count": sum(
                    1 for node in selected_nodes
                    if node.get("count_as_infrastructure")
                ),
                "supporting_node_count": sum(
                    1 for node in selected_nodes
                    if not node.get("count_as_infrastructure")
                ),
                "verified_edge_count": len(selected_edges),
                "total_verified_edge_count": len(full_edges),
                "unmapped_resource_count": full_unmapped_count,
                "unresolved_reference_count": full_unresolved_count,
                "collected_at": collected_at,
                "max_nodes": limit,
                "truncated": bool(omitted_node_count),
                "omitted_node_count": omitted_node_count,
                "confidence": overall_confidence,
                "relationship_confidence": "VERIFIED",
                "relationship_coverage": relation_coverage,
                "inventory_completeness": (
                    normalized_inventory_completeness
                ),
                "collection_issue_count": normalized_issue_count,
            },
        }

    def _add_explicit_relations(
        self,
        source_node: Mapping[str, Any],
        details: Mapping[str, Any],
        nodes: Dict[str, Dict[str, Any]],
        lookup: Dict[tuple[str, str], str],
        edges: Dict[tuple[str, str, str], Dict[str, Any]],
        warnings: List[Dict[str, Any]],
        allowed_references: frozenset[str],
    ) -> None:
        relations = details.get("explicit_relations")
        if not isinstance(relations, (list, tuple)):
            return
        for relation in relations:
            if not isinstance(relation, Mapping):
                continue
            target_category = self._category(relation.get("target_category"))
            target_id = self._string(relation.get("target_id"))
            source_field = self._string(relation.get("source_field"))
            relation_type = self._relation_token(relation.get("type"))
            if (
                target_category not in REPRESENTATIVE_CATEGORY_LABELS
                and target_category not in SUPPORTING_CATEGORIES
            ) or not target_id:
                warnings.append({
                    "code": "INVALID_EXPLICIT_RELATION",
                    "message": "대상 category 또는 ID가 없는 명시 관계를 제외했습니다.",
                    "source": source_field or "details.explicit_relations",
                    "confidence": "UNMAPPED",
                })
                continue
            if target_category not in allowed_references:
                continue
            target_node = self._target_node(
                target_category,
                target_id,
                source_field or "details.explicit_relations",
                nodes,
                lookup,
            )
            oriented = self._orient_relation(
                source_node,
                target_node,
                relation_type,
            )
            self._store_edge(
                edges,
                oriented[0],
                oriented[1],
                oriented[2],
                source_field or "details.explicit_relations",
            )

    def _add_field_relations(
        self,
        node: Mapping[str, Any],
        details: Mapping[str, Any],
        nodes: Dict[str, Dict[str, Any]],
        lookup: Dict[tuple[str, str], str],
        edges: Dict[tuple[str, str, str], Dict[str, Any]],
        allowed_references: frozenset[str],
    ) -> None:
        category = str(node["category"])
        subnet_ids = self._values(
            details,
            ("subnet_no", "subnet_nos", "subnet_no_list"),
        )
        vpc_ids = self._values(details, ("vpc_no",))

        if category == "SUBNET":
            self._relations_to_targets(
                node, "VPC", vpc_ids, "CONTAINS", "details.vpc_no",
                nodes, lookup, edges, allowed_references,
            )
        elif category in self.WORKLOAD_CATEGORIES:
            self._relations_to_targets(
                node, "SUBNET", subnet_ids, "CONTAINS",
                "details.subnet_no", nodes, lookup, edges,
                allowed_references,
            )
            if not subnet_ids:
                self._relations_to_targets(
                    node, "VPC", vpc_ids, "CONTAINS", "details.vpc_no",
                    nodes, lookup, edges, allowed_references,
                )
        elif category == "PUBLIC_IP":
            server_ids = self._values(
                details,
                ("server_instance_no", "attached_server_id"),
            )
            nic_ids = self._values(
                details,
                ("network_interface_no", "network_interface_nos"),
            )
            self._relations_to_targets(
                node, "SERVER", server_ids, "ASSIGNED_TO",
                "details.server_instance_no", nodes, lookup, edges,
                allowed_references,
            )
            self._relations_to_targets(
                node, "NETWORK_INTERFACE", nic_ids, "ASSIGNED_TO",
                "details.network_interface_no", nodes, lookup, edges,
                allowed_references,
            )
            if not server_ids and not nic_ids:
                self._relations_to_targets(
                    node, "VPC", vpc_ids, "CONTAINS", "details.vpc_no",
                    nodes, lookup, edges, allowed_references,
                )

        if category == "SERVER":
            nic_ids = self._values(
                details,
                ("network_interface_no", "network_interface_nos"),
            )
            public_ip_ids = self._values(
                details,
                ("public_ip_instance_nos", "public_ip_instance_no_list"),
            )
            self._relations_to_targets(
                node, "NETWORK_INTERFACE", nic_ids, "ATTACHED_TO",
                "details.network_interface_no", nodes, lookup, edges,
                allowed_references,
            )
            self._relations_to_targets(
                node, "PUBLIC_IP", public_ip_ids, "ASSIGNED_TO",
                "details.public_ip_instance_no", nodes, lookup, edges,
                allowed_references,
            )
        elif category == "BLOCK_STORAGE":
            server_ids = self._values(
                details,
                ("attached_server_id", "server_instance_no"),
            )
            self._relations_to_targets(
                node, "SERVER", server_ids, "ATTACHED_STORAGE",
                "details.attached_server_id", nodes, lookup, edges,
                allowed_references,
            )
        elif category == "BLOCK_STORAGE_SNAPSHOT":
            storage_ids = self._values(
                details,
                ("block_storage_instance_no",),
            )
            self._relations_to_targets(
                node, "BLOCK_STORAGE", storage_ids, "HAS_SNAPSHOT",
                "details.block_storage_instance_no", nodes, lookup, edges,
                allowed_references,
            )
        elif category == "LOAD_BALANCER":
            target_group_ids = self._values(
                details,
                ("target_group_no", "target_group_nos"),
            )
            target_server_ids = self._values(
                details,
                ("target_server_instance_no", "target_server_instance_nos"),
            )
            self._relations_to_targets(
                node, "TARGET_GROUP", target_group_ids, "TARGETS",
                "details.target_group_no", nodes, lookup, edges,
                allowed_references,
            )
            self._relations_to_targets(
                node, "SERVER", target_server_ids, "TARGETS",
                "details.target_server_instance_no", nodes, lookup, edges,
                allowed_references,
            )
        elif category == "VPC_PEERING":
            source_vpc_ids = self._values(details, ("source_vpc_no",))
            target_vpc_ids = self._values(details, ("target_vpc_no",))
            for vpc_id in source_vpc_ids:
                if "VPC" not in allowed_references:
                    continue
                vpc_node = self._target_node(
                    "VPC", vpc_id, "details.source_vpc_no",
                    nodes, lookup,
                )
                self._store_edge(
                    edges, vpc_node, node, "PEERS_FROM",
                    "details.source_vpc_no",
                )
            for vpc_id in target_vpc_ids:
                if "VPC" not in allowed_references:
                    continue
                vpc_node = self._target_node(
                    "VPC", vpc_id, "details.target_vpc_no",
                    nodes, lookup,
                )
                self._store_edge(
                    edges, node, vpc_node, "PEERS_TO",
                    "details.target_vpc_no",
                )

    def _relations_to_targets(
        self,
        source_node: Mapping[str, Any],
        target_category: str,
        target_ids: Sequence[str],
        relation_type: str,
        source_field: str,
        nodes: Dict[str, Dict[str, Any]],
        lookup: Dict[tuple[str, str], str],
        edges: Dict[tuple[str, str, str], Dict[str, Any]],
        allowed_references: frozenset[str],
    ) -> None:
        if target_category not in allowed_references:
            return
        for target_id in target_ids:
            target_node = self._target_node(
                target_category,
                target_id,
                source_field,
                nodes,
                lookup,
            )
            oriented = self._orient_relation(
                source_node,
                target_node,
                relation_type,
            )
            self._store_edge(
                edges,
                oriented[0],
                oriented[1],
                oriented[2],
                source_field,
            )

    def _orient_relation(
        self,
        source_node: Mapping[str, Any],
        target_node: Mapping[str, Any],
        relation_type: str,
    ) -> tuple[Mapping[str, Any], Mapping[str, Any], str]:
        source_category = str(source_node["category"])
        target_category = str(target_node["category"])
        relation = relation_type or "RELATED_TO"

        if target_category == "VPC" and source_category != "VPC_PEERING":
            return target_node, source_node, "CONTAINS"
        if target_category == "SUBNET":
            return target_node, source_node, "CONTAINS"
        if source_category == "BLOCK_STORAGE" and target_category == "SERVER":
            return target_node, source_node, "ATTACHED_STORAGE"
        if (
            source_category == "BLOCK_STORAGE_SNAPSHOT"
            and target_category == "BLOCK_STORAGE"
        ):
            return target_node, source_node, "HAS_SNAPSHOT"
        if source_category == "SERVER" and target_category in {
            "NETWORK_INTERFACE",
            "PUBLIC_IP",
        }:
            return target_node, source_node, (
                "ATTACHED_TO"
                if target_category == "NETWORK_INTERFACE"
                else "ASSIGNED_TO"
            )
        if target_category == "PUBLIC_IP" and source_category in {
            "NAT_GATEWAY",
            "LOAD_BALANCER",
            "SERVER",
            "NETWORK_INTERFACE",
        }:
            return target_node, source_node, "ASSIGNED_TO"
        if source_category == "LOAD_BALANCER" and target_category in {
            "TARGET_GROUP",
            "SERVER",
        }:
            return source_node, target_node, "TARGETS"
        if source_category == "VPC_PEERING" and target_category == "VPC":
            if "SOURCE" in relation:
                return target_node, source_node, "PEERS_FROM"
            return source_node, target_node, "PEERS_TO"
        return source_node, target_node, relation

    def _target_node(
        self,
        category: str,
        resource_id: str,
        source: str,
        nodes: Dict[str, Dict[str, Any]],
        lookup: Dict[tuple[str, str], str],
    ) -> Dict[str, Any]:
        existing_id = lookup.get((category, resource_id))
        if existing_id is not None:
            return nodes[existing_id]
        node_id = self._node_id(category, resource_id)
        node = nodes.get(node_id)
        if node is None:
            node = {
                "node_id": node_id,
                "category": category,
                "category_label": REPRESENTATIVE_CATEGORY_LABELS.get(
                    category,
                    category.replace("_", " ").title(),
                ),
                "resource_type": category,
                "resource_id": resource_id,
                "name": None,
                "private_ips": [],
                "public_ips": [],
                "network_cidrs": [],
                "status": None,
                "zone": None,
                "platform": None,
                "kind": "supporting",
                "reference_kind": "REFERENCE_ONLY",
                "count_as_infrastructure": False,
                "source": source,
                "confidence": "VERIFIED",
                "resolution": "UNRESOLVED",
                "is_mapped": True,
            }
            nodes[node_id] = node
        lookup[(category, resource_id)] = node_id
        return node

    def _store_edge(
        self,
        edges: Dict[tuple[str, str, str], Dict[str, Any]],
        source_node: Mapping[str, Any],
        target_node: Mapping[str, Any],
        relationship: str,
        source: str,
    ) -> None:
        source_id = str(source_node["node_id"])
        target_id = str(target_node["node_id"])
        if source_id == target_id:
            return
        normalized_relationship = self._relation_token(relationship)
        key = (source_id, target_id, normalized_relationship)
        existing = edges.get(key)
        if existing is not None:
            evidence = existing.setdefault("sources", [existing["source"]])
            if source not in evidence:
                evidence.append(source)
                existing["source"] = " | ".join(evidence)
            return
        edges[key] = {
            "edge_id": f"{source_id}|{normalized_relationship}|{target_id}",
            "source_node_id": source_id,
            "target_node_id": target_id,
            "relationship": normalized_relationship,
            "source": source,
            "sources": [source],
            "confidence": "VERIFIED",
        }

    def _inventory_node(
        self,
        node_id: str,
        category: str,
        resource_id: Optional[str],
        resource: Mapping[str, Any],
        details: Mapping[str, Any],
    ) -> Dict[str, Any]:
        source_parts = [
            self._string(details.get("inventory_source")),
            self._string(details.get("source_product")),
            self._string(details.get("source_resource_type")),
        ]
        source = " / ".join(part for part in source_parts if part)
        private_ips = self._valid_ip_values(
            self._field_values(
                resource,
                details,
                self.PRIVATE_IP_FIELDS,
            )
        )
        public_ips = self._valid_ip_values(
            self._field_values(
                resource,
                details,
                self.PUBLIC_IP_FIELDS,
            )
        )
        generic_ips = self._valid_ip_values(
            self._primitive_values(details.get("ip_addresses"))
        )
        network_type = self._relation_token(details.get("network_type"))
        if network_type in self.PUBLIC_NETWORK_TYPES:
            public_ips = self._unique_strings(public_ips + generic_ips)
        elif network_type in self.PRIVATE_NETWORK_TYPES:
            private_ips = self._unique_strings(private_ips + generic_ips)

        return {
            "node_id": node_id,
            "category": category,
            "category_label": self._string(resource.get("category_label"))
            or REPRESENTATIVE_CATEGORY_LABELS[category],
            "resource_type": self._string(resource.get("resource_type"))
            or category,
            "resource_id": resource_id,
            "name": self._string(resource.get("resource_name")),
            "private_ips": private_ips,
            "public_ips": public_ips,
            "network_cidrs": self._valid_network_values(
                self._field_values(
                    resource,
                    details,
                    self.CIDR_FIELDS,
                )
            ),
            "status": self._string(resource.get("status")),
            "zone": self._string(resource.get("zone_code")),
            "platform": self._string(resource.get("platform")),
            "kind": "representative",
            "reference_kind": None,
            "count_as_infrastructure": True,
            "source": source or "normalized_inventory",
            "confidence": "VERIFIED",
            "resolution": "RESOLVED",
            "is_mapped": False,
        }

    def _resource_id(
        self,
        category: str,
        resource: Mapping[str, Any],
        details: Mapping[str, Any],
    ) -> Optional[str]:
        resource_id = self._string(resource.get("resource_id"))
        if resource_id:
            return resource_id
        for field in self.ID_FIELDS.get(category, ()):
            resource_id = self._string(details.get(field))
            if resource_id:
                return resource_id
        return None

    def _field_values(
        self,
        resource: Mapping[str, Any],
        details: Mapping[str, Any],
        field_names: Sequence[str],
    ) -> List[str]:
        result = []
        for container in (resource, details):
            for field in field_names:
                for value in self._primitive_values(container.get(field)):
                    if value not in result:
                        result.append(value)
        return result

    @staticmethod
    def _valid_ip_values(values: Iterable[str]) -> List[str]:
        result = []
        for value in values:
            try:
                normalized = str(ip_address(value.strip()))
            except ValueError:
                continue
            if normalized not in result:
                result.append(normalized)
        return result

    @staticmethod
    def _valid_network_values(values: Iterable[str]) -> List[str]:
        result = []
        for value in values:
            rendered = value.strip()
            if "/" not in rendered:
                continue
            try:
                normalized = str(ip_network(rendered, strict=False))
            except ValueError:
                continue
            if normalized not in result:
                result.append(normalized)
        return result

    def _truncate(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        limit: int,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        if len(nodes) <= limit:
            return list(nodes), list(edges)

        node_by_id = {node["node_id"]: node for node in nodes}
        selected_ids = set()
        selected_edges = []
        for edge in sorted(edges, key=self._edge_sort_key):
            endpoints = {
                edge["source_node_id"],
                edge["target_node_id"],
            }
            missing = endpoints - selected_ids
            if len(selected_ids) + len(missing) > limit:
                continue
            selected_ids.update(missing)
            selected_edges.append(edge)

        for node in sorted(nodes, key=self._node_sort_key):
            if len(selected_ids) >= limit:
                break
            selected_ids.add(node["node_id"])

        selected_nodes = [
            node_by_id[node_id]
            for node_id in selected_ids
            if node_id in node_by_id
        ]
        selected_edges = [
            edge for edge in selected_edges
            if (
                edge["source_node_id"] in selected_ids
                and edge["target_node_id"] in selected_ids
            )
        ]
        return selected_nodes, selected_edges

    def _values(
        self,
        details: Mapping[str, Any],
        field_names: Sequence[str],
    ) -> List[str]:
        result = []
        for field_name in field_names:
            for value in self._primitive_values(details.get(field_name)):
                if value not in result:
                    result.append(value)
        return result

    def _primitive_values(self, value: Any) -> List[str]:
        candidates = value if isinstance(value, (list, tuple)) else [value]
        result = []
        for candidate in candidates:
            rendered = self._string(candidate)
            if rendered and rendered not in result:
                result.append(rendered)
        return result

    @staticmethod
    def _unique_strings(values: Iterable[str]) -> List[str]:
        result = []
        for value in values:
            if value not in result:
                result.append(value)
        return result

    def _merge_node(
        self,
        existing: Dict[str, Any],
        candidate: Mapping[str, Any],
    ) -> None:
        for field in (
            "category_label",
            "resource_type",
            "resource_id",
            "name",
            "status",
            "zone",
            "platform",
            "source",
        ):
            if not existing.get(field) and candidate.get(field):
                existing[field] = candidate[field]
        for list_field in ("private_ips", "public_ips", "network_cidrs"):
            values = existing.setdefault(list_field, [])
            for value in candidate.get(list_field) or []:
                if value not in values:
                    values.append(value)

    def _node_sort_key(self, node: Mapping[str, Any]) -> tuple[Any, ...]:
        category = str(node.get("category") or "")
        try:
            category_order = REPRESENTATIVE_CATEGORIES.index(category)
        except ValueError:
            category_order = len(REPRESENTATIVE_CATEGORIES)
        return (
            0 if node.get("is_mapped") else 1,
            category_order,
            str(node.get("name") or "").casefold(),
            str(node.get("resource_id") or ""),
            str(node.get("node_id") or ""),
        )

    @staticmethod
    def _edge_sort_key(edge: Mapping[str, Any]) -> tuple[str, str, str]:
        return (
            str(edge.get("source_node_id") or ""),
            str(edge.get("target_node_id") or ""),
            str(edge.get("relationship") or ""),
        )

    def _category(self, value: Any) -> str:
        token = self._relation_token(value)
        return self.CATEGORY_ALIASES.get(token, token)

    @staticmethod
    def _relation_token(value: Any) -> str:
        rendered = str(value or "").strip().upper()
        return "_".join(part for part in rendered.replace("-", "_").split("_") if part)

    @staticmethod
    def _node_id(
        category: str,
        resource_id: Optional[str],
        *,
        index: Optional[int] = None,
        discriminator: Optional[str] = None,
    ) -> str:
        if resource_id:
            if discriminator:
                suffix = sha256(
                    discriminator.encode("utf-8")
                ).hexdigest()[:10]
                return f"{category}:{resource_id}:{suffix}"
            return f"{category}:{resource_id}"
        return f"{category}:UNIDENTIFIED:{index if index is not None else 'REF'}"

    @staticmethod
    def _max_nodes(value: Optional[int]) -> int:
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        return InfrastructureTopologyBuilder.DEFAULT_MAX_NODES

    @staticmethod
    def _mapping(value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _mapping_items(
        value: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        if isinstance(value, (str, bytes, Mapping)):
            return []
        try:
            return [dict(item) for item in value if isinstance(item, Mapping)]
        except TypeError:
            return []

    @staticmethod
    def _string(value: Any) -> Optional[str]:
        if value is None or isinstance(value, (dict, list, tuple, set)):
            return None
        rendered = str(value).strip()
        return rendered[:500] if rendered else None


__all__ = [
    "InfrastructureTopologyBuilder",
    "REPRESENTATIVE_CATEGORIES",
    "REPRESENTATIVE_CATEGORY_LABELS",
    "TopologyDisplayOptions",
]

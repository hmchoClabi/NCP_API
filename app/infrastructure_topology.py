"""수집 API가 명시한 관계만 사용해 결정적인 인프라 토폴로지를 만든다."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, fields
from hashlib import sha256
from ipaddress import ip_address, ip_network
from math import isfinite
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from app.report_options import (
    RESOURCE_CATEGORY_LABELS,
    RESOURCE_CATEGORY_OPTIONS,
)

REPRESENTATIVE_CATEGORY_LABELS = dict(RESOURCE_CATEGORY_LABELS)
REPRESENTATIVE_CATEGORIES = tuple(RESOURCE_CATEGORY_OPTIONS)
SUPPORTING_CATEGORIES = frozenset({"NETWORK_INTERFACE", "TARGET_GROUP"})
OMITTED_TOPOLOGY_CATEGORIES = frozenset({
    "BLOCK_STORAGE_SNAPSHOT",
    "CERTIFICATE",
    "CLOUD_FUNCTIONS",
    "SERVER_IMAGE",
    "VIRTUAL_PRIVATE_GATEWAY",
})
SERVER_EMBEDDED_CATEGORIES = frozenset({
    "BLOCK_STORAGE",
    "NETWORK_INTERFACE",
    "PUBLIC_IP",
})
TOPOLOGY_PRESENTATION_POLICY_VERSION = 1
TOPOLOGY_PRESENTATION_POLICY_MODE = "IDEMPOTENT_MIGRATION"
PRESENTATION_RELATIONSHIP_GAP_FIELDS = frozenset({
    "retained_ambiguous_auxiliary_count",
    "retained_unverified_nat_subnet_count",
})


@dataclass
class _TopologyGraph:
    """노드 식별과 명시 관계 연결 단계가 공유하는 내부 그래프 상태."""

    nodes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    lookup: Dict[tuple[str, str], str] = field(default_factory=dict)
    resource_nodes: List[tuple[Dict[str, Any], Mapping[str, Any]]] = field(
        default_factory=list
    )
    edges: Dict[tuple[str, str, str], Dict[str, Any]] = field(
        default_factory=dict
    )
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    presentation: Dict[str, int] = field(default_factory=dict)


@dataclass
class _TopologySelection:
    """표시 제한을 적용한 그래프와 전체 그래프의 품질 통계."""

    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    unmapped_nodes: List[Dict[str, Any]]
    unresolved_nodes: List[Dict[str, Any]]
    full_edge_count: int
    full_unmapped_count: int
    full_unresolved_count: int
    omitted_node_count: int


@dataclass(frozen=True)
class TopologyDisplayOptions:
    """구성도에 표시할 선택적 자원 속성을 정의한다."""

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
    """이름·IP·CIDR 추론 없이 노드와 검증된 관계만 생성한다."""

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
        "CLOUD_FUNCTION": "CLOUD_FUNCTIONS",
        "FUNCTION": "CLOUD_FUNCTIONS",
        "FUNCTIONS": "CLOUD_FUNCTIONS",
        "VGW": "VIRTUAL_PRIVATE_GATEWAY",
        "VPC_GATEWAY": "VIRTUAL_PRIVATE_GATEWAY",
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
        allowed_categories = self._allowed_categories(
            allowed_reference_categories
        )
        allowed_references = allowed_categories | SUPPORTING_CATEGORIES
        resource_items = self._mapping_items(resources)
        graph = self._build_resource_graph(resource_items, allowed_categories)
        self._connect_resource_graph(graph, allowed_references)
        graph.presentation = self._apply_presentation_policy(graph)
        full_edges = list(graph.edges.values())
        self._mark_mapped_nodes(graph.nodes, full_edges)
        selection = self._select_topology(graph.nodes, full_edges, limit)
        (
            normalized_completeness,
            normalized_issue_count,
            relationship_coverage,
            confidence,
        ) = self._topology_quality(
            selection,
            inventory_completeness,
            collection_issue_count,
        )
        if any(
            graph.presentation.get(field_name)
            for field_name in PRESENTATION_RELATIONSHIP_GAP_FIELDS
        ):
            relationship_coverage = "PARTIAL"
            confidence = "PARTIAL"
        self._append_topology_warnings(graph.warnings, selection, limit)
        selection.nodes.sort(key=self._node_sort_key)
        selection.edges.sort(key=self._edge_sort_key)
        return self._topology_payload(
            selection,
            graph.warnings,
            collected_at=collected_at,
            max_nodes=limit,
            confidence=confidence,
            relationship_coverage=relationship_coverage,
            inventory_completeness=normalized_completeness,
            collection_issue_count=normalized_issue_count,
            presentation=graph.presentation,
        )

    def _select_topology(
        self,
        nodes: Dict[str, Dict[str, Any]],
        edges: List[Dict[str, Any]],
        limit: int,
    ) -> _TopologySelection:
        full_nodes = list(nodes.values())
        selected_nodes, selected_edges = self._truncate(
            full_nodes,
            edges,
            limit,
        )
        return _TopologySelection(
            nodes=selected_nodes,
            edges=selected_edges,
            unmapped_nodes=[
                node for node in selected_nodes
                if (
                    node["kind"] == "representative"
                    and not node.get("is_mapped")
                )
            ],
            unresolved_nodes=[
                node for node in selected_nodes
                if node.get("resolution") == "UNRESOLVED"
            ],
            full_edge_count=len(edges),
            full_unmapped_count=sum(
                1 for node in full_nodes
                if (
                    node["kind"] == "representative"
                    and not node.get("is_mapped")
                )
            ),
            full_unresolved_count=sum(
                1 for node in full_nodes
                if node.get("resolution") == "UNRESOLVED"
            ),
            omitted_node_count=len(full_nodes) - len(selected_nodes),
        )

    @staticmethod
    def _topology_quality(
        selection: _TopologySelection,
        inventory_completeness: str,
        collection_issue_count: int,
    ) -> tuple[str, int, str, str]:
        normalized_completeness = str(
            inventory_completeness or "UNKNOWN"
        ).strip().upper()[:60]
        try:
            normalized_issue_count = max(int(collection_issue_count or 0), 0)
        except (TypeError, ValueError):
            normalized_issue_count = 0
        relationship_coverage = (
            "PARTIAL"
            if (
                selection.full_unmapped_count
                or selection.full_unresolved_count
            )
            else "COMPLETE"
        )
        confidence = (
            "PARTIAL"
            if (
                selection.full_unmapped_count
                or selection.full_unresolved_count
                or selection.omitted_node_count
                or normalized_issue_count
                or normalized_completeness
                not in {
                    "COMPLETE",
                    "COMPLETE_FOR_SELECTED_SCOPE",
                    "COMPLETE_FOR_SNAPSHOT_SCOPE",
                }
            )
            else "VERIFIED"
        )
        return (
            normalized_completeness,
            normalized_issue_count,
            relationship_coverage,
            confidence,
        )

    @staticmethod
    def _append_topology_warnings(
        warnings: List[Dict[str, Any]],
        selection: _TopologySelection,
        limit: int,
    ) -> None:
        if selection.full_unmapped_count:
            warnings.append({
                "code": "UNMAPPED_RESOURCES",
                "message": (
                    "명시적인 리소스 ID 관계가 없어 미매핑 그룹에 "
                    f"{selection.full_unmapped_count}개 자원을 표시합니다."
                ),
                "source": "normalized_inventory",
                "confidence": "UNMAPPED",
            })
        if selection.full_unresolved_count:
            warnings.append({
                "code": "UNRESOLVED_REFERENCES",
                "message": (
                    "관계 대상 ID는 확인되었지만 인벤토리에서 상세 자원을 "
                    f"찾지 못한 참조가 {selection.full_unresolved_count}개 있습니다."
                ),
                "source": "explicit_resource_id_relation",
                "confidence": "VERIFIED",
            })
        if selection.omitted_node_count:
            warnings.append({
                "code": "TOPOLOGY_TRUNCATED",
                "message": (
                    f"구성도 노드 제한({limit}개)으로 "
                    f"{selection.omitted_node_count}개 노드를 생략했습니다."
                ),
                "source": "renderer_limit",
                "confidence": "VERIFIED",
            })

    @staticmethod
    def _topology_payload(
        selection: _TopologySelection,
        warnings: List[Dict[str, Any]],
        *,
        collected_at: Optional[str],
        max_nodes: int,
        confidence: str,
        relationship_coverage: str,
        inventory_completeness: str,
        collection_issue_count: int,
        presentation: Mapping[str, int],
    ) -> Dict[str, Any]:
        selected_ids = {node["node_id"] for node in selection.nodes}
        return {
            "nodes": selection.nodes,
            "edges": selection.edges,
            "unmapped_node_ids": [
                node["node_id"] for node in selection.unmapped_nodes
                if node["node_id"] in selected_ids
            ],
            "unresolved_node_ids": [
                node["node_id"] for node in selection.unresolved_nodes
                if node["node_id"] in selected_ids
            ],
            "warnings": warnings,
            "summary": {
                "representative_node_count": sum(
                    1 for node in selection.nodes
                    if node.get("count_as_infrastructure")
                ),
                "supporting_node_count": sum(
                    1 for node in selection.nodes
                    if not node.get("count_as_infrastructure")
                ),
                "verified_edge_count": len(selection.edges),
                "total_verified_edge_count": selection.full_edge_count,
                "unmapped_resource_count": selection.full_unmapped_count,
                "unresolved_reference_count": (
                    selection.full_unresolved_count
                ),
                "collected_at": collected_at,
                "max_nodes": max_nodes,
                "truncated": bool(selection.omitted_node_count),
                "omitted_node_count": selection.omitted_node_count,
                "confidence": confidence,
                "relationship_confidence": "VERIFIED",
                "relationship_coverage": relationship_coverage,
                "inventory_completeness": inventory_completeness,
                "collection_issue_count": collection_issue_count,
                "presentation_policy_version": (
                    TOPOLOGY_PRESENTATION_POLICY_VERSION
                ),
                "presentation_policy_mode": TOPOLOGY_PRESENTATION_POLICY_MODE,
                "presentation_policy": dict(presentation),
            },
        }

    def _allowed_categories(
        self,
        values: Optional[Iterable[str]],
    ) -> frozenset[str]:
        if values is None:
            return frozenset(REPRESENTATIVE_CATEGORIES)
        return frozenset(
            category
            for category in (self._category(value) for value in values)
            if category in REPRESENTATIVE_CATEGORY_LABELS
        )

    def _build_resource_graph(
        self,
        resources: List[Dict[str, Any]],
        allowed_categories: frozenset[str],
    ) -> _TopologyGraph:
        """명시 ID를 기준으로 자원 노드를 만들고 충돌 ID를 분리한다."""
        graph = _TopologyGraph()
        identity_counts: Dict[tuple[str, str], int] = {}
        for resource in resources:
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

        for index, resource in enumerate(resources):
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
                identity_key and identity_counts.get(identity_key, 0) > 1
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
            candidate = self._inventory_node(
                node_id,
                category,
                resource_id,
                resource,
                details,
            )
            if identity_collision:
                # 같은 category/ID가 여러 원본 자원을 가리키면 표시 단계에서
                # 임의로 하나로 합치지 않도록 충돌 사실을 보존한다.
                candidate["identity_collision"] = True
            node = graph.nodes.get(node_id)
            if node is None:
                graph.nodes[node_id] = candidate
                node = candidate
            else:
                self._merge_node(node, candidate)
            if resource_id and not identity_collision:
                graph.lookup[(category, resource_id)] = node_id
            graph.resource_nodes.append((node, resource))
        return graph

    def _connect_resource_graph(
        self,
        graph: _TopologyGraph,
        allowed_references: frozenset[str],
    ) -> None:
        """API가 리소스 ID로 밝힌 관계만 그래프 간선으로 연결한다."""
        for node, resource in graph.resource_nodes:
            details = self._mapping(resource.get("details"))
            self._add_explicit_relations(
                node,
                details,
                graph.nodes,
                graph.lookup,
                graph.edges,
                graph.warnings,
                allowed_references,
            )
            self._add_field_relations(
                node,
                details,
                graph.nodes,
                graph.lookup,
                graph.edges,
                allowed_references,
            )

    def _apply_presentation_policy(
        self,
        graph: _TopologyGraph,
    ) -> Dict[str, int]:
        """보고서 구성도에서 보조 자원을 안전하게 축약한다.

        자원 이름이나 IP가 비슷하다는 이유로 관계를 만들지 않는다. 수집기가
        남긴 명시적 자원 ID edge만 사용하며, 서버 ID가 충돌하거나 여러 서버로
        연결된 보조 자원은 독립 노드로 유지한다.
        """
        metadata = {
            "embedded_node_count": 0,
            "embedded_block_storage_count": 0,
            "embedded_network_interface_count": 0,
            "embedded_public_ip_count": 0,
            "excluded_category_node_count": 0,
            "excluded_nat_subnet_count": 0,
            "excluded_orphan_reference_count": 0,
            "retained_ambiguous_auxiliary_count": 0,
            "retained_unverified_nat_subnet_count": 0,
            "removed_edge_count": 0,
        }

        excluded_ids = {
            node_id
            for node_id, node in graph.nodes.items()
            if str(node.get("category") or "")
            in OMITTED_TOPOLOGY_CATEGORIES
        }
        metadata["excluded_category_node_count"] = len(excluded_ids)
        metadata["removed_edge_count"] += self._remove_nodes(
            graph,
            excluded_ids,
        )

        for node in graph.nodes.values():
            if node.get("category") == "NAT_GATEWAY":
                # 실제 위치를 단정하지 않고 렌더러에 VPC 경계 배치 의도만 전달한다.
                node["placement_hint"] = "VPC_BOUNDARY"

        edges_by_source, edges_by_target = self._edge_endpoint_index(
            graph.edges.values()
        )
        (
            nat_subnet_ids,
            retained_unverified_nat_subnet_count,
        ) = self._collapsible_nat_subnet_ids(
            graph,
            edges_by_source,
            edges_by_target,
        )
        self._bridge_nat_subnet_relations(
            graph,
            nat_subnet_ids,
            edges_by_source,
            edges_by_target,
        )
        metadata["excluded_nat_subnet_count"] = len(nat_subnet_ids)
        metadata["retained_unverified_nat_subnet_count"] = (
            retained_unverified_nat_subnet_count
        )
        metadata["removed_edge_count"] += self._remove_nodes(
            graph,
            nat_subnet_ids,
        )

        edges_by_source, edges_by_target = self._edge_endpoint_index(
            graph.edges.values()
        )
        embedded_ids, ambiguous_count = self._embed_server_auxiliaries(
            graph,
            edges_by_source,
            edges_by_target,
        )
        for node_id in embedded_ids:
            category = str(graph.nodes[node_id].get("category") or "")
            metadata["embedded_node_count"] += 1
            counter = {
                "BLOCK_STORAGE": "embedded_block_storage_count",
                "NETWORK_INTERFACE": "embedded_network_interface_count",
                "PUBLIC_IP": "embedded_public_ip_count",
            }.get(category)
            if counter:
                metadata[counter] += 1
        metadata["retained_ambiguous_auxiliary_count"] = ambiguous_count
        metadata["removed_edge_count"] += self._remove_nodes(
            graph,
            embedded_ids,
        )
        orphan_ids = self._orphan_supporting_node_ids(graph)
        metadata["excluded_orphan_reference_count"] = len(orphan_ids)
        metadata["removed_edge_count"] += self._remove_nodes(
            graph,
            orphan_ids,
        )

        if ambiguous_count and not any(
            warning.get("code") == "AUXILIARY_RESOURCE_NOT_EMBEDDED"
            for warning in graph.warnings
        ):
            graph.warnings.append({
                "code": "AUXILIARY_RESOURCE_NOT_EMBEDDED",
                "message": (
                    "서버와의 명시적 1:1 관계를 확인할 수 없는 보조 자원 "
                    f"{ambiguous_count}개는 서버 노드에 병합하지 않았습니다."
                ),
                "source": "explicit_resource_id_relation",
                "confidence": "PARTIAL",
            })
        if retained_unverified_nat_subnet_count and not any(
            warning.get("code") == "NAT_SUBNET_NOT_COLLAPSED"
            for warning in graph.warnings
        ):
            graph.warnings.append({
                "code": "NAT_SUBNET_NOT_COLLAPSED",
                "message": (
                    "NAT 전용으로 보이지만 명시적인 NAT Gateway 소속과 "
                    "단일 VPC 상위 관계를 모두 확인하지 못한 Subnet "
                    f"{retained_unverified_nat_subnet_count}개를 유지했습니다."
                ),
                "source": "explicit_resource_id_relation",
                "confidence": "PARTIAL",
            })
        return metadata

    def _collapsible_nat_subnet_ids(
        self,
        graph: _TopologyGraph,
        edges_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
        edges_by_target: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> tuple[set[str], int]:
        """NAT 전용임을 명시적으로 확인한 subnet만 숨긴다."""
        result: set[str] = set()
        retained_unverified_count = 0
        for subnet_id, subnet in graph.nodes.items():
            if subnet.get("category") != "SUBNET":
                continue
            child_edges = [
                edge
                for edge in edges_by_source.get(subnet_id, ())
                if edge.get("relationship") == "CONTAINS"
            ]
            has_general_workload = any(
                graph.nodes.get(str(edge.get("target_node_id")), {}).get(
                    "category"
                )
                != "NAT_GATEWAY"
                for edge in child_edges
            )
            if has_general_workload:
                continue

            usage_type = self._relation_token(
                subnet.get("subnet_usage_type")
            )
            usage_is_nat = usage_type in {"NATGW", "NAT_GATEWAY"}
            nat_child_edges = [
                edge
                for edge in child_edges
                if graph.nodes.get(
                    str(edge.get("target_node_id")), {}
                ).get("category") == "NAT_GATEWAY"
            ]
            nat_memberships = [
                edge
                for edge in nat_child_edges
                if self._is_nat_subnet_membership(edge)
            ]
            vpc_parent_ids = {
                str(edge.get("source_node_id"))
                for edge in edges_by_target.get(subnet_id, ())
                if (
                    edge.get("relationship") == "CONTAINS"
                    and graph.nodes.get(
                        str(edge.get("source_node_id")), {}
                    ).get("category")
                    == "VPC"
                )
            }
            looks_like_nat_subnet = usage_is_nat or bool(nat_child_edges)
            if not looks_like_nat_subnet:
                continue
            if nat_memberships and len(vpc_parent_ids) == 1:
                result.add(subnet_id)
                continue

            # API 일부 실패나 충돌 상태에서 subnet만 지우면 실제 구성보다
            # 단정적인 그림이 되므로 원본 노드를 남기고 품질을 낮춘다.
            subnet["confidence"] = "PARTIAL"
            retained_unverified_count += 1
        return result, retained_unverified_count

    def _bridge_nat_subnet_relations(
        self,
        graph: _TopologyGraph,
        subnet_ids: set[str],
        edges_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
        edges_by_target: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> None:
        """숨길 NAT subnet의 검증된 VPC 관계를 NAT Gateway로 승계한다."""
        for subnet_id in subnet_ids:
            vpc_edges = [
                edge
                for edge in edges_by_target.get(subnet_id, ())
                if (
                    edge.get("relationship") == "CONTAINS"
                    and graph.nodes.get(
                        str(edge.get("source_node_id")), {}
                    ).get("category")
                    == "VPC"
                )
            ]
            nat_edges = [
                edge
                for edge in edges_by_source.get(subnet_id, ())
                if (
                    edge.get("relationship") == "CONTAINS"
                    and graph.nodes.get(
                        str(edge.get("target_node_id")), {}
                    ).get("category")
                    == "NAT_GATEWAY"
                    and self._is_nat_subnet_membership(edge)
                )
            ]
            for vpc_edge in vpc_edges:
                vpc = graph.nodes.get(str(vpc_edge.get("source_node_id")))
                if vpc is None:
                    continue
                for nat_edge in nat_edges:
                    nat = graph.nodes.get(str(nat_edge.get("target_node_id")))
                    if nat is None:
                        continue
                    evidence = self._unique_strings(
                        self._edge_sources(vpc_edge)
                        + self._edge_sources(nat_edge)
                    )
                    self._store_edge(
                        graph.edges,
                        vpc,
                        nat,
                        "CONTAINS",
                        " | ".join(evidence)
                        or "explicit_resource_id_relation",
                    )

    def _embed_server_auxiliaries(
        self,
        graph: _TopologyGraph,
        edges_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
        edges_by_target: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> tuple[set[str], int]:
        embedded_ids: set[str] = set()
        ambiguous_count = 0
        ambiguous_identity_ids = self._ambiguous_auxiliary_node_ids(graph)
        expected_relationships = {
            "BLOCK_STORAGE": {"ATTACHED_STORAGE", "ATTACHED_TO"},
            "NETWORK_INTERFACE": {"ATTACHED_TO", "USES"},
            "PUBLIC_IP": {"ASSIGNED_TO"},
        }
        for auxiliary_id, auxiliary in graph.nodes.items():
            category = str(auxiliary.get("category") or "")
            if category not in SERVER_EMBEDDED_CATEGORIES:
                continue
            if auxiliary_id in ambiguous_identity_ids:
                auxiliary["confidence"] = "PARTIAL"
                ambiguous_count += 1
                continue
            server_ids = set()
            incident_edges = (
                *edges_by_source.get(auxiliary_id, ()),
                *edges_by_target.get(auxiliary_id, ()),
            )
            for edge in incident_edges:
                if edge.get("relationship") not in expected_relationships[category]:
                    continue
                source_id = str(edge.get("source_node_id") or "")
                target_id = str(edge.get("target_node_id") or "")
                other_id = None
                if source_id == auxiliary_id:
                    other_id = target_id
                elif target_id == auxiliary_id:
                    other_id = source_id
                if (
                    other_id
                    and graph.nodes.get(other_id, {}).get("category") == "SERVER"
                ):
                    server_ids.add(other_id)
            if not server_ids:
                continue
            if (
                category == "PUBLIC_IP"
                and self._has_non_server_public_ip_assignment(
                    auxiliary_id,
                    graph,
                    incident_edges,
                )
            ):
                ambiguous_count += 1
                continue
            if len(server_ids) != 1:
                ambiguous_count += 1
                continue
            server = graph.nodes[next(iter(server_ids))]
            if not self._resolved_server_node(server):
                ambiguous_count += 1
                continue
            self._embed_auxiliary(server, auxiliary)
            embedded_ids.add(auxiliary_id)
        return embedded_ids, ambiguous_count

    @staticmethod
    def _ambiguous_auxiliary_node_ids(graph: _TopologyGraph) -> set[str]:
        """동일 category/ID가 여러 노드를 뜻하는 보조 자원을 찾는다."""

        nodes_by_identity: Dict[tuple[str, str], List[str]] = {}
        ambiguous_ids = {
            node_id
            for node_id, node in graph.nodes.items()
            if (
                node.get("category") in SERVER_EMBEDDED_CATEGORIES
                and node.get("identity_collision") is True
            )
        }
        for node_id, node in graph.nodes.items():
            category = str(node.get("category") or "")
            resource_id = str(node.get("resource_id") or "").strip()
            if category not in SERVER_EMBEDDED_CATEGORIES or not resource_id:
                continue
            nodes_by_identity.setdefault((category, resource_id), []).append(
                node_id
            )
        for node_ids in nodes_by_identity.values():
            if len(node_ids) > 1:
                ambiguous_ids.update(node_ids)
        return ambiguous_ids

    @staticmethod
    def _has_non_server_public_ip_assignment(
        public_ip_id: str,
        graph: _TopologyGraph,
        edges: Sequence[Mapping[str, Any]],
    ) -> bool:
        for edge in edges:
            if edge.get("relationship") not in {"ASSIGNED_TO", "USES"}:
                continue
            source_id = str(edge.get("source_node_id") or "")
            target_id = str(edge.get("target_node_id") or "")
            if source_id == public_ip_id:
                other_id = target_id
            elif target_id == public_ip_id:
                other_id = source_id
            else:
                continue
            if graph.nodes.get(other_id, {}).get("category") != "SERVER":
                return True
        return False

    @staticmethod
    def _orphan_supporting_node_ids(graph: _TopologyGraph) -> set[str]:
        connected_ids = {
            str(edge.get(field) or "")
            for edge in graph.edges.values()
            for field in ("source_node_id", "target_node_id")
        }
        return {
            node_id
            for node_id, node in graph.nodes.items()
            if node.get("kind") == "supporting" and node_id not in connected_ids
        }

    def _embed_auxiliary(
        self,
        server: Dict[str, Any],
        auxiliary: Mapping[str, Any],
    ) -> None:
        category = str(auxiliary.get("category") or "")
        if category == "BLOCK_STORAGE":
            disks = server.setdefault("attached_disks", [])
            disk = {
                "resource_id": auxiliary.get("resource_id"),
                "name": auxiliary.get("name"),
                "size_gb": auxiliary.get("storage_size_gb"),
                "storage_type": auxiliary.get("storage_type"),
                "disk_type": auxiliary.get("disk_type"),
                "volume_type": auxiliary.get("volume_type"),
            }
            self._append_unique_resource(disks, disk, auxiliary)
            disks.sort(key=self._embedded_resource_sort_key)
            server["attached_disk_count"] = len(disks)
            known_sizes = [
                self._nonnegative_number(disk_item.get("size_gb"))
                for disk_item in disks
            ]
            server["attached_disk_capacity_known_count"] = sum(
                value is not None for value in known_sizes
            )
            server["attached_disk_total_gb"] = (
                self._sum_numbers(known_sizes)
                if known_sizes and all(value is not None for value in known_sizes)
                else None
            )
            return

        if category == "NETWORK_INTERFACE":
            interfaces = server.setdefault("network_interfaces", [])
            interface = {
                "resource_id": auxiliary.get("resource_id"),
                "private_ips": list(auxiliary.get("private_ips") or []),
                "public_ips": list(auxiliary.get("public_ips") or []),
            }
            self._append_unique_resource(interfaces, interface, auxiliary)
            interfaces.sort(key=self._embedded_resource_sort_key)
            server["network_interface_count"] = len(interfaces)
            self._merge_network_values(server, auxiliary)
            return

        if category == "PUBLIC_IP":
            public_ip_ids = server.setdefault("public_ip_resource_ids", [])
            resource_id = self._string(auxiliary.get("resource_id"))
            if resource_id and resource_id not in public_ip_ids:
                public_ip_ids.append(resource_id)
                public_ip_ids.sort()
            server["public_ip_resource_count"] = len(public_ip_ids)
            self._merge_network_values(server, auxiliary)

    @staticmethod
    def _append_unique_resource(
        resources: List[Dict[str, Any]],
        candidate: Dict[str, Any],
        source_node: Mapping[str, Any],
    ) -> None:
        identity = (
            str(candidate.get("resource_id") or ""),
            str(source_node.get("node_id") or ""),
        )
        for existing in resources:
            existing_identity = (
                str(existing.get("resource_id") or ""),
                str(existing.get("node_id") or ""),
            )
            if (
                existing_identity == identity
                or (
                    identity[0]
                    and existing_identity[0] == identity[0]
                )
            ):
                return
        candidate["node_id"] = source_node.get("node_id")
        resources.append(candidate)

    @staticmethod
    def _embedded_resource_sort_key(
        resource: Mapping[str, Any],
    ) -> tuple[str, str]:
        return (
            str(resource.get("name") or "").casefold(),
            str(resource.get("resource_id") or resource.get("node_id") or ""),
        )

    @staticmethod
    def _resolved_server_node(node: Mapping[str, Any]) -> bool:
        resolution = str(node.get("resolution") or "").upper()
        if resolution:
            return resolution == "RESOLVED"
        return bool(
            node.get("kind") == "representative" and node.get("resource_id")
        )

    def _merge_network_values(
        self,
        server: Dict[str, Any],
        auxiliary: Mapping[str, Any],
    ) -> None:
        for field in ("private_ips", "public_ips"):
            values = server.setdefault(field, [])
            for value in auxiliary.get(field) or []:
                if value not in values:
                    values.append(value)
            values.sort(key=self._network_value_sort_key)

    @staticmethod
    def _network_value_sort_key(value: Any) -> tuple[Any, ...]:
        """IP는 주소값으로, 비정상 legacy 값은 문자열로 안정 정렬한다."""

        rendered = str(value).strip()
        try:
            address = ip_address(rendered)
        except ValueError:
            return 1, rendered.casefold(), rendered
        return 0, address.version, int(address)

    @staticmethod
    def _remove_nodes(graph: _TopologyGraph, node_ids: set[str]) -> int:
        if not node_ids:
            return 0
        for node_id in node_ids:
            graph.nodes.pop(node_id, None)
        removed_edges = 0
        retained_edges = {}
        for key, edge in graph.edges.items():
            if (
                edge.get("source_node_id") in node_ids
                or edge.get("target_node_id") in node_ids
            ):
                removed_edges += 1
                continue
            retained_edges[key] = edge
        graph.edges = retained_edges
        return removed_edges

    @staticmethod
    def _edge_sources(edge: Mapping[str, Any]) -> List[str]:
        sources = edge.get("sources")
        if isinstance(sources, (list, tuple)):
            return [str(source) for source in sources if str(source).strip()]
        source = str(edge.get("source") or "").strip()
        return [source] if source else []

    @staticmethod
    def _edge_endpoint_index(
        edges: Iterable[Mapping[str, Any]],
    ) -> tuple[
        Dict[str, List[Mapping[str, Any]]],
        Dict[str, List[Mapping[str, Any]]],
    ]:
        """간선을 출발점과 도착점별로 한 번만 색인한다."""
        edges_by_source: Dict[str, List[Mapping[str, Any]]] = {}
        edges_by_target: Dict[str, List[Mapping[str, Any]]] = {}
        for edge in edges:
            source_id = str(edge.get("source_node_id") or "")
            target_id = str(edge.get("target_node_id") or "")
            if source_id:
                edges_by_source.setdefault(source_id, []).append(edge)
            if target_id:
                edges_by_target.setdefault(target_id, []).append(edge)
        return edges_by_source, edges_by_target

    @classmethod
    def _is_nat_subnet_membership(cls, edge: Mapping[str, Any]) -> bool:
        valid_sources = {
            "subnetno",
            "details.subnet_no",
            "natgateway.subnetno",
        }
        return any(
            source.strip().lower() in valid_sources
            for source in cls._edge_sources(edge)
        )

    @staticmethod
    def _nonnegative_number(value: Any) -> Optional[float | int]:
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if not isfinite(number) or number < 0:
            return None
        return int(number) if number.is_integer() else number

    @staticmethod
    def _sum_numbers(values: Iterable[Optional[float | int]]) -> float | int:
        total = sum(float(value) for value in values if value is not None)
        return int(total) if total.is_integer() else round(total, 6)

    @staticmethod
    def _mark_mapped_nodes(
        nodes: Dict[str, Dict[str, Any]],
        edges: List[Dict[str, Any]],
    ) -> None:
        degree = {node_id: 0 for node_id in nodes}
        for edge in edges:
            degree[edge["source_node_id"]] += 1
            degree[edge["target_node_id"]] += 1
        for node_id, node in nodes.items():
            node["is_mapped"] = degree.get(node_id, 0) > 0
            if (
                not node["is_mapped"]
                and node.get("kind", "representative") == "representative"
            ):
                node["confidence"] = "UNMAPPED"

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

        node = {
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
        if category == "SERVER":
            node.update({
                "network_interfaces": [],
                "network_interface_count": 0,
                "attached_disks": [],
                "attached_disk_count": 0,
                "attached_disk_capacity_known_count": 0,
                "attached_disk_total_gb": None,
                "public_ip_resource_ids": [],
                "public_ip_resource_count": 0,
            })
        elif category == "BLOCK_STORAGE":
            node.update({
                "storage_size_gb": self._nonnegative_number(
                    details.get("size_gb")
                ),
                "storage_type": self._string(details.get("storage_type")),
                "disk_type": self._string(details.get("disk_type")),
                "volume_type": self._string(details.get("volume_type")),
            })
        elif category == "SUBNET":
            node["subnet_usage_type"] = self._relation_token(
                details.get("usage_type")
            ) or None
        elif category == "NAT_GATEWAY":
            node["placement_hint"] = "VPC_BOUNDARY"
        return node

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

    @classmethod
    def _valid_ip_values(cls, values: Iterable[str]) -> List[str]:
        result = []
        for value in values:
            try:
                normalized = str(ip_address(value.strip()))
            except ValueError:
                continue
            if normalized not in result:
                result.append(normalized)
        result.sort(key=cls._network_value_sort_key)
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
            "storage_size_gb",
            "storage_type",
            "disk_type",
            "volume_type",
            "subnet_usage_type",
            "placement_hint",
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


def apply_topology_presentation_policy(value: Any) -> Dict[str, Any]:
    """저장 시점이 오래된 구성도에도 현재 표시 정책을 동일하게 적용한다.

    입력 객체를 변경하지 않으며, 이미 정책이 적용된 payload에 다시 호출해도
    자원 수와 메타데이터가 중복 증가하지 않는다.
    """
    if not isinstance(value, Mapping):
        return {}
    result = deepcopy(dict(value))
    raw_nodes = result.get("nodes")
    raw_edges = result.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        return result

    graph = _TopologyGraph()
    builder = InfrastructureTopologyBuilder()
    for raw_node in raw_nodes:
        if not isinstance(raw_node, Mapping):
            continue
        node = dict(raw_node)
        node_id = str(node.get("node_id") or "").strip()
        if not node_id or node_id in graph.nodes:
            continue
        category = builder._category(node.get("category"))
        node["category"] = category
        representative = category in REPRESENTATIVE_CATEGORY_LABELS
        node.setdefault("kind", "representative" if representative else "supporting")
        node.setdefault("count_as_infrastructure", representative)
        node.setdefault(
            "resolution",
            "RESOLVED" if node.get("resource_id") else "UNRESOLVED",
        )
        node.setdefault("confidence", "VERIFIED")
        graph.nodes[node_id] = node
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, Mapping):
            continue
        edge = dict(raw_edge)
        source_id = str(edge.get("source_node_id") or "").strip()
        target_id = str(edge.get("target_node_id") or "").strip()
        relationship = InfrastructureTopologyBuilder._relation_token(
            edge.get("relationship")
        )
        if (
            not source_id
            or not target_id
            or source_id not in graph.nodes
            or target_id not in graph.nodes
            or not relationship
        ):
            continue
        edge["source_node_id"] = source_id
        edge["target_node_id"] = target_id
        edge["relationship"] = relationship
        graph.edges[(source_id, target_id, relationship)] = edge
    raw_warnings = result.get("warnings")
    graph.warnings = [
        dict(warning)
        for warning in raw_warnings
        if isinstance(warning, Mapping)
    ] if isinstance(raw_warnings, list) else []

    current_metadata = builder._apply_presentation_policy(graph)
    visible_edges = list(graph.edges.values())
    builder._mark_mapped_nodes(graph.nodes, visible_edges)
    visible_nodes = sorted(graph.nodes.values(), key=builder._node_sort_key)
    visible_edges.sort(key=builder._edge_sort_key)
    visible_ids = {str(node.get("node_id") or "") for node in visible_nodes}
    unmapped_ids = [
        str(node.get("node_id"))
        for node in visible_nodes
        if node.get("kind") == "representative" and not node.get("is_mapped")
    ]
    unresolved_ids = [
        str(node.get("node_id"))
        for node in visible_nodes
        if node.get("resolution") == "UNRESOLVED"
    ]

    summary = result.get("summary")
    summary = dict(summary) if isinstance(summary, Mapping) else {}
    existing_metadata = summary.get("presentation_policy")
    combined_metadata = (
        dict(existing_metadata)
        if isinstance(existing_metadata, Mapping)
        else {}
    )
    for key, count in current_metadata.items():
        previous = combined_metadata.get(key, 0)
        try:
            previous_count = max(int(previous), 0)
        except (TypeError, ValueError):
            previous_count = 0
        if key in PRESENTATION_RELATIONSHIP_GAP_FIELDS:
            combined_metadata[key] = max(previous_count, count)
        else:
            combined_metadata[key] = previous_count + count

    previous_total = summary.get("total_verified_edge_count")
    try:
        total_verified = max(
            int(previous_total) - current_metadata["removed_edge_count"],
            len(visible_edges),
        )
    except (TypeError, ValueError):
        total_verified = len(visible_edges)
    try:
        omitted_node_count = max(int(summary.get("omitted_node_count") or 0), 0)
    except (TypeError, ValueError):
        omitted_node_count = 0
    try:
        max_nodes = max(
            int(summary.get("max_nodes") or builder.DEFAULT_MAX_NODES),
            1,
        )
    except (TypeError, ValueError):
        max_nodes = builder.DEFAULT_MAX_NODES
    summary.update({
        "representative_node_count": sum(
            1 for node in visible_nodes if node.get("count_as_infrastructure")
        ),
        "supporting_node_count": sum(
            1 for node in visible_nodes if not node.get("count_as_infrastructure")
        ),
        "verified_edge_count": len(visible_edges),
        "total_verified_edge_count": total_verified,
        "unmapped_resource_count": len(unmapped_ids),
        "unresolved_reference_count": len(unresolved_ids),
        "presentation_policy_version": TOPOLOGY_PRESENTATION_POLICY_VERSION,
        "presentation_policy_mode": TOPOLOGY_PRESENTATION_POLICY_MODE,
        "presentation_policy": combined_metadata,
    })

    has_relationship_gap = bool(
        unmapped_ids
        or unresolved_ids
        or any(
            combined_metadata.get(field_name)
            for field_name in PRESENTATION_RELATIONSHIP_GAP_FIELDS
        )
    )
    existing_coverage = str(
        summary.get("relationship_coverage") or ""
    ).strip().upper()
    summary["relationship_coverage"] = (
        existing_coverage
        if existing_coverage in {"PARTIAL", "UNAVAILABLE"}
        else "PARTIAL" if has_relationship_gap else "COMPLETE"
    )

    try:
        collection_issue_count = max(
            int(summary.get("collection_issue_count") or 0),
            0,
        )
    except (TypeError, ValueError):
        collection_issue_count = 0
    inventory_completeness = str(
        summary.get("inventory_completeness") or ""
    ).strip().upper()
    incomplete_inventory = bool(
        inventory_completeness
        and inventory_completeness not in {
            "COMPLETE",
            "COMPLETE_FOR_SELECTED_SCOPE",
            "COMPLETE_FOR_SNAPSHOT_SCOPE",
        }
    )
    existing_confidence = str(
        summary.get("confidence") or ""
    ).strip().upper()
    if existing_confidence == "UNAVAILABLE":
        summary["confidence"] = "UNAVAILABLE"
    elif (
        existing_confidence == "PARTIAL"
        or has_relationship_gap
        or omitted_node_count
        or collection_issue_count
        or incomplete_inventory
    ):
        summary["confidence"] = "PARTIAL"
    else:
        summary["confidence"] = "VERIFIED"

    graph.warnings = [
        warning
        for warning in graph.warnings
        if warning.get("code") not in {
            "UNMAPPED_RESOURCES",
            "UNRESOLVED_REFERENCES",
            "TOPOLOGY_TRUNCATED",
        }
    ]
    selection = _TopologySelection(
        nodes=visible_nodes,
        edges=visible_edges,
        unmapped_nodes=[
            node for node in visible_nodes
            if str(node.get("node_id") or "") in unmapped_ids
        ],
        unresolved_nodes=[
            node for node in visible_nodes
            if str(node.get("node_id") or "") in unresolved_ids
        ],
        full_edge_count=total_verified,
        full_unmapped_count=len(unmapped_ids),
        full_unresolved_count=len(unresolved_ids),
        omitted_node_count=omitted_node_count,
    )
    builder._append_topology_warnings(graph.warnings, selection, max_nodes)

    result["nodes"] = visible_nodes
    result["edges"] = visible_edges
    result["unmapped_node_ids"] = [
        node_id for node_id in unmapped_ids if node_id in visible_ids
    ]
    result["unresolved_node_ids"] = [
        node_id for node_id in unresolved_ids if node_id in visible_ids
    ]
    result["warnings"] = graph.warnings
    result["summary"] = summary
    return result


__all__ = [
    "apply_topology_presentation_policy",
    "InfrastructureTopologyBuilder",
    "OMITTED_TOPOLOGY_CATEGORIES",
    "REPRESENTATIVE_CATEGORIES",
    "REPRESENTATIVE_CATEGORY_LABELS",
    "SERVER_EMBEDDED_CATEGORIES",
    "TOPOLOGY_PRESENTATION_POLICY_MODE",
    "TOPOLOGY_PRESENTATION_POLICY_VERSION",
    "TopologyDisplayOptions",
]

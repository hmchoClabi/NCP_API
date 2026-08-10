import copy
import unittest

from app.infrastructure_topology import (
    InfrastructureTopologyBuilder,
    TOPOLOGY_PRESENTATION_POLICY_MODE,
    TOPOLOGY_PRESENTATION_POLICY_VERSION,
    apply_topology_presentation_policy,
)


class _CountingEdgeList(list):
    def __init__(self, values, owner):
        super().__init__(values)
        self._owner = owner

    def __iter__(self):
        self._owner.edge_visit_count += len(self)
        return super().__iter__()


class _IndexedVisitTrackingBuilder(InfrastructureTopologyBuilder):
    def __init__(self):
        self.index_build_count = 0
        self.indexed_edge_count = 0
        self.edge_visit_count = 0

    def _edge_endpoint_index(self, edges):
        edges_by_source, edges_by_target = super()._edge_endpoint_index(edges)
        self.index_build_count += 1
        self.indexed_edge_count += sum(
            len(indexed_edges) for indexed_edges in edges_by_source.values()
        )
        wrapped_source = {
            node_id: _CountingEdgeList(indexed_edges, self)
            for node_id, indexed_edges in edges_by_source.items()
        }
        wrapped_target = {
            node_id: _CountingEdgeList(indexed_edges, self)
            for node_id, indexed_edges in edges_by_target.items()
        }
        return wrapped_source, wrapped_target


class TopologyPresentationPolicyTests(unittest.TestCase):
    def test_exact_server_auxiliaries_are_embedded_and_not_drawn(self):
        topology = InfrastructureTopologyBuilder().build([
            self._resource("VPC", "vpc-1", "main-vpc"),
            self._resource(
                "SUBNET",
                "subnet-1",
                "app-subnet",
                details={"vpc_no": "vpc-1"},
            ),
            self._resource(
                "SERVER",
                "server-1",
                "app-1",
                details={
                    "subnet_no": "subnet-1",
                    "private_ips": ["10.0.1.10"],
                    "network_interface_nos": ["nic-1"],
                },
            ),
            self._resource(
                "BLOCK_STORAGE",
                "disk-1",
                "data-disk",
                details={
                    "attached_server_id": "server-1",
                    "size_gb": 250,
                    "storage_type": "SSD",
                },
            ),
            self._resource(
                "PUBLIC_IP",
                "public-ip-1",
                "app-egress",
                details={
                    "server_instance_no": "server-1",
                    "public_ip": "203.0.113.10",
                },
            ),
        ])

        self.assertEqual(
            {node["category"] for node in topology["nodes"]},
            {"VPC", "SUBNET", "SERVER"},
        )
        server = next(
            node for node in topology["nodes"] if node["category"] == "SERVER"
        )
        self.assertEqual(server["network_interface_count"], 1)
        self.assertEqual(
            server["network_interfaces"][0]["resource_id"],
            "nic-1",
        )
        self.assertEqual(server["attached_disk_count"], 1)
        self.assertEqual(server["attached_disk_total_gb"], 250)
        self.assertEqual(server["attached_disks"][0]["name"], "data-disk")
        self.assertEqual(server["public_ips"], ["203.0.113.10"])
        self.assertEqual(server["public_ip_resource_ids"], ["public-ip-1"])
        self.assertFalse(
            any(
                endpoint.startswith(
                    ("BLOCK_STORAGE:", "NETWORK_INTERFACE:", "PUBLIC_IP:")
                )
                for edge in topology["edges"]
                for endpoint in (
                    edge["source_node_id"],
                    edge["target_node_id"],
                )
            )
        )
        metadata = topology["summary"]["presentation_policy"]
        self.assertEqual(metadata["embedded_block_storage_count"], 1)
        self.assertEqual(metadata["embedded_network_interface_count"], 1)
        self.assertEqual(metadata["embedded_public_ip_count"], 1)

    def test_ambiguous_server_identity_does_not_embed_storage(self):
        topology = InfrastructureTopologyBuilder().build([
            self._resource(
                "SERVER",
                "same-server-id",
                "classic",
                platform="CLASSIC",
            ),
            self._resource(
                "SERVER",
                "same-server-id",
                "vpc",
                platform="VPC",
            ),
            self._resource(
                "BLOCK_STORAGE",
                "disk-1",
                "ambiguous-disk",
                details={
                    "attached_server_id": "same-server-id",
                    "size_gb": 100,
                },
            ),
        ])

        self.assertIn(
            "BLOCK_STORAGE",
            {node["category"] for node in topology["nodes"]},
        )
        self.assertTrue(
            any(
                warning["code"] == "AUXILIARY_RESOURCE_NOT_EMBEDDED"
                for warning in topology["warnings"]
            )
        )
        self.assertEqual(
            topology["summary"]["presentation_policy"][
                "retained_ambiguous_auxiliary_count"
            ],
            1,
        )

    def test_auxiliary_output_categories_are_omitted_without_mutating_input(self):
        resources = [
            self._resource(category, f"id-{index}", f"resource-{index}")
            for index, category in enumerate((
                "CERTIFICATE",
                "CLOUD_FUNCTIONS",
                "BLOCK_STORAGE_SNAPSHOT",
                "SERVER_IMAGE",
                "VIRTUAL_PRIVATE_GATEWAY",
            ))
        ]
        original = copy.deepcopy(resources)

        topology = InfrastructureTopologyBuilder().build(resources)

        self.assertEqual(resources, original)
        self.assertEqual(topology["nodes"], [])
        self.assertEqual(
            topology["summary"]["presentation_policy"][
                "excluded_category_node_count"
            ],
            5,
        )

    def test_nat_dedicated_subnet_is_collapsed_to_verified_vpc_relation(self):
        topology = InfrastructureTopologyBuilder().build([
            self._resource("VPC", "vpc-1", "main-vpc"),
            self._resource(
                "SUBNET",
                "nat-subnet",
                "nat-only",
                details={
                    "vpc_no": "vpc-1",
                    "usage_type": "NATGW",
                },
            ),
            self._resource(
                "NAT_GATEWAY",
                "nat-1",
                "egress",
                details={
                    "vpc_no": "vpc-1",
                    "subnet_no": "nat-subnet",
                },
            ),
        ])

        self.assertNotIn(
            "nat-subnet",
            {node["resource_id"] for node in topology["nodes"]},
        )
        nat = next(
            node
            for node in topology["nodes"]
            if node["category"] == "NAT_GATEWAY"
        )
        self.assertEqual(nat["placement_hint"], "VPC_BOUNDARY")
        self.assertIn(
            ("VPC:vpc-1", "NAT_GATEWAY:nat-1", "CONTAINS"),
            {
                (
                    edge["source_node_id"],
                    edge["target_node_id"],
                    edge["relationship"],
                )
                for edge in topology["edges"]
            },
        )

    def test_empty_subnet_is_excluded_but_populated_subnet_is_retained(self):
        topology = InfrastructureTopologyBuilder().build([
            self._resource("VPC", "vpc-1", "main-vpc"),
            self._resource(
                "SUBNET",
                "empty-subnet",
                "empty",
                details={"vpc_no": "vpc-1"},
            ),
            self._resource(
                "SUBNET",
                "app-subnet",
                "application",
                details={"vpc_no": "vpc-1"},
            ),
            self._resource(
                "SERVER",
                "server-1",
                "app",
                details={"subnet_no": "app-subnet"},
            ),
        ])

        subnet_ids = {
            node["resource_id"]
            for node in topology["nodes"]
            if node["category"] == "SUBNET"
        }
        self.assertEqual(subnet_ids, {"app-subnet"})
        self.assertEqual(
            topology["summary"]["presentation_policy"][
                "excluded_empty_subnet_count"
            ],
            1,
        )
        self.assertNotIn(
            "SUBNET:empty-subnet",
            {
                str(edge[field])
                for edge in topology["edges"]
                for field in ("source_node_id", "target_node_id")
            },
        )

    def test_non_contains_relation_does_not_populate_subnet(self):
        topology = InfrastructureTopologyBuilder().build([
            self._resource("VPC", "vpc-1", "main-vpc"),
            self._resource(
                "SUBNET",
                "empty-subnet",
                "empty",
                details={
                    "vpc_no": "vpc-1",
                    "explicit_relations": [{
                        "type": "ROUTES_TO",
                        "target_category": "NAT_GATEWAY",
                        "target_id": "nat-1",
                        "source_field": "routeList[].targetNo",
                    }],
                },
            ),
            self._resource(
                "NAT_GATEWAY",
                "nat-1",
                "egress",
                details={"vpc_no": "vpc-1"},
            ),
        ])

        self.assertNotIn(
            "empty-subnet",
            {node["resource_id"] for node in topology["nodes"]},
        )
        self.assertEqual(
            topology["summary"]["presentation_policy"][
                "excluded_empty_subnet_count"
            ],
            1,
        )

    def test_nat_subnet_with_server_workload_is_not_collapsed(self):
        topology = InfrastructureTopologyBuilder().build([
            self._resource("VPC", "vpc-1", "main-vpc"),
            self._resource(
                "SUBNET",
                "shared-subnet",
                "shared",
                details={
                    "vpc_no": "vpc-1",
                    "usage_type": "NATGW",
                },
            ),
            self._resource(
                "NAT_GATEWAY",
                "nat-1",
                "egress",
                details={"subnet_no": "shared-subnet"},
            ),
            self._resource(
                "SERVER",
                "server-1",
                "app",
                details={"subnet_no": "shared-subnet"},
            ),
        ])

        self.assertIn(
            "shared-subnet",
            {node["resource_id"] for node in topology["nodes"]},
        )

    def test_nat_subnet_without_explicit_membership_is_removed_when_empty(self):
        topology = InfrastructureTopologyBuilder().build(
            [
                self._resource("VPC", "vpc-1", "main-vpc"),
                self._resource(
                    "SUBNET",
                    "nat-subnet",
                    "nat-only",
                    details={
                        "vpc_no": "vpc-1",
                        "usage_type": "NATGW",
                    },
                ),
            ],
            allowed_reference_categories=("VPC", "SUBNET"),
        )

        self.assertNotIn(
            "nat-subnet",
            {node.get("resource_id") for node in topology["nodes"]},
        )
        self.assertEqual(topology["summary"]["confidence"], "PARTIAL")
        self.assertEqual(
            topology["summary"]["presentation_policy"][
                "retained_unverified_nat_subnet_count"
            ],
            0,
        )
        self.assertEqual(
            topology["summary"]["presentation_policy"][
                "excluded_empty_subnet_count"
            ],
            1,
        )
        self.assertNotIn(
            "NAT_SUBNET_NOT_COLLAPSED",
            {warning["code"] for warning in topology["warnings"]},
        )
        self.assertEqual(
            apply_topology_presentation_policy(topology),
            topology,
        )

    def test_nat_subnet_with_multiple_vpc_parents_is_not_collapsed(self):
        topology = InfrastructureTopologyBuilder().build([
            self._resource("VPC", "vpc-1", "main-vpc"),
            self._resource("VPC", "vpc-2", "other-vpc"),
            self._resource(
                "SUBNET",
                "nat-subnet",
                "ambiguous-nat-subnet",
                details={
                    "vpc_no": "vpc-1",
                    "usage_type": "NATGW",
                    "explicit_relations": [{
                        "type": "BELONGS_TO",
                        "target_category": "VPC",
                        "target_id": "vpc-2",
                        "source_field": "legacy.secondaryVpcNo",
                    }],
                },
            ),
            self._resource(
                "NAT_GATEWAY",
                "nat-1",
                "egress",
                details={"subnet_no": "nat-subnet"},
            ),
        ])

        self.assertIn(
            "nat-subnet",
            {node["resource_id"] for node in topology["nodes"]},
        )
        self.assertEqual(
            topology["summary"]["presentation_policy"][
                "retained_unverified_nat_subnet_count"
            ],
            1,
        )
        self.assertEqual(topology["summary"]["confidence"], "PARTIAL")

    def test_route_to_nat_does_not_make_an_ordinary_subnet_dedicated(self):
        topology = InfrastructureTopologyBuilder().build([
            self._resource("VPC", "vpc-1", "main-vpc"),
            self._resource(
                "SUBNET",
                "app-subnet",
                "app",
                details={
                    "vpc_no": "vpc-1",
                    "explicit_relations": [{
                        "type": "ROUTES_TO",
                        "target_category": "NAT_GATEWAY",
                        "target_id": "nat-1",
                        "source_field": "routeList[].targetNo",
                    }],
                },
            ),
            self._resource("NAT_GATEWAY", "nat-1", "egress"),
            self._resource(
                "SERVER",
                "server-1",
                "app-server",
                details={"subnet_no": "app-subnet"},
            ),
        ])

        self.assertIn(
            "app-subnet",
            {node["resource_id"] for node in topology["nodes"]},
        )

    def test_public_ip_with_legacy_non_server_uses_is_not_embedded(self):
        topology = InfrastructureTopologyBuilder().build([
            self._resource("SERVER", "server-1", "app"),
            self._resource("NAT_GATEWAY", "nat-1", "egress"),
            self._resource(
                "PUBLIC_IP",
                "public-ip-1",
                "shared-address",
                details={
                    "explicit_relations": [
                        {
                            "type": "ASSIGNED_TO",
                            "target_category": "SERVER",
                            "target_id": "server-1",
                            "source_field": "serverInstanceNo",
                        },
                        {
                            "type": "USES",
                            "target_category": "NAT_GATEWAY",
                            "target_id": "nat-1",
                            "source_field": "natGatewayInstanceNo",
                        },
                    ],
                },
            ),
        ])

        self.assertIn(
            "PUBLIC_IP",
            {node["category"] for node in topology["nodes"]},
        )
        self.assertEqual(topology["summary"]["confidence"], "PARTIAL")

    def test_colliding_auxiliary_identity_is_not_embedded_or_deleted(self):
        topology = InfrastructureTopologyBuilder().build([
            self._resource("SERVER", "server-1", "app"),
            self._resource(
                "BLOCK_STORAGE",
                "disk-1",
                "classic-disk",
                platform="CLASSIC",
                details={
                    "source_nrn": "nrn:classic:disk-1",
                    "attached_server_id": "server-1",
                    "size_gb": 100,
                },
            ),
            self._resource(
                "BLOCK_STORAGE",
                "disk-1",
                "vpc-disk",
                platform="VPC",
                details={
                    "source_nrn": "nrn:vpc:disk-1",
                    "attached_server_id": "server-1",
                    "size_gb": 200,
                },
            ),
        ])

        disks = [
            node for node in topology["nodes"]
            if node["category"] == "BLOCK_STORAGE"
        ]
        server = next(
            node for node in topology["nodes"]
            if node["category"] == "SERVER"
        )
        self.assertEqual(len(disks), 2)
        self.assertFalse(server.get("attached_disks"))
        self.assertTrue(all(node["confidence"] == "PARTIAL" for node in disks))
        self.assertEqual(
            topology["summary"]["presentation_policy"][
                "retained_ambiguous_auxiliary_count"
            ],
            2,
        )
        self.assertEqual(topology["summary"]["confidence"], "PARTIAL")

    def test_merged_public_ips_have_canonical_order(self):
        resources = [
            self._resource(
                "SERVER",
                "server-1",
                "app",
                details={
                    "private_ips": [
                        "2001:db8::20",
                        "10.0.0.10",
                        "10.0.0.2",
                    ],
                },
            ),
            self._resource(
                "PUBLIC_IP",
                "public-ip-10",
                "address-10",
                details={
                    "server_instance_no": "server-1",
                    "public_ip": "203.0.113.10",
                },
            ),
            self._resource(
                "PUBLIC_IP",
                "public-ip-2",
                "address-2",
                details={
                    "server_instance_no": "server-1",
                    "public_ip": "203.0.113.2",
                },
            ),
            self._resource(
                "PUBLIC_IP",
                "public-ip-v6",
                "address-v6",
                details={
                    "server_instance_no": "server-1",
                    "public_ip": "2001:db8::1",
                },
            ),
        ]

        forward = InfrastructureTopologyBuilder().build(resources)
        reversed_result = InfrastructureTopologyBuilder().build(
            list(reversed(resources))
        )
        for topology in (forward, reversed_result):
            server = next(
                node for node in topology["nodes"]
                if node["category"] == "SERVER"
            )
            self.assertEqual(
                server["public_ips"],
                ["203.0.113.2", "203.0.113.10", "2001:db8::1"],
            )
            self.assertEqual(
                server["private_ips"],
                ["10.0.0.2", "10.0.0.10", "2001:db8::20"],
            )

    def test_large_inventory_uses_endpoint_indices_for_presentation_policy(self):
        server_count = 400
        nat_count = 200
        resources = [self._resource("VPC", "vpc-1", "main-vpc")]
        for index in range(nat_count):
            subnet_id = f"nat-subnet-{index}"
            resources.extend([
                self._resource(
                    "SUBNET",
                    subnet_id,
                    subnet_id,
                    details={"vpc_no": "vpc-1", "usage_type": "NATGW"},
                ),
                self._resource(
                    "NAT_GATEWAY",
                    f"nat-{index}",
                    f"nat-{index}",
                    details={"subnet_no": subnet_id},
                ),
            ])
        for index in range(server_count):
            server_id = f"server-{index}"
            resources.extend([
                self._resource(
                    "SERVER",
                    server_id,
                    server_id,
                    details={
                        "network_interface_nos": [f"nic-{index}"],
                        "private_ips": [
                            f"10.{index // 250}.{index % 250}.10"
                        ],
                    },
                ),
                self._resource(
                    "BLOCK_STORAGE",
                    f"disk-{index}",
                    f"disk-{index}",
                    details={
                        "attached_server_id": server_id,
                        "size_gb": 100,
                    },
                ),
                self._resource(
                    "PUBLIC_IP",
                    f"public-ip-{index}",
                    f"public-ip-{index}",
                    details={
                        "server_instance_no": server_id,
                        "public_ip": (
                            f"203.0.{index // 250}.{index % 250 + 1}"
                        ),
                    },
                ),
            ])

        builder = _IndexedVisitTrackingBuilder()
        topology = builder.build(resources, max_nodes=1000)

        metadata = topology["summary"]["presentation_policy"]
        self.assertEqual(metadata["excluded_nat_subnet_count"], nat_count)
        self.assertEqual(
            metadata["embedded_block_storage_count"],
            server_count,
        )
        self.assertEqual(
            metadata["embedded_network_interface_count"],
            server_count,
        )
        self.assertEqual(
            metadata["embedded_public_ip_count"],
            server_count,
        )
        self.assertEqual(builder.index_build_count, 2)
        self.assertGreater(builder.indexed_edge_count, 0)
        self.assertLessEqual(
            builder.edge_visit_count,
            builder.indexed_edge_count * 2,
        )

    def test_presentation_policy_is_idempotent_for_stored_topology(self):
        topology = InfrastructureTopologyBuilder().build([
            self._resource("SERVER", "server-1", "app"),
            self._resource(
                "BLOCK_STORAGE",
                "disk-1",
                "data",
                details={"attached_server_id": "server-1", "size_gb": 50},
            ),
        ])

        reapplied = apply_topology_presentation_policy(topology)

        self.assertEqual(reapplied, topology)
        self.assertEqual(
            topology["summary"]["presentation_policy_version"],
            TOPOLOGY_PRESENTATION_POLICY_VERSION,
        )
        self.assertEqual(
            topology["summary"]["presentation_policy_mode"],
            TOPOLOGY_PRESENTATION_POLICY_MODE,
        )

    def test_stored_topology_migrates_empty_subnet_once(self):
        stored_topology = {
            "nodes": [
                {
                    "node_id": "VPC:vpc-1",
                    "category": "VPC",
                    "resource_id": "vpc-1",
                },
                {
                    "node_id": "SUBNET:empty-subnet",
                    "category": "SUBNET",
                    "resource_id": "empty-subnet",
                },
            ],
            "edges": [{
                "source_node_id": "VPC:vpc-1",
                "target_node_id": "SUBNET:empty-subnet",
                "relationship": "CONTAINS",
                "confidence": "VERIFIED",
            }],
            "warnings": [],
            "summary": {
                "presentation_policy_version": 1,
                "presentation_policy": {},
                "confidence": "VERIFIED",
                "relationship_coverage": "COMPLETE",
                "inventory_completeness": "COMPLETE",
                "collection_issue_count": 0,
            },
        }

        migrated = apply_topology_presentation_policy(stored_topology)

        self.assertEqual(
            [node["resource_id"] for node in migrated["nodes"]],
            ["vpc-1"],
        )
        self.assertEqual(migrated["edges"], [])
        self.assertEqual(
            migrated["summary"]["presentation_policy"][
                "excluded_empty_subnet_count"
            ],
            1,
        )
        self.assertEqual(
            migrated["summary"]["presentation_policy_version"],
            TOPOLOGY_PRESENTATION_POLICY_VERSION,
        )
        self.assertEqual(
            apply_topology_presentation_policy(migrated),
            migrated,
        )

    def test_stored_duplicate_auxiliary_identity_is_retained(self):
        stored_topology = {
            "nodes": [
                {
                    "node_id": "SERVER:server-1",
                    "category": "SERVER",
                    "resource_id": "server-1",
                    "kind": "representative",
                    "count_as_infrastructure": True,
                    "resolution": "RESOLVED",
                },
                {
                    "node_id": "BLOCK_STORAGE:disk-1:classic",
                    "category": "BLOCK_STORAGE",
                    "resource_id": "disk-1",
                    "name": "classic-disk",
                    "kind": "representative",
                    "count_as_infrastructure": True,
                    "resolution": "RESOLVED",
                },
                {
                    "node_id": "BLOCK_STORAGE:disk-1:vpc",
                    "category": "BLOCK_STORAGE",
                    "resource_id": "disk-1",
                    "name": "vpc-disk",
                    "kind": "representative",
                    "count_as_infrastructure": True,
                    "resolution": "RESOLVED",
                },
            ],
            "edges": [
                {
                    "source_node_id": "SERVER:server-1",
                    "target_node_id": "BLOCK_STORAGE:disk-1:classic",
                    "relationship": "ATTACHED_STORAGE",
                    "source": "details.attached_server_id",
                    "confidence": "VERIFIED",
                },
                {
                    "source_node_id": "SERVER:server-1",
                    "target_node_id": "BLOCK_STORAGE:disk-1:vpc",
                    "relationship": "ATTACHED_STORAGE",
                    "source": "details.attached_server_id",
                    "confidence": "VERIFIED",
                },
            ],
            "warnings": [],
            "summary": {
                "confidence": "VERIFIED",
                "relationship_coverage": "COMPLETE",
                "inventory_completeness": "COMPLETE",
                "collection_issue_count": 0,
            },
        }

        topology = apply_topology_presentation_policy(stored_topology)

        self.assertEqual(
            sum(
                node["category"] == "BLOCK_STORAGE"
                for node in topology["nodes"]
            ),
            2,
        )
        server = next(
            node for node in topology["nodes"]
            if node["category"] == "SERVER"
        )
        self.assertFalse(server.get("attached_disks"))
        self.assertEqual(
            topology["summary"]["presentation_policy"][
                "retained_ambiguous_auxiliary_count"
            ],
            2,
        )
        self.assertEqual(topology["summary"]["confidence"], "PARTIAL")
        self.assertEqual(
            apply_topology_presentation_policy(topology),
            topology,
        )

    def test_stored_topology_quality_is_recalculated_after_embedding(self):
        stored_topology = {
            "nodes": [
                {
                    "node_id": "SERVER:server-1",
                    "category": "SERVER",
                    "resource_id": "server-1",
                    "name": "app",
                    "kind": "representative",
                    "count_as_infrastructure": True,
                    "resolution": "RESOLVED",
                },
                {
                    "node_id": "BLOCK_STORAGE:disk-1",
                    "category": "BLOCK_STORAGE",
                    "resource_id": "disk-1",
                    "name": "data",
                    "storage_size_gb": 50,
                    "kind": "representative",
                    "count_as_infrastructure": True,
                    "resolution": "RESOLVED",
                },
            ],
            "edges": [{
                "source_node_id": "SERVER:server-1",
                "target_node_id": "BLOCK_STORAGE:disk-1",
                "relationship": "ATTACHED_STORAGE",
                "source": "details.attached_server_id",
                "confidence": "VERIFIED",
            }],
            "warnings": [],
            "summary": {
                "total_verified_edge_count": 1,
                "verified_edge_count": 1,
                "unmapped_resource_count": 0,
                "unresolved_reference_count": 0,
                "confidence": "VERIFIED",
                "relationship_coverage": "COMPLETE",
                "inventory_completeness": "COMPLETE",
                "collection_issue_count": 0,
            },
        }

        topology = apply_topology_presentation_policy(stored_topology)

        self.assertEqual(
            [node["category"] for node in topology["nodes"]],
            ["SERVER"],
        )
        self.assertEqual(topology["edges"], [])
        self.assertEqual(
            topology["unmapped_node_ids"],
            ["SERVER:server-1"],
        )
        self.assertEqual(topology["summary"]["confidence"], "PARTIAL")
        self.assertEqual(
            topology["summary"]["relationship_coverage"],
            "PARTIAL",
        )
        self.assertEqual(
            [warning["code"] for warning in topology["warnings"]],
            ["UNMAPPED_RESOURCES"],
        )

    @staticmethod
    def _resource(
        category,
        resource_id,
        name,
        *,
        details=None,
        platform="VPC",
    ):
        return {
            "category": category,
            "category_label": category,
            "service_name": category,
            "resource_type": category,
            "resource_id": resource_id,
            "resource_name": name,
            "status": "RUN",
            "region_code": "KR",
            "zone_code": "KR-1",
            "platform": platform,
            "details": {
                "inventory_source": "TEST_API",
                **(details or {}),
            },
        }


if __name__ == "__main__":
    unittest.main()

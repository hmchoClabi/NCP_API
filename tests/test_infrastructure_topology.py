import unittest

from app.infrastructure_topology import (
    InfrastructureTopologyBuilder,
    TopologyDisplayOptions,
)
from app.renderers import HtmlReportRenderer
from app.report_models import ReportResult


class InfrastructureTopologyBuilderTests(unittest.TestCase):
    def test_disabled_reference_category_is_not_reintroduced(self):
        topology = InfrastructureTopologyBuilder().build(
            [{
                "category": "LOAD_BALANCER",
                "resource_id": "lb-1",
                "resource_name": "selected-lb",
                "details": {
                    "load_balancer_instance_no": "lb-1",
                    "target_server_instance_nos": ["server-secret"],
                },
            }],
            allowed_reference_categories=["LOAD_BALANCER"],
        )

        self.assertEqual(
            {node["category"] for node in topology["nodes"]},
            {"LOAD_BALANCER"},
        )
        self.assertNotIn("server-secret", str(topology))
        self.assertEqual(topology["edges"], [])

    def test_ambiguous_cross_platform_id_is_not_joined_to_inventory_node(self):
        topology = InfrastructureTopologyBuilder().build([
            {
                "category": "SERVER",
                "resource_id": "same-id",
                "resource_name": "classic-server",
                "platform": "CLASSIC",
                "details": {"server_instance_no": "same-id"},
            },
            {
                "category": "SERVER",
                "resource_id": "same-id",
                "resource_name": "vpc-server",
                "platform": "VPC",
                "details": {"server_instance_no": "same-id"},
            },
            {
                "category": "BLOCK_STORAGE",
                "resource_id": "storage-1",
                "resource_name": "ambiguous-storage",
                "details": {
                    "block_storage_instance_no": "storage-1",
                    "server_instance_no": "same-id",
                },
            },
        ])

        server_nodes = [
            node for node in topology["nodes"]
            if node["category"] == "SERVER"
        ]
        self.assertEqual(len(server_nodes), 3)
        self.assertEqual(
            sum(node["resolution"] == "UNRESOLVED" for node in server_nodes),
            1,
        )
        storage_edges = [
            edge for edge in topology["edges"]
            if any(
                "storage-1" in str(node_id)
                for node_id in (
                    edge["source_node_id"],
                    edge["target_node_id"],
                )
            )
        ]
        self.assertEqual(len(storage_edges), 1)
        self.assertIn("SERVER:same-id", str(storage_edges[0]))

    def test_builds_only_explicit_id_relationships_with_evidence(self):
        topology = InfrastructureTopologyBuilder().build(
            [
                self._resource("VPC", "vpc-1", "shared-vpc"),
                self._resource(
                    "SUBNET",
                    "subnet-1",
                    "app-subnet",
                    details={"vpc_no": "vpc-1"},
                ),
                self._resource(
                    "SERVER",
                    "server-1",
                    "app",
                    details={
                        "vpc_no": "vpc-1",
                        "subnet_no": "subnet-1",
                        "network_interface_nos": ["nic-1"],
                    },
                ),
                self._resource(
                    "BLOCK_STORAGE",
                    "storage-1",
                    "data",
                    details={"attached_server_id": "server-1"},
                ),
                self._resource(
                    "PUBLIC_IP",
                    "public-ip-1",
                    "egress",
                    details={"server_instance_no": "server-1"},
                ),
                self._resource(
                    "LOAD_BALANCER",
                    "lb-1",
                    "frontend",
                    details={
                        "explicit_relations": [{
                            "type": "TARGETS",
                            "target_category": "SERVER",
                            "target_id": "server-1",
                            "source_field": "targetList.serverInstanceNo",
                        }],
                    },
                ),
                self._resource(
                    "CLOUD_DB",
                    "db-1",
                    "shared-vpc",
                    details={
                        "vpc_name": "shared-vpc",
                        "network_cidr": "10.0.0.0/16",
                    },
                ),
            ],
            collected_at="2026-08-07T16:00:00+09:00",
        )

        edges = {
            (
                edge["source_node_id"],
                edge["target_node_id"],
                edge["relationship"],
            )
            for edge in topology["edges"]
        }
        self.assertIn(("VPC:vpc-1", "SUBNET:subnet-1", "CONTAINS"), edges)
        self.assertIn(
            ("SUBNET:subnet-1", "SERVER:server-1", "CONTAINS"),
            edges,
        )
        self.assertIn(
            ("NETWORK_INTERFACE:nic-1", "SERVER:server-1", "ATTACHED_TO"),
            edges,
        )
        self.assertIn(
            ("SERVER:server-1", "BLOCK_STORAGE:storage-1", "ATTACHED_STORAGE"),
            edges,
        )
        self.assertIn(
            ("PUBLIC_IP:public-ip-1", "SERVER:server-1", "ASSIGNED_TO"),
            edges,
        )
        self.assertIn(
            ("LOAD_BALANCER:lb-1", "SERVER:server-1", "TARGETS"),
            edges,
        )
        self.assertFalse(
            any("db-1" in endpoint for edge in edges for endpoint in edge[:2])
        )
        self.assertIn("CLOUD_DB:db-1", topology["unmapped_node_ids"])
        self.assertTrue(
            all(edge["confidence"] == "VERIFIED" for edge in topology["edges"])
        )
        target_edge = next(
            edge for edge in topology["edges"]
            if edge["relationship"] == "TARGETS"
        )
        self.assertEqual(target_edge["source"], "targetList.serverInstanceNo")
        self.assertEqual(
            topology["summary"]["collected_at"],
            "2026-08-07T16:00:00+09:00",
        )

    def test_missing_target_is_reference_only_and_unresolved(self):
        topology = InfrastructureTopologyBuilder().build([
            self._resource(
                "LOAD_BALANCER",
                "lb-1",
                "frontend",
                details={
                    "explicit_relations": [{
                        "type": "TARGETS",
                        "target_category": "TARGET_GROUP",
                        "target_id": "tg-404",
                        "source_field": "targetGroupNo",
                    }],
                },
            )
        ])

        reference = next(
            node for node in topology["nodes"]
            if node["category"] == "TARGET_GROUP"
        )
        self.assertEqual(reference["kind"], "supporting")
        self.assertEqual(reference["reference_kind"], "REFERENCE_ONLY")
        self.assertEqual(reference["resolution"], "UNRESOLVED")
        self.assertFalse(reference["count_as_infrastructure"])
        self.assertEqual(reference["confidence"], "VERIFIED")
        self.assertEqual(topology["summary"]["unresolved_reference_count"], 1)

    def test_max_nodes_reports_truncation_without_guessing(self):
        resources = [
            self._resource("SERVER", f"server-{index}", f"server-{index}")
            for index in range(12)
        ]
        topology = InfrastructureTopologyBuilder().build(
            resources,
            max_nodes=5,
        )

        self.assertEqual(len(topology["nodes"]), 5)
        self.assertTrue(topology["summary"]["truncated"])
        self.assertEqual(topology["summary"]["omitted_node_count"], 7)
        self.assertEqual(topology["summary"]["max_nodes"], 5)
        self.assertEqual(topology["edges"], [])

    def test_invalid_network_values_and_ambiguous_fields_are_omitted(self):
        topology = InfrastructureTopologyBuilder().build([
            self._resource(
                "SERVER",
                "server-1",
                "app",
                details={
                    "private_ips": [
                        "10.0.1.5",
                        "not-an-ip",
                        "2001:db8::1",
                    ],
                    "public_ips": [
                        "203.0.113.5",
                        "public.example.com",
                    ],
                    "network_cidr": [
                        "10.0.1.7/24",
                        "not-a-cidr",
                        "192.0.2.1",
                    ],
                    "ip": "198.51.100.10",
                    "ip_address": "198.51.100.11",
                    "subnet": "172.16.0.0/16",
                },
            ),
            self._resource(
                "LOAD_BALANCER",
                "lb-public",
                "public-lb",
                details={
                    "network_type": "PUBLIC",
                    "ip_addresses": [
                        "198.51.100.20",
                        "lb.example.com",
                    ],
                },
            ),
            self._resource(
                "LOAD_BALANCER",
                "lb-private",
                "private-lb",
                details={
                    "network_type": "PRIVATE",
                    "ip_addresses": ["10.0.2.20", "invalid"],
                },
            ),
            self._resource(
                "LOAD_BALANCER",
                "lb-unknown",
                "unknown-lb",
                details={
                    "network_type": "NOT_PUBLIC",
                    "ip_addresses": ["198.51.100.30"],
                },
            ),
        ])
        nodes = {
            node["resource_id"]: node
            for node in topology["nodes"]
        }

        self.assertEqual(
            nodes["server-1"]["private_ips"],
            ["10.0.1.5", "2001:db8::1"],
        )
        self.assertEqual(
            nodes["server-1"]["public_ips"],
            ["203.0.113.5"],
        )
        self.assertEqual(
            nodes["server-1"]["network_cidrs"],
            ["10.0.1.0/24"],
        )
        self.assertEqual(
            nodes["lb-public"]["public_ips"],
            ["198.51.100.20"],
        )
        self.assertEqual(
            nodes["lb-private"]["private_ips"],
            ["10.0.2.20"],
        )
        self.assertEqual(nodes["lb-unknown"]["private_ips"], [])
        self.assertEqual(nodes["lb-unknown"]["public_ips"], [])
        self.assertNotIn("198.51.100.10", str(topology))
        self.assertNotIn("198.51.100.11", str(topology))
        self.assertNotIn("172.16.0.0/16", str(topology))
        self.assertNotIn("public.example.com", str(topology))

    @staticmethod
    def _resource(category, resource_id, name, *, details=None):
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
            "platform": "VPC",
            "details": {
                "inventory_source": "TEST_API",
                **(details or {}),
            },
        }


class InfrastructureTopologyIntegrationTests(unittest.TestCase):
    def test_report_model_keeps_new_categories_and_builds_topology(self):
        report = ReportResult(
            period={"file_suffix": "topology"},
            collection_metadata={
                "infrastructure": {
                    "completed_at": "2026-08-07T16:30:00+09:00",
                }
            },
            infrastructure=[
                InfrastructureTopologyBuilderTests._resource(
                    "VPC", "vpc-1", "vpc"
                ),
                InfrastructureTopologyBuilderTests._resource(
                    "SUBNET",
                    "subnet-1",
                    "subnet",
                    details={"vpc_no": "vpc-1"},
                ),
                {"category": "ALARM", "resource_id": "alarm-1"},
            ],
        )

        snapshot = report.to_dict()
        topology = report.display_infrastructure_topology

        self.assertEqual(
            [item["category"] for item in snapshot["infrastructure"]],
            ["VPC", "SUBNET"],
        )
        self.assertNotIn("alarm-1", str(snapshot))
        self.assertEqual(topology["summary"]["verified_edge_count"], 1)
        self.assertEqual(topology["summary"]["unmapped_resource_count"], 0)
        self.assertEqual(
            snapshot["infrastructure_topology"]["summary"]["collected_at"],
            "2026-08-07T16:30:00+09:00",
        )
        restored = ReportResult.from_dict(snapshot)
        self.assertEqual(
            restored.display_infrastructure_topology,
            snapshot["infrastructure_topology"],
        )

    def test_renderer_uses_static_svg_and_honors_sensitive_field_options(self):
        report = self._report_with_sensitive_topology()
        hidden_html = HtmlReportRenderer(
            topology_display_options={
                "show_resource_name": False,
                "show_resource_id": False,
                "show_private_ip": False,
                "show_public_ip": False,
                "show_network_cidr": False,
                "show_status": False,
                "show_zone": False,
                "show_platform": False,
                "include_unmapped_resources": False,
            }
        ).render(report)
        hidden_section = self._topology_section(hidden_html)

        self.assertIn("<svg", hidden_section)
        self.assertNotIn("<script", hidden_section)
        self.assertIn("confidence", hidden_section)
        self.assertIn("details.subnet_no", hidden_section)
        for hidden_value in (
            "&lt;prod-vpc&gt;",
            "private-server-name",
            "vpc-sensitive-id",
            "server-sensitive-id",
            "10.0.1.7",
            "203.0.113.7",
            "10.0.0.0/16",
            "KR-1",
        ):
            self.assertNotIn(hidden_value, hidden_section)

        visible_html = HtmlReportRenderer(
            topology_display_options={
                "show_resource_name": True,
                "show_resource_id": True,
                "show_private_ip": True,
                "show_public_ip": True,
                "show_network_cidr": True,
                "show_status": True,
                "show_zone": True,
                "show_platform": True,
            }
        ).render(report)
        visible_section = self._topology_section(visible_html)
        self.assertIn("&lt;prod-vpc&gt;", visible_section)
        self.assertIn("private-server-name", visible_section)
        self.assertIn("server-sensitive-id", visible_section)
        self.assertIn("10.0.1.7", visible_section)
        self.assertIn("203.0.113.7", visible_section)
        self.assertIn("10.0.0.0/16", visible_section)
        self.assertIn("KR-1", visible_section)

    def test_compound_renderer_nests_vpc_subnet_and_server(self):
        report = self._report_with_sensitive_topology()
        topology = report.display_infrastructure_topology
        renderer = HtmlReportRenderer()
        options = TopologyDisplayOptions()
        layout, width, height = renderer._topology_layout(
            topology["nodes"],
            topology["edges"],
            options,
        )

        vpc_box = layout["boxes"]["VPC:vpc-sensitive-id"]
        subnet_box = layout["boxes"]["SUBNET:subnet-sensitive-id"]
        server_box = layout["boxes"]["SERVER:server-sensitive-id"]
        self.assertTrue(self._box_contains(vpc_box, subnet_box))
        self.assertTrue(self._box_contains(subnet_box, server_box))
        self.assertGreater(width, 0)
        self.assertGreater(height, 0)
        self.assertEqual(
            {boundary["node_id"] for boundary in layout["boundaries"]},
            {"VPC:vpc-sensitive-id", "SUBNET:subnet-sensitive-id"},
        )
        self.assertEqual(len(layout["consumed_edges"]), 2)

        svg = renderer._topology_svg(
            topology["nodes"],
            topology["edges"],
            options,
        )
        self.assertIn("topology-boundary--vpc", svg)
        self.assertIn("topology-boundary--subnet", svg)
        self.assertEqual(svg.count('class="topology-node"'), 1)
        self.assertNotIn('class="topology-edge"', svg)

        section = self._topology_section(renderer.render(report))
        self.assertIn("중첩된 경계 상자로 표현합니다", section)
        self.assertIn("details.vpc_no", section)
        self.assertIn("details.subnet_no", section)

    def test_multi_subnet_resource_stays_at_vpc_level_with_edges(self):
        topology = InfrastructureTopologyBuilder().build([
            InfrastructureTopologyBuilderTests._resource(
                "VPC", "vpc-1", "vpc"
            ),
            InfrastructureTopologyBuilderTests._resource(
                "SUBNET",
                "subnet-1",
                "subnet-a",
                details={"vpc_no": "vpc-1"},
            ),
            InfrastructureTopologyBuilderTests._resource(
                "SUBNET",
                "subnet-2",
                "subnet-b",
                details={"vpc_no": "vpc-1"},
            ),
            InfrastructureTopologyBuilderTests._resource(
                "LOAD_BALANCER",
                "lb-1",
                "frontend",
                details={"subnet_nos": ["subnet-1", "subnet-2"]},
            ),
        ])
        renderer = HtmlReportRenderer()
        options = TopologyDisplayOptions()
        layout, _, _ = renderer._topology_layout(
            topology["nodes"],
            topology["edges"],
            options,
        )

        load_balancer_box = layout["boxes"]["LOAD_BALANCER:lb-1"]
        self.assertTrue(
            self._box_contains(layout["boxes"]["VPC:vpc-1"], load_balancer_box)
        )
        self.assertFalse(
            self._box_contains(
                layout["boxes"]["SUBNET:subnet-1"],
                load_balancer_box,
            )
        )
        self.assertFalse(
            self._box_contains(
                layout["boxes"]["SUBNET:subnet-2"],
                load_balancer_box,
            )
        )
        svg = renderer._topology_svg(
            topology["nodes"],
            topology["edges"],
            options,
        )
        self.assertEqual(svg.count('class="topology-edge"'), 2)

    def test_conflicting_vpc_membership_is_not_nested(self):
        topology = InfrastructureTopologyBuilder().build([
            InfrastructureTopologyBuilderTests._resource(
                "VPC", "vpc-1", "vpc-a"
            ),
            InfrastructureTopologyBuilderTests._resource(
                "VPC", "vpc-2", "vpc-b"
            ),
            InfrastructureTopologyBuilderTests._resource(
                "SUBNET",
                "subnet-1",
                "subnet-a",
                details={"vpc_no": "vpc-1"},
            ),
            InfrastructureTopologyBuilderTests._resource(
                "SUBNET",
                "subnet-2",
                "subnet-b",
                details={"vpc_no": "vpc-2"},
            ),
            InfrastructureTopologyBuilderTests._resource(
                "SERVER",
                "server-1",
                "ambiguous-server",
                details={
                    "explicit_relations": [
                        {
                            "type": "CONTAINS",
                            "target_category": "SUBNET",
                            "target_id": "subnet-1",
                            "source_field": "test.subnetA",
                        },
                        {
                            "type": "CONTAINS",
                            "target_category": "SUBNET",
                            "target_id": "subnet-2",
                            "source_field": "test.subnetB",
                        },
                    ]
                },
            ),
        ])
        renderer = HtmlReportRenderer()
        options = TopologyDisplayOptions()
        layout, _, _ = renderer._topology_layout(
            topology["nodes"],
            topology["edges"],
            options,
        )

        server_box = layout["boxes"]["SERVER:server-1"]
        self.assertFalse(
            self._box_contains(layout["boxes"]["VPC:vpc-1"], server_box)
        )
        self.assertFalse(
            self._box_contains(layout["boxes"]["VPC:vpc-2"], server_box)
        )
        server_edges = {
            renderer._topology_edge_key(edge)
            for edge in topology["edges"]
            if "SERVER:server-1" in renderer._topology_edge_key(edge)
        }
        self.assertTrue(server_edges)
        self.assertTrue(server_edges.isdisjoint(layout["consumed_edges"]))

    def test_group_by_vpc_false_preserves_linear_nodes_and_edges(self):
        report = self._report_with_sensitive_topology()
        topology = report.display_infrastructure_topology
        renderer = HtmlReportRenderer()
        options = TopologyDisplayOptions(group_by_vpc=False)
        layout, _, _ = renderer._topology_layout(
            topology["nodes"],
            topology["edges"],
            options,
        )
        svg = renderer._topology_svg(
            topology["nodes"],
            topology["edges"],
            options,
        )

        self.assertEqual(layout["boundaries"], [])
        self.assertEqual(layout["consumed_edges"], set())
        self.assertNotIn("topology-boundary--vpc", svg)
        self.assertEqual(svg.count('class="topology-node"'), 3)
        self.assertEqual(svg.count('class="topology-edge"'), 2)

    def test_edge_path_uses_actual_boundary_dimensions(self):
        path, label_x, label_y = HtmlReportRenderer._topology_edge_path(
            (0.0, 0.0, 800.0, 600.0),
            (900.0, 100.0, 230.0, 196.0),
        )

        self.assertTrue(path.startswith("M 800.0 300.0"))
        self.assertGreater(label_x, 800.0)
        self.assertGreater(label_y, 0.0)

    def test_compound_svg_is_deterministic_for_input_order(self):
        report = self._report_with_sensitive_topology()
        topology = report.display_infrastructure_topology
        renderer = HtmlReportRenderer()
        options = TopologyDisplayOptions()

        expected = renderer._topology_svg(
            topology["nodes"],
            topology["edges"],
            options,
        )
        reordered = renderer._topology_svg(
            list(reversed(topology["nodes"])),
            list(reversed(topology["edges"])),
            options,
        )

        self.assertEqual(reordered, expected)

    def test_renderer_can_disable_the_diagram(self):
        report = self._report_with_sensitive_topology()
        report.customer = {
            "report_options": {
                "diagram": {"enabled": False, "max_nodes": 80},
            }
        }
        html = HtmlReportRenderer().render(report)

        self.assertNotIn("<h2>클라우드 구성도</h2>", html)

    def _report_with_sensitive_topology(self):
        return ReportResult(
            period={
                "file_suffix": "topology",
                "start_dt": "2026-08-07 00:00:00",
                "end_dt": "2026-08-07 23:59:59",
            },
            collection_metadata={
                "infrastructure": {
                    "completed_at": "2026-08-07T16:30:00+09:00",
                    "source": "TEST_API",
                    "inventory_completeness": "COMPLETE_FOR_SELECTED_SCOPE",
                }
            },
            infrastructure=[
                {
                    **InfrastructureTopologyBuilderTests._resource(
                        "VPC",
                        "vpc-sensitive-id",
                        "<prod-vpc>",
                        details={"network_cidr": "10.0.0.0/16"},
                    ),
                    "private_ip": "10.0.0.1",
                },
                {
                    **InfrastructureTopologyBuilderTests._resource(
                        "SUBNET",
                        "subnet-sensitive-id",
                        "private-subnet",
                        details={"vpc_no": "vpc-sensitive-id"},
                    ),
                    "private_ip": "10.0.0.2",
                },
                {
                    **InfrastructureTopologyBuilderTests._resource(
                        "SERVER",
                        "server-sensitive-id",
                        "private-server-name",
                        details={"subnet_no": "subnet-sensitive-id"},
                    ),
                    "private_ip": "10.0.1.7",
                    "public_ip": "203.0.113.7",
                },
            ],
            servers=[],
            billing={"summary": {}, "network_usage_summary": []},
        )

    @staticmethod
    def _topology_section(html):
        return html.split("<h2>클라우드 구성도</h2>", 1)[1].split(
            "</section>",
            1,
        )[0]

    @staticmethod
    def _box_contains(outer, inner):
        outer_x, outer_y, outer_width, outer_height = outer
        inner_x, inner_y, inner_width, inner_height = inner
        return (
            outer_x <= inner_x
            and outer_y <= inner_y
            and outer_x + outer_width >= inner_x + inner_width
            and outer_y + outer_height >= inner_y + inner_height
        )


if __name__ == "__main__":
    unittest.main()

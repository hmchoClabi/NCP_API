import copy
import time
import unittest

from app.infrastructure_topology import TopologyDisplayOptions
from app.renderers.html_renderer import HtmlReportRenderer
from app.renderers.html_styles import HTML_REPORT_STYLES
from app.renderers.topology_edge_router import OrthogonalEdgeRouter


class TopologyRendererLayoutTests(unittest.TestCase):
    def setUp(self):
        self.renderer = HtmlReportRenderer()
        self.edge_router = OrthogonalEdgeRouter()
        self.options = TopologyDisplayOptions()

    def test_nat_gateways_straddle_their_verified_vpc_boundaries(self):
        nodes = [
            self._node("VPC", "vpc-a", "vpc-a"),
            self._node("SUBNET", "subnet-a", "subnet-a"),
            self._node("NAT_GATEWAY", "nat-a1", "nat-a1"),
            self._node("NAT_GATEWAY", "nat-a2", "nat-a2"),
            self._node("VPC", "vpc-b", "vpc-b"),
            self._node("NAT_GATEWAY", "nat-b1", "nat-b1"),
        ]
        edges = [
            self._edge("VPC:vpc-a", "SUBNET:subnet-a"),
            self._edge("SUBNET:subnet-a", "NAT_GATEWAY:nat-a1"),
            self._edge("SUBNET:subnet-a", "NAT_GATEWAY:nat-a2"),
            self._edge("VPC:vpc-b", "NAT_GATEWAY:nat-b1"),
        ]
        original_nodes = copy.deepcopy(nodes)
        original_edges = copy.deepcopy(edges)

        layout, width, _ = self.renderer._topology_layout(
            list(reversed(nodes)),
            list(reversed(edges)),
            self.options,
        )

        self.assertEqual(nodes, original_nodes)
        self.assertEqual(edges, original_edges)
        self.assertEqual(
            layout["vpc_boundary_node_ids"],
            {
                "NAT_GATEWAY:nat-a1",
                "NAT_GATEWAY:nat-a2",
                "NAT_GATEWAY:nat-b1",
            },
        )
        for nat_id, vpc_id in (
            ("NAT_GATEWAY:nat-a1", "VPC:vpc-a"),
            ("NAT_GATEWAY:nat-a2", "VPC:vpc-a"),
            ("NAT_GATEWAY:nat-b1", "VPC:vpc-b"),
        ):
            nat_box = layout["boxes"][nat_id]
            vpc_box = layout["boxes"][vpc_id]
            vpc_right = vpc_box[0] + vpc_box[2]
            self.assertLess(nat_box[0], vpc_right)
            self.assertGreater(nat_box[0] + nat_box[2], vpc_right)
            self.assertLessEqual(nat_box[0] + nat_box[2], width)

        self.assertFalse(
            self._boxes_overlap(
                layout["boxes"]["NAT_GATEWAY:nat-a1"],
                layout["boxes"]["NAT_GATEWAY:nat-a2"],
            )
        )
        self.assertFalse(
            self._boxes_overlap(
                layout["boxes"]["SUBNET:subnet-a"],
                layout["boxes"]["NAT_GATEWAY:nat-a1"],
            )
        )
        vpc_a = layout["boxes"]["VPC:vpc-a"]
        content_bottom = max(
            layout["boxes"][node_id][1]
            + layout["boxes"][node_id][3]
            for node_id in (
                "SUBNET:subnet-a",
                "NAT_GATEWAY:nat-a1",
                "NAT_GATEWAY:nat-a2",
            )
        )
        self.assertLessEqual(
            vpc_a[1] + vpc_a[3] - content_bottom,
            24,
        )

        svg = self.renderer._topology_svg(nodes, edges, self.options)
        self.assertEqual(svg.count('data-placement="vpc-boundary"'), 3)
        self.assertIn("topology-node--vpc-boundary", svg)

    def test_nat_with_conflicting_vpc_evidence_uses_external_fallback(self):
        nodes = [
            self._node("VPC", "vpc-a", "vpc-a"),
            self._node("VPC", "vpc-b", "vpc-b"),
            self._node("NAT_GATEWAY", "nat-conflict", "nat-conflict"),
        ]
        edges = [
            self._edge("VPC:vpc-a", "NAT_GATEWAY:nat-conflict"),
            self._edge("VPC:vpc-b", "NAT_GATEWAY:nat-conflict"),
        ]

        layout, _, _ = self.renderer._topology_layout(
            nodes,
            edges,
            self.options,
        )

        self.assertNotIn(
            "NAT_GATEWAY:nat-conflict",
            layout["vpc_boundary_node_ids"],
        )
        nat_box = layout["boxes"]["NAT_GATEWAY:nat-conflict"]
        self.assertFalse(self._box_contains(layout["boxes"]["VPC:vpc-a"], nat_box))
        self.assertFalse(self._box_contains(layout["boxes"]["VPC:vpc-b"], nat_box))
        self.assertTrue(
            {
                self.renderer._topology_edge_key(edge)
                for edge in edges
            }.isdisjoint(layout["consumed_edges"])
        )

    def test_server_card_shows_only_ip_and_aggregate_disk_summary(self):
        node = self._node("SERVER", "server-1", "server-1")
        node.update({
            "private_ips": ["10.0.0.10"],
            "metadata": {
                "public_ip": "203.0.113.10",
                "attached_disk_count": 3,
                "attached_disk_total_gb": 240.5,
                "attached_disks": [
                    {"name": "sensitive-volume-name", "size_gb": 100},
                ],
                "network_interfaces": [
                    {"name": "sensitive-nic-name"},
                ],
            },
        })

        lines = self.renderer._topology_node_lines(node, self.options)

        self.assertIn("Private IP 10.0.0.10", lines)
        self.assertIn("Public IP 203.0.113.10", lines)
        self.assertIn("디스크 3개 · 합계 240.5 GB", lines)
        self.assertNotIn("sensitive-volume-name", str(lines))
        self.assertNotIn("sensitive-nic-name", str(lines))

        hidden_lines = self.renderer._topology_node_lines(
            node,
            TopologyDisplayOptions(
                show_private_ip=False,
                show_public_ip=False,
            ),
        )
        self.assertNotIn("10.0.0.10", str(hidden_lines))
        self.assertNotIn("203.0.113.10", str(hidden_lines))
        self.assertIn("디스크 3개 · 합계 240.5 GB", hidden_lines)

    def test_server_card_does_not_treat_partial_disk_capacity_as_total(self):
        node = self._node("SERVER", "server-1", "server-1")
        node.update({
            "attached_disk_count": 2,
            "attached_disk_capacity_known_count": 1,
            "attached_disk_total_gb": None,
            "attached_disks": [
                {"name": "known", "size_gb": 100},
                {"name": "unknown", "size_gb": None},
            ],
        })

        lines = self.renderer._topology_node_lines(node, self.options)

        self.assertIn("디스크 2개 · 확인 용량 100 GB (1개 확인)", lines)
        self.assertNotIn("디스크 2개 · 합계 100 GB", lines)

    def test_explicit_zone_uses_compact_landscape_boundary_hierarchy(self):
        vpc = self._node("VPC", "vpc-a", "production")
        vpc["network_cidrs"] = ["10.0.0.0/16"]
        nodes = [vpc]
        edges = []
        for index in range(3):
            subnet = self._node(
                "SUBNET",
                f"subnet-{index}",
                f"application-{index}",
            )
            subnet.update({
                "zone": "KR-1",
                "network_cidrs": [f"10.0.{index}.0/24"],
            })
            server = self._node(
                "SERVER",
                f"server-{index}",
                f"application-{index}",
            )
            server.update({
                "private_ips": [f"10.0.{index}.10"],
                "status": "RUN",
                "zone": "KR-1",
                "platform": "VPC",
            })
            nodes.extend((subnet, server))
            edges.extend((
                self._edge("VPC:vpc-a", f"SUBNET:subnet-{index}"),
                self._edge(
                    f"SUBNET:subnet-{index}",
                    f"SERVER:server-{index}",
                ),
            ))

        layout, width, height = self.renderer._topology_layout(
            nodes,
            edges,
            self.options,
        )

        zone_boundaries = [
            boundary
            for boundary in layout["boundaries"]
            if boundary.get("category") == "zone"
        ]
        self.assertEqual(len(zone_boundaries), 1)
        zone_box = zone_boundaries[0]["box"]
        for index in range(3):
            self.assertTrue(
                self._box_contains(
                    zone_box,
                    layout["boxes"][f"SUBNET:subnet-{index}"],
                )
            )
        self.assertGreater(width, height)
        self.assertEqual(self.renderer.TOPOLOGY_NODE_WIDTH, 184)
        self.assertEqual(self.renderer.TOPOLOGY_NODE_HEIGHT, 126)

        svg = self.renderer._topology_svg(nodes, edges, self.options)
        self.assertIn("topology-vpc-title-tab", svg)
        self.assertIn("topology-zone-title-tab", svg)
        self.assertIn("topology-subnet-title-tab", svg)
        self.assertIn("topology-boundary--zone", svg)
        self.assertIn("topology-boundary--subnet", svg)
        self.assertIn("topology-node-badge", svg)
        self.assertNotIn("topology-boundary--public", svg)
        self.assertNotIn("topology-boundary--private", svg)
        edge_path, _, _ = self.renderer._topology_edge_path(
            (0.0, 0.0, 184.0, 126.0),
            (280.0, 80.0, 184.0, 126.0),
        )
        self.assertIn(" H ", edge_path)
        self.assertIn(" V ", edge_path)
        self.assertNotIn(" C ", edge_path)

    def test_zone_grouping_and_label_follow_show_zone_option(self):
        subnet = self._node("SUBNET", "subnet-a", "application")
        subnet["zone"] = "KR-1"
        nodes = [
            self._node("VPC", "vpc-a", "production"),
            subnet,
            self._node("SERVER", "server-a", "application"),
        ]
        edges = [
            self._edge("VPC:vpc-a", "SUBNET:subnet-a"),
            self._edge("SUBNET:subnet-a", "SERVER:server-a"),
        ]
        options = TopologyDisplayOptions(show_zone=False)

        layout, _, _ = self.renderer._topology_layout(nodes, edges, options)
        svg = self.renderer._topology_svg(nodes, edges, options)

        self.assertFalse(any(
            boundary.get("category") == "zone"
            for boundary in layout["boundaries"]
        ))
        self.assertNotIn("Zone KR-1", svg)

    def test_relationship_edge_avoids_unrelated_subnets_and_resources(self):
        vpc = self._node("VPC", "vpc-a", "production")
        load_balancer = self._node("LOAD_BALANCER", "lb-a", "public-lb")
        nodes = [vpc, load_balancer]
        edges = [self._edge("VPC:vpc-a", "LOAD_BALANCER:lb-a")]
        for index in range(3):
            subnet = self._node(
                "SUBNET",
                f"subnet-{index}",
                f"application-{index}",
            )
            subnet["zone"] = "KR-1"
            server = self._node(
                "SERVER",
                f"server-{index}",
                f"application-{index}",
            )
            nodes.extend((subnet, server))
            edges.extend((
                self._edge("VPC:vpc-a", f"SUBNET:subnet-{index}"),
                self._edge(
                    f"SUBNET:subnet-{index}",
                    f"SERVER:server-{index}",
                ),
            ))
        edges.append({
            **self._edge("LOAD_BALANCER:lb-a", "SERVER:server-2"),
            "relationship": "TARGETS",
        })

        layout, width, height = self.renderer._topology_layout(
            nodes,
            edges,
            self.options,
        )
        helper = self.renderer._topology_helper()
        path, _, _, points = helper._topology_routed_edge_path(
            source_id="LOAD_BALANCER:lb-a",
            target_id="SERVER:server-2",
            boxes=layout["boxes"],
            boundaries=layout["boundaries"],
            options=self.options,
            width=width,
            height=height,
        )

        self.assertTrue(points, "장애물 회피 경로가 fallback 없이 계산돼야 합니다.")
        self.assertIn(" H ", path)
        self.assertIn(" V ", path)
        forbidden_ids = (
            "SUBNET:subnet-0",
            "SUBNET:subnet-1",
            "SERVER:server-0",
            "SERVER:server-1",
        )
        for node_id in forbidden_ids:
            obstacle = self.edge_router.inflate_box(
                layout["boxes"][node_id],
                self.edge_router.EDGE_CLEARANCE,
            )
            for start, end in self.edge_router.path_segments(points):
                self.assertTrue(
                    self.edge_router.segment_clear(start, end, [obstacle]),
                    f"관계선이 무관한 {node_id} 영역을 침범했습니다.",
                )

    def test_routing_is_deterministic_and_reserves_compound_gutters(self):
        nodes = [
            self._node("VPC", "vpc-a", "production"),
            self._node("SUBNET", "subnet-a", "application-a"),
            self._node("SUBNET", "subnet-b", "application-b"),
            self._node("SERVER", "server-a", "application-a"),
            self._node("SERVER", "server-b", "application-b"),
        ]
        for node in nodes:
            if node["category"] == "SUBNET":
                node["zone"] = "KR-1"
        edges = [
            self._edge("VPC:vpc-a", "SUBNET:subnet-a"),
            self._edge("VPC:vpc-a", "SUBNET:subnet-b"),
            self._edge("SUBNET:subnet-a", "SERVER:server-a"),
            self._edge("SUBNET:subnet-b", "SERVER:server-b"),
            {
                **self._edge("SERVER:server-a", "SERVER:server-b"),
                "relationship": "TARGETS",
            },
        ]

        first = self.renderer._topology_svg(nodes, edges, self.options)
        second = self.renderer._topology_svg(
            list(reversed(nodes)),
            list(reversed(edges)),
            self.options,
        )
        layout, _, _ = self.renderer._topology_layout(
            nodes,
            edges,
            self.options,
        )
        subnet_a = layout["boxes"]["SUBNET:subnet-a"]
        subnet_b = layout["boxes"]["SUBNET:subnet-b"]

        self.assertEqual(first, second)
        self.assertGreaterEqual(
            subnet_b[0] - (subnet_a[0] + subnet_a[2]),
            24,
        )

    def test_dense_inventory_edge_routing_stays_bounded(self):
        boxes = {
            "SERVER:source": (20.0, 680.0, 40.0, 40.0),
            "SERVER:target": (4940.0, 680.0, 40.0, 40.0),
        }
        for index in range(78):
            boxes[f"SERVER:blocker-{index}"] = (
                150.0 + index * 58.0,
                70.0 + index * 13.0,
                34.0,
                34.0,
            )

        started_at = time.perf_counter()
        path, _, _, points = self.edge_router.route(
            source_id="SERVER:source",
            target_id="SERVER:target",
            boxes=boxes,
            boundaries=[],
            width=5000.0,
            height=1400.0,
        )
        elapsed = time.perf_counter() - started_at

        self.assertTrue(path)
        self.assertTrue(points)
        self.assertLess(elapsed, 2.0)

    def test_blocked_route_is_omitted_instead_of_using_unsafe_fallback(self):
        boxes = {
            "SERVER:source": (20.0, 90.0, 20.0, 20.0),
            "SERVER:blocker": (80.0, -20.0, 40.0, 240.0),
            "SERVER:target": (160.0, 90.0, 20.0, 20.0),
        }

        path, label_x, label_y, points = self.edge_router.route(
            source_id="SERVER:source",
            target_id="SERVER:target",
            boxes=boxes,
            boundaries=[],
            width=200.0,
            height=200.0,
        )

        self.assertEqual(path, "")
        self.assertIsNone(label_x)
        self.assertIsNone(label_y)
        self.assertEqual(points, [])

    def test_small_svg_is_not_forced_to_fill_the_report_width(self):
        topology_rule = HTML_REPORT_STYLES.split(".topology-svg {", 1)[1].split(
            "}",
            1,
        )[0]

        self.assertIn("min-width: 0", topology_rule)
        self.assertNotIn("min-width: 100%", topology_rule)

    def test_resource_icons_do_not_use_dashboard_card_chrome(self):
        node_rule = HTML_REPORT_STYLES.split(".topology-node rect {", 1)[1].split(
            "}",
            1,
        )[0]

        self.assertIn("fill: transparent", node_rule)
        self.assertIn("stroke: none", node_rule)
        self.assertIn("filter: none", node_rule)
        self.assertNotIn("drop-shadow", node_rule)

    @staticmethod
    def _node(category, resource_id, name):
        return {
            "node_id": f"{category}:{resource_id}",
            "category": category,
            "category_label": category,
            "resource_id": resource_id,
            "name": name,
            "private_ips": [],
            "public_ips": [],
            "network_cidrs": [],
            "kind": "representative",
            "source": "TEST_API",
            "confidence": "VERIFIED",
            "resolution": "RESOLVED",
        }

    @staticmethod
    def _edge(source_id, target_id):
        return {
            "source_node_id": source_id,
            "target_node_id": target_id,
            "relationship": "CONTAINS",
            "source": "details.verified_parent_id",
            "confidence": "VERIFIED",
        }

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

    @staticmethod
    def _boxes_overlap(first, second):
        first_x, first_y, first_width, first_height = first
        second_x, second_y, second_width, second_height = second
        return not (
            first_x + first_width <= second_x
            or second_x + second_width <= first_x
            or first_y + first_height <= second_y
            or second_y + second_height <= first_y
        )


if __name__ == "__main__":
    unittest.main()

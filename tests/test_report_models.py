import unittest

from app.infrastructure_topology import (
    TOPOLOGY_PRESENTATION_POLICY_MODE,
    TOPOLOGY_PRESENTATION_POLICY_VERSION,
)
from app.report_models import ReportResult


class ReportResultSnapshotTests(unittest.TestCase):
    def test_snapshot_round_trip_preserves_raw_metric_series(self):
        report = ReportResult(
            period={"file_suffix": "20260802", "period_type": "day"},
            infrastructure=[{
                "category": "LOAD_BALANCER",
                "resource_id": "lb-1",
                "resource_name": "frontend",
            }],
            infrastructure_metrics=[{
                "category": "LOAD_BALANCER",
                "metric": "connections_per_second",
                "series": [{"points": [[1, 2.0]]}],
            }],
            server_metrics=[{
                "server_name": "web-1",
                "raw_metrics": {"CPU/used_rto": {"avg": [{"values": [1, 2]}]}},
            }],
        )
        snapshot = report.to_dict()
        snapshot["server_metrics"] = report.server_metrics

        restored = ReportResult.from_dict(snapshot)

        self.assertEqual(restored.server_metrics, report.server_metrics)
        self.assertEqual(restored.infrastructure, report.infrastructure)
        self.assertEqual(
            restored.infrastructure_metrics,
            report.infrastructure_metrics,
        )
        self.assertEqual(snapshot["schema_version"], "1.3")

    def test_legacy_snapshot_uses_servers_as_infrastructure_fallback(self):
        restored = ReportResult.from_dict({
            "period": {"file_suffix": "legacy"},
            "servers": [{
                "server_id": "server-1",
                "server_name": "web-1",
                "status": "RUN",
            }],
        })

        self.assertEqual(len(restored.display_infrastructure), 1)
        self.assertEqual(
            restored.display_infrastructure[0]["category"],
            "SERVER",
        )
        self.assertFalse(
            restored.selected_report_options.section_enabled(
                "infrastructure_diagram"
            )
        )
        self.assertEqual(restored.display_infrastructure_topology, {})

    def test_stored_topology_outside_period_is_not_rendered(self):
        report = ReportResult(
            period={
                "file_suffix": "202607",
                "start_dt": "2026-07-01 00:00:00",
                "end_dt": "2026-07-31 23:59:59",
            },
            infrastructure_topology={
                "nodes": [{"node_id": "SERVER:current"}],
                "edges": [],
                "summary": {
                    "collected_at": "2026-08-07T12:00:00+09:00",
                    "confidence": "VERIFIED",
                    "snapshot_source": "LIVE_API_COLLECTION",
                },
            },
        )

        topology = report.display_infrastructure_topology

        self.assertEqual(topology["nodes"], [])
        self.assertEqual(topology["summary"]["confidence"], "UNAVAILABLE")
        self.assertEqual(
            topology["warnings"][0]["code"],
            "PERIOD_SNAPSHOT_UNAVAILABLE",
        )

    def test_legacy_placeholder_rebuilds_labelled_current_state_topology(self):
        collected_at = "2026-08-09T22:19:17+09:00"
        report = ReportResult(
            period={
                "file_suffix": "20260808",
                "start_dt": "2026-08-08T00:00:00+09:00",
                "end_dt": "2026-08-09T00:00:00+09:00",
                "end_exclusive": True,
            },
            report_options={
                "sections": ["infrastructure_diagram"],
                "resource_categories": ["VPC", "SUBNET"],
                "diagram": {"enabled": True},
            },
            infrastructure=[
                {
                    "category": "VPC",
                    "resource_id": "vpc-1",
                    "resource_name": "main-vpc",
                    "details": {"vpc_no": "vpc-1"},
                },
                {
                    "category": "SUBNET",
                    "resource_id": "subnet-1",
                    "resource_name": "app-subnet",
                    "details": {"vpc_no": "vpc-1"},
                },
            ],
            collection_metadata={
                "infrastructure": {
                    "source": "CURRENT_API_COLLECTION",
                    "time_basis": "CURRENT_STATE_FILTERED_BY_CREATE_TIME",
                    "completed_at": collected_at,
                    "reference_at": collected_at,
                    "inventory_completeness": "PARTIAL",
                    "collection_issue_count": 1,
                }
            },
            infrastructure_topology={
                "nodes": [],
                "edges": [],
                "warnings": [],
                "summary": {
                    "collected_at": collected_at,
                    "confidence": "UNAVAILABLE",
                    "time_basis": "REPORT_PERIOD",
                    "snapshot_source": "CURRENT_API_COLLECTION",
                },
            },
            generated_at="2026-08-09T22:19:40+09:00",
        )

        topology = report.display_infrastructure_topology

        self.assertEqual(topology["summary"]["confidence"], "PARTIAL")
        self.assertEqual(
            topology["summary"]["time_basis"],
            "CURRENT_STATE_FILTERED_BY_CREATE_TIME",
        )
        self.assertEqual(len(topology["nodes"]), 1)
        self.assertEqual(len(topology["edges"]), 0)
        self.assertEqual(
            topology["summary"]["presentation_policy"][
                "excluded_empty_subnet_count"
            ],
            1,
        )
        self.assertEqual(
            topology["warnings"][0]["code"],
            "CURRENT_STATE_TOPOLOGY_FALLBACK",
        )

    def test_current_state_topology_with_mismatched_timestamp_is_rejected(self):
        report = ReportResult(
            period={
                "start_dt": "2026-08-08T00:00:00+09:00",
                "end_dt": "2026-08-09T00:00:00+09:00",
                "end_exclusive": True,
            },
            report_options={
                "sections": ["infrastructure_diagram"],
                "resource_categories": ["VPC"],
                "diagram": {"enabled": True},
            },
            collection_metadata={
                "infrastructure": {
                    "source": "CURRENT_API_COLLECTION",
                    "time_basis": "CURRENT_STATE_FILTERED_BY_CREATE_TIME",
                    "completed_at": "2026-08-09T22:19:17+09:00",
                }
            },
            infrastructure_topology={
                "nodes": [{"node_id": "VPC:vpc-1"}],
                "edges": [],
                "summary": {
                    "collected_at": "2026-08-09T22:20:17+09:00",
                    "confidence": "PARTIAL",
                    "time_basis": "CURRENT_STATE_FILTERED_BY_CREATE_TIME",
                    "snapshot_source": "CURRENT_API_COLLECTION",
                },
            },
            generated_at="2026-08-09T22:20:30+09:00",
        )

        topology = report.display_infrastructure_topology

        self.assertEqual(topology["nodes"], [])
        self.assertEqual(topology["summary"]["confidence"], "UNAVAILABLE")

    def test_public_and_persistence_inventory_are_separated(self):
        report = ReportResult(
            period={"file_suffix": "separated"},
            report_options={
                "sections": ["infrastructure_inventory", "monitoring"],
                "resource_categories": ["SERVER"],
                "monitoring_categories": ["CLOUD_DB"],
                "diagram": {"enabled": False},
            },
            infrastructure=[
                {"category": "SERVER", "resource_id": "server-1"},
                {"category": "CLOUD_DB", "resource_id": "cdb-1"},
            ],
        )

        public_snapshot = report.to_dict()
        persistence_snapshot = report.to_persistence_dict()

        self.assertEqual(
            [item["category"] for item in public_snapshot["infrastructure"]],
            ["SERVER"],
        )
        self.assertEqual(
            [
                item["category"]
                for item in persistence_snapshot["infrastructure"]
            ],
            ["SERVER", "CLOUD_DB"],
        )

    def test_target_groups_are_supporting_persistence_not_inventory_rows(self):
        report = ReportResult(
            period={"file_suffix": "target-groups"},
            report_options={
                "sections": ["infrastructure_inventory"],
                "resource_categories": ["LOAD_BALANCER"],
                "monitoring_categories": ["LOAD_BALANCER"],
                "diagram": {"enabled": False},
            },
            infrastructure=[
                {"category": "LOAD_BALANCER", "resource_id": "lb-1"},
                {
                    "category": "TARGET_GROUP",
                    "resource_id": "tg-1",
                    "details": {"ready_target_count": 2},
                },
            ],
        )

        public_snapshot = report.to_dict()
        persistence_snapshot = report.to_persistence_dict()

        self.assertEqual(
            [item["category"] for item in public_snapshot["infrastructure"]],
            ["LOAD_BALANCER"],
        )
        self.assertEqual(
            [
                item["category"]
                for item in persistence_snapshot["infrastructure"]
            ],
            ["LOAD_BALANCER", "TARGET_GROUP"],
        )
        self.assertEqual(
            report.display_load_balancer_target_groups[0]["resource_id"],
            "tg-1",
        )

    def test_public_json_redacts_hidden_topology_and_internal_customer_fields(self):
        report = ReportResult(
            period={"file_suffix": "redacted"},
            customer={
                "id": "customer-1",
                "name": "고객 1",
                "api_type": "public",
                "region": "KR",
                "credential_ref": "encrypted-db://credential-secret",
                "cloud_account_id": "internal-account-uuid",
            },
            report_options={
                "sections": ["infrastructure_diagram"],
                "resource_categories": ["SERVER"],
                "monitoring_categories": [],
                "diagram": {
                    "enabled": True,
                    "show_resource_name": False,
                    "show_resource_id": False,
                    "show_private_ip": False,
                    "show_public_ip": False,
                    "show_network_cidr": False,
                },
            },
            servers=[{
                "server_id": "server-secret",
                "server_name": "server-name-secret",
                "private_ip": "10.0.0.10",
            }],
            infrastructure=[{
                "category": "SERVER",
                "resource_id": "server-secret",
                "resource_name": "server-name-secret",
                "details": {"private_ip": "10.0.0.10"},
            }],
            infrastructure_topology={
                "nodes": [{
                    "node_id": "SERVER:server-secret",
                    "category": "SERVER",
                    "resource_id": "server-secret",
                    "name": "server-name-secret",
                    "private_ips": ["10.0.0.10"],
                    "public_ips": ["203.0.113.10"],
                    "network_cidrs": ["10.0.0.0/24"],
                    "network_interface_count": 1,
                    "network_interfaces": [{
                        "resource_id": "nic-secret",
                        "private_ips": ["10.0.0.11"],
                    }],
                    "attached_disk_count": 1,
                    "attached_disk_total_gb": 100,
                    "attached_disks": [{
                        "resource_id": "disk-secret",
                        "name": "disk-name-secret",
                        "size_gb": 100,
                    }],
                    "public_ip_resource_ids": ["public-ip-secret"],
                    "unexpected_internal_field": "topology-secret",
                }],
                "edges": [],
                "unmapped_node_ids": ["SERVER:server-secret"],
                "unresolved_node_ids": [],
                "summary": {"confidence": "UNMAPPED"},
            },
        )

        public_snapshot = report.to_dict()
        persistence_snapshot = report.to_persistence_dict()
        public_text = str(public_snapshot)

        self.assertEqual(public_snapshot["servers"], [])
        self.assertEqual(public_snapshot["infrastructure"], [])
        self.assertNotIn("credential-secret", public_text)
        self.assertNotIn("internal-account-uuid", public_text)
        self.assertNotIn("server-secret", public_text)
        self.assertNotIn("server-name-secret", public_text)
        self.assertNotIn("10.0.0.10", public_text)
        self.assertNotIn("203.0.113.10", public_text)
        self.assertNotIn("10.0.0.0/24", public_text)
        self.assertNotIn("10.0.0.11", public_text)
        self.assertNotIn("nic-secret", public_text)
        self.assertNotIn("disk-secret", public_text)
        self.assertNotIn("disk-name-secret", public_text)
        self.assertNotIn("public-ip-secret", public_text)
        self.assertNotIn("topology-secret", public_text)
        self.assertEqual(
            public_snapshot["infrastructure_topology"]["nodes"][0][
                "node_id"
            ],
            "node-001",
        )
        self.assertEqual(
            public_snapshot["infrastructure_topology"]["nodes"][0][
                "attached_disk_total_gb"
            ],
            100,
        )
        public_summary = public_snapshot["infrastructure_topology"]["summary"]
        self.assertEqual(
            public_summary["presentation_policy_version"],
            TOPOLOGY_PRESENTATION_POLICY_VERSION,
        )
        self.assertEqual(
            public_summary["presentation_policy_mode"],
            TOPOLOGY_PRESENTATION_POLICY_MODE,
        )
        self.assertEqual(
            persistence_snapshot["infrastructure_topology"]["nodes"][0][
                "resource_id"
            ],
            "server-secret",
        )

    def test_snapshot_excludes_non_infrastructure_and_unsupported_metrics(self):
        report = ReportResult(
            period={"file_suffix": "filtered"},
            servers=[{"server_id": "server-1", "server_name": "web-1"}],
            infrastructure=[
                {
                    "category": "LOAD_BALANCER",
                    "resource_id": "lb-1",
                },
                {
                    "category": "ALARM",
                    "resource_id": "alarm-1",
                },
            ],
            infrastructure_metrics=[
                {"category": "CLOUD_DB", "metric": "cpu_total"},
                {"category": "NAS", "metric": "volume_used_ratio"},
                {"category": "SERVER", "metric": "used_rto"},
            ],
        )

        snapshot = report.to_dict()

        self.assertEqual(
            [item["resource_id"] for item in snapshot["infrastructure"]],
            ["lb-1"],
        )
        self.assertEqual(
            [item["category"] for item in snapshot["infrastructure_metrics"]],
            ["CLOUD_DB", "NAS"],
        )
        self.assertNotIn("alarm-1", str(snapshot))

    def test_invalid_snapshot_is_rejected(self):
        with self.assertRaises(ValueError):
            ReportResult.from_dict({"servers": []})


if __name__ == "__main__":
    unittest.main()

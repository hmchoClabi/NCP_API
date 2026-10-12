import unittest

from app.report_models import ReportResult


class ReportResultSnapshotTests(unittest.TestCase):
    def test_snapshot_round_trip_preserves_raw_metric_series(self):
        report = ReportResult(
            period={"file_suffix": "20260802", "period_type": "day"},
            infrastructure_snapshot={
                "servers": [{"server_id": "observed-server"}],
                "infrastructure": [
                    {
                        "category": "SERVER",
                        "resource_id": "observed-server",
                    }
                ],
                "metadata": {"source": "LIVE_API_COLLECTION"},
            },
            infrastructure=[
                {
                    "category": "LOAD_BALANCER",
                    "resource_id": "lb-1",
                    "resource_name": "frontend",
                }
            ],
            infrastructure_metrics=[
                {
                    "category": "LOAD_BALANCER",
                    "metric": "connections_per_second",
                    "series": [{"points": [[1, 2.0]]}],
                }
            ],
            server_metrics=[
                {
                    "server_name": "web-1",
                    "raw_metrics": {"CPU/used_rto": {"avg": [{"values": [1, 2]}]}},
                }
            ],
        )
        snapshot = report.to_persistence_dict()
        snapshot["server_metrics"] = report.server_metrics

        restored = ReportResult.from_dict(snapshot)

        self.assertEqual(restored.server_metrics, report.server_metrics)
        self.assertEqual(restored.infrastructure, report.infrastructure)
        self.assertEqual(
            restored.infrastructure_metrics,
            report.infrastructure_metrics,
        )
        self.assertEqual(
            restored.infrastructure_snapshot,
            report.infrastructure_snapshot,
        )
        self.assertNotIn("infrastructure_snapshot", report.to_dict())
        self.assertEqual(snapshot["schema_version"], "1.5")

    def test_legacy_snapshot_uses_servers_as_infrastructure_fallback(self):
        restored = ReportResult.from_dict(
            {
                "period": {"file_suffix": "legacy"},
                "servers": [
                    {
                        "server_id": "server-1",
                        "server_name": "web-1",
                        "status": "RUN",
                    }
                ],
            }
        )

        self.assertEqual(len(restored.display_infrastructure), 1)
        self.assertEqual(
            restored.display_infrastructure[0]["category"],
            "SERVER",
        )
        self.assertTrue(
            restored.selected_report_options.section_enabled("infrastructure_inventory")
        )

    def test_public_and_persistence_inventory_are_separated(self):
        report = ReportResult(
            period={"file_suffix": "separated"},
            report_options={
                "sections": ["infrastructure_inventory", "monitoring"],
                "resource_categories": ["SERVER"],
                "monitoring_categories": ["CLOUD_DB"],
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
            [item["category"] for item in persistence_snapshot["infrastructure"]],
            ["SERVER", "CLOUD_DB"],
        )

    def test_target_groups_are_supporting_persistence_not_inventory_rows(self):
        report = ReportResult(
            period={"file_suffix": "target-groups"},
            report_options={
                "sections": ["infrastructure_inventory"],
                "resource_categories": ["LOAD_BALANCER"],
                "monitoring_categories": ["LOAD_BALANCER"],
            },
            infrastructure=[
                {
                    "category": "LOAD_BALANCER",
                    "resource_id": "lb-1",
                    "details": {
                        "target_group_count": 1,
                        "registered_target_count": 2,
                        "ready_target_count": 2,
                        "unready_target_count": 0,
                        "unused_target_count": 0,
                        "unknown_target_count": 0,
                        "target_health_snapshot_available": True,
                    },
                },
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
            [item["category"] for item in persistence_snapshot["infrastructure"]],
            ["LOAD_BALANCER", "TARGET_GROUP"],
        )
        self.assertEqual(
            public_snapshot["infrastructure"][0]["details"].get("ready_target_count"),
            2,
        )

    def test_public_json_exposes_only_safe_inventory_fields(self):
        report = ReportResult(
            period={"file_suffix": "redacted"},
            customer={
                "id": "customer-1",
                "name": "Customer One",
                "api_type": "public",
                "region": "KR",
                "credential_ref": "encrypted-db://credential-secret",
                "cloud_account_id": "internal-account-uuid",
            },
            report_options={
                "sections": ["infrastructure_inventory"],
                "resource_categories": ["SERVER"],
                "monitoring_categories": [],
            },
            servers=[
                {
                    "server_id": "server-secret",
                    "server_name": "web-1",
                    "private_ip": "10.0.0.10",
                    "status": "RUN",
                    "unexpected_internal_field": "server-internal-secret",
                }
            ],
            infrastructure=[
                {
                    "category": "SERVER",
                    "resource_id": "resource-secret",
                    "resource_name": "web-1",
                    "status": "RUN",
                    "details": {
                        "private_ip": "10.0.0.10",
                        "network_cidr": "10.0.0.0/24",
                        "network_interfaces": [{"resource_id": "nic-secret"}],
                        "size_gb": 100,
                        "unexpected_internal_field": "inventory-internal-secret",
                    },
                }
            ],
        )

        public_snapshot = report.to_dict()
        persistence_snapshot = report.to_persistence_dict()
        public_text = str(public_snapshot)

        self.assertEqual(
            public_snapshot["servers"],
            [{"server_name": "web-1", "status": "RUN"}],
        )
        self.assertEqual(
            public_snapshot["infrastructure"],
            [
                {
                    "category": "SERVER",
                    "resource_name": "web-1",
                    "status": "RUN",
                    "details": {"size_gb": 100},
                }
            ],
        )
        for secret in (
            "credential-secret",
            "internal-account-uuid",
            "server-secret",
            "resource-secret",
            "10.0.0.10",
            "10.0.0.0/24",
            "nic-secret",
            "server-internal-secret",
            "inventory-internal-secret",
        ):
            self.assertNotIn(secret, public_text)
        self.assertEqual(
            persistence_snapshot["infrastructure"][0]["resource_id"],
            "resource-secret",
        )

    def test_snapshot_excludes_non_infrastructure_and_unsupported_metrics(self):
        report = ReportResult(
            period={"file_suffix": "filtered"},
            servers=[{"server_id": "server-1", "server_name": "web-1"}],
            infrastructure=[
                {
                    "category": "LOAD_BALANCER",
                    "resource_id": "lb-1",
                    "resource_name": "frontend",
                },
                {
                    "category": "ALARM",
                    "resource_id": "alarm-1",
                    "resource_name": "internal-alarm",
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
            [item["category"] for item in snapshot["infrastructure"]],
            ["LOAD_BALANCER"],
        )
        self.assertNotIn("resource_id", snapshot["infrastructure"][0])
        self.assertEqual(
            [item["category"] for item in snapshot["infrastructure_metrics"]],
            ["CLOUD_DB", "NAS"],
        )
        self.assertNotIn("internal-alarm", str(snapshot))

    def test_invalid_snapshot_is_rejected(self):
        with self.assertRaises(ValueError):
            ReportResult.from_dict({"servers": []})


if __name__ == "__main__":
    unittest.main()

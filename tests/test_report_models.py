import unittest

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
        self.assertEqual(snapshot["schema_version"], "1.2")

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
            ["CLOUD_DB"],
        )
        self.assertNotIn("alarm-1", str(snapshot))

    def test_invalid_snapshot_is_rejected(self):
        with self.assertRaises(ValueError):
            ReportResult.from_dict({"servers": []})


if __name__ == "__main__":
    unittest.main()

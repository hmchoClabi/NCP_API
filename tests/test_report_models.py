import unittest

from app.report_models import ReportResult


class ReportResultSnapshotTests(unittest.TestCase):
    def test_snapshot_round_trip_preserves_raw_metric_series(self):
        report = ReportResult(
            period={"file_suffix": "20260802", "period_type": "day"},
            server_metrics=[{
                "server_name": "web-1",
                "raw_metrics": {"CPU/used_rto": {"avg": [{"values": [1, 2]}]}},
            }],
        )
        snapshot = report.to_dict()
        snapshot["server_metrics"] = report.server_metrics

        restored = ReportResult.from_dict(snapshot)

        self.assertEqual(restored.server_metrics, report.server_metrics)

    def test_invalid_snapshot_is_rejected(self):
        with self.assertRaises(ValueError):
            ReportResult.from_dict({"servers": []})


if __name__ == "__main__":
    unittest.main()

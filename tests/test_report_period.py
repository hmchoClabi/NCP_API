import unittest
from datetime import datetime, timedelta, timezone

from app.report_period import (
    build_snapshot_eligibility_window,
    normalize_period_bounds,
    snapshot_window_metadata,
)


class ReportPeriodTest(unittest.TestCase):
    def test_inclusive_end_is_normalized_to_exclusive_boundary(self):
        start = datetime(2026, 8, 1, tzinfo=timezone.utc)
        inclusive_end = datetime(2026, 8, 1, 23, 59, 59, tzinfo=timezone.utc)

        normalized = normalize_period_bounds(
            start,
            inclusive_end,
            end_exclusive=False,
        )

        self.assertEqual(
            normalized,
            (start, inclusive_end + timedelta(seconds=1)),
        )

    def test_exclusive_end_is_not_adjusted(self):
        start = datetime(2026, 8, 1, tzinfo=timezone.utc)
        exclusive_end = datetime(2026, 8, 2, tzinfo=timezone.utc)

        normalized = normalize_period_bounds(
            start,
            exclusive_end,
            end_exclusive=True,
        )

        self.assertEqual(normalized, (start, exclusive_end))

    def test_invalid_period_is_rejected(self):
        boundary = datetime(2026, 8, 1, tzinfo=timezone.utc)

        with self.assertRaisesRegex(ValueError, "Report period is invalid"):
            normalize_period_bounds(
                boundary,
                boundary,
                end_exclusive=True,
            )

    def test_snapshot_window_rejects_reference_before_period(self):
        start = datetime(2026, 8, 1, tzinfo=timezone.utc)
        end = datetime(2026, 8, 2, tzinfo=timezone.utc)

        self.assertIsNone(
            build_snapshot_eligibility_window(
                start,
                end,
                start - timedelta(microseconds=1),
            )
        )

    def test_snapshot_window_clamps_reference_to_period_end(self):
        start = datetime(2026, 8, 1, tzinfo=timezone.utc)
        end = datetime(2026, 8, 2, tzinfo=timezone.utc)

        window = build_snapshot_eligibility_window(
            start,
            end,
            end + timedelta(days=1),
        )

        self.assertIsNotNone(window)
        self.assertEqual(window["eligible_start"], start)
        self.assertEqual(window["eligible_end"], end)
        self.assertEqual(
            window["reference_at"],
            end - timedelta(microseconds=1),
        )

    def test_snapshot_metadata_includes_non_negative_age(self):
        start = datetime(2026, 8, 1, tzinfo=timezone.utc)
        end = datetime(2026, 8, 2, tzinfo=timezone.utc)
        reference = start + timedelta(hours=6)
        observed = start + timedelta(hours=5, minutes=59)
        window = build_snapshot_eligibility_window(start, end, reference)

        metadata = snapshot_window_metadata(window, observed)

        self.assertEqual(metadata["snapshot_age_seconds"], 60)
        self.assertEqual(metadata["reference_at"], reference.isoformat())


if __name__ == "__main__":
    unittest.main()

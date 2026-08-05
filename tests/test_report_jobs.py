import unittest
from datetime import datetime, timezone

from webapp.jobs import ReportJobRepository


class ReportJobTests(unittest.TestCase):
    def test_daily_target_is_normalized(self):
        self.assertEqual(
            ReportJobRepository._validate_target("daily", "2026-08-02"),
            ("DAILY", "2026-08-02", "2026-08-02", None, None),
        )

    def test_monthly_target_rejects_invalid_month(self):
        with self.assertRaises(ValueError):
            ReportJobRepository._validate_target("MONTHLY", "2026-13")

    def test_next_daily_run_uses_seoul_clock(self):
        now = datetime(2026, 8, 3, 0, 30, tzinfo=timezone.utc)
        next_run = ReportJobRepository.next_run_at(
            "DAILY", 9, 45, None, "Asia/Seoul", now=now
        )

        self.assertEqual(next_run, datetime(2026, 8, 3, 0, 45, tzinfo=timezone.utc))

    def test_custom_time_range_is_stored_with_kst_boundaries(self):
        result = ReportJobRepository._validate_target(
            "CUSTOM", "", "2026-08-03T08:00", "2026-08-03T09:00"
        )

        self.assertEqual(result[0], "CUSTOM")
        self.assertEqual(
            result[1], "2026-08-03T08:00:00/2026-08-03T09:00:00"
        )
        self.assertEqual(result[3].utcoffset().total_seconds(), 9 * 3600)

    def test_custom_time_range_rejects_reverse_period(self):
        with self.assertRaises(ValueError):
            ReportJobRepository._validate_target(
                "CUSTOM", "", "2026-08-03T09:00", "2026-08-03T08:00"
            )

    def test_monthly_schedule_targets_previous_month(self):
        schedule = {
            "timezone": "Asia/Seoul",
            "next_run_at": datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc),
            "report_type": "MONTHLY",
        }

        self.assertEqual(ReportJobRepository.scheduled_target(schedule), "2026-07")


if __name__ == "__main__":
    unittest.main()

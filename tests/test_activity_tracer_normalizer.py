import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from normalizers.activitytracereventnormalizer import (
    ActivityTracerEventNormalizer,
)


class ActivityTracerEventNormalizerTests(unittest.TestCase):
    def test_adds_readable_kst_time_without_changing_raw_timestamp(self):
        event_dt = datetime(
            2026,
            6,
            15,
            13,
            45,
            12,
            345000,
            tzinfo=ZoneInfo("Asia/Seoul"),
        )
        event_time = int(event_dt.timestamp() * 1000)

        result = ActivityTracerEventNormalizer().normalize(
            [{"historyId": "one", "eventTime": event_time}]
        )

        self.assertEqual(result[0]["event_time"], event_time)
        self.assertEqual(
            result[0]["event_time_kst"],
            "2026-06-15 13:45:12.345 KST",
        )

    def test_invalid_event_time_is_preserved_without_failing_event(self):
        result = ActivityTracerEventNormalizer().normalize(
            [{"historyId": "one", "eventTime": "unknown"}]
        )

        self.assertEqual(result[0]["event_time"], "unknown")
        self.assertIsNone(result[0]["event_time_kst"])

    def test_events_are_sorted_oldest_first_with_unknown_times_last(self):
        result = ActivityTracerEventNormalizer().normalize(
            [
                {"historyId": "late", "eventTime": 1781508600000},
                {"historyId": "unknown", "eventTime": "unknown"},
                {"historyId": "early", "eventTime": 1781505000000},
                {"historyId": "same", "eventTime": 1781505000000},
            ]
        )

        self.assertEqual(
            [event["event_id"] for event in result],
            ["early", "same", "late", "unknown"],
        )


if __name__ == "__main__":
    unittest.main()

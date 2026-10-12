import unittest

from normalizers.insighteventnormalizer import InsightEventNormalizer


class InsightEventNormalizerTests(unittest.TestCase):
    def test_event_detail_fields_and_kst_time_are_preserved(self):
        normalizer = InsightEventNormalizer()

        result = normalizer.normalize(
            [
                {
                    "eventId": "event-1",
                    "startTime": 1785646800000,
                    "calc": "AVG",
                    "interval": "Min5",
                    "metricGroupItemId": "metric-item-1",
                    "calcSlidingGroupKey": "detail-key",
                    "metric": "cpu_used_rto",
                    "criteria": "80",
                    "operatorSymbol": ">=",
                    "detectValue": "91.5",
                    "unit": "%",
                }
            ]
        )

        event = result[0]
        self.assertEqual(event["calc"], "AVG")
        self.assertEqual(event["interval"], "Min5")
        self.assertEqual(event["metric_group_item_id"], "metric-item-1")
        self.assertEqual(event["calc_sliding_group_key"], "detail-key")
        self.assertTrue(event["start_time_kst"].endswith(" KST"))

    def test_events_are_sorted_oldest_first_with_unknown_times_last(self):
        normalizer = InsightEventNormalizer()

        result = normalizer.normalize(
            [
                {"eventId": "late", "startTime": 1781508600000},
                {"eventId": "unknown"},
                {"eventId": "early", "startTime": "1781505000000"},
                {"eventId": "same", "startTime": 1781505000000},
            ]
        )

        self.assertEqual(
            [event["event_id"] for event in result],
            ["early", "same", "late", "unknown"],
        )

        grouped = normalizer.group_events(result, group_by="level")
        self.assertEqual(
            [event["event_id"] for event in grouped["unknown"]],
            ["early", "same", "late", "unknown"],
        )


if __name__ == "__main__":
    unittest.main()

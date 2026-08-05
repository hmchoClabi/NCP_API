import unittest
from datetime import datetime

from database.config import DatabaseSettings
from database.report_repository import PostgresReportRepository


class ReportRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.repository = PostgresReportRepository(DatabaseSettings())

    def test_customer_code_is_stable_and_schema_compatible(self):
        first = self.repository._customer_code("Customer.With Spaces")
        second = self.repository._customer_code("Customer.With Spaces")

        self.assertEqual(first, second)
        self.assertRegex(first, r"^[a-z0-9][a-z0-9_-]+[a-z0-9]$")
        self.assertLessEqual(len(first), 80)

    def test_inclusive_report_end_is_saved_as_exclusive(self):
        start, end, end_exclusive = self.repository._period_bounds(
            {
                "start_dt": "2026-07-01 00:00:00",
                "end_dt": "2026-07-01 23:59:59",
            }
        )

        self.assertTrue(end_exclusive)
        self.assertEqual(start.hour, 0)
        self.assertEqual(end, datetime(2026, 7, 2, tzinfo=self.repository.KST))

    def test_invalid_source_ip_is_not_sent_to_inet_column(self):
        self.assertIsNone(self.repository._ip_address("not-an-ip"))
        self.assertEqual(self.repository._ip_address("218.38.161.126"), "218.38.161.126")


if __name__ == "__main__":
    unittest.main()

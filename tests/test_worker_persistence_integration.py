import os
import unittest

import pytest

from app.report_models import ReportResult
from database.config import DatabaseSettings
from database.report_repository import PostgresReportRepository


@pytest.mark.worker_integration
class WorkerPersistenceIntegrationTests(unittest.TestCase):
    def test_public_worker_can_replace_report_details(self):
        settings = DatabaseSettings.from_env()
        self.assertEqual(settings.role, "public_worker")
        account_id = os.environ["TEST_CLOUD_ACCOUNT_ID"]
        report = ReportResult(
            period={
                "period_type": "day",
                "start_dt": "2026-08-02 00:00:00",
                "end_dt": "2026-08-02 23:59:59",
                "billing_month": "202608",
                "file_suffix": "worker_persistence_20260802",
            },
            customer={
                "id": "worker-persistence-integration",
                "name": "Worker Persistence Integration",
                "api_type": "public",
                "region": "KR",
                "cloud_account_id": account_id,
                "cloud_account_code": "worker-test",
            },
            activity_events={"events": []},
            billing={"summary": {}},
        )
        repository = PostgresReportRepository(settings)

        first_id = repository.save_report(report)
        second_id = repository.save_report(report)

        self.assertEqual(first_id, second_id)
        self.assertEqual(repository.last_report_run_id, second_id)


if __name__ == "__main__":
    unittest.main()

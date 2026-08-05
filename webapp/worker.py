from __future__ import annotations

import argparse
import os

from app.apifactory import APIFactory
from app.runner import ReportRunner
from database import PostgresReportRepository
from database.config import DatabaseSettings
from webapp.repository import PortalRepository
from webapp.security import CredentialCipher, LocalKeyEncryptionProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a report for a stored NCP account")
    parser.add_argument("--account-id", required=True)
    period = parser.add_mutually_exclusive_group(required=True)
    period.add_argument("--target-day")
    period.add_argument("--target-month")
    args = parser.parse_args()

    settings = DatabaseSettings.from_env()
    key_file = os.environ["CREDENTIAL_MASTER_KEY_FILE"]
    portal = PortalRepository(settings)
    customer, credentials = portal.account_credentials(
        args.account_id,
        CredentialCipher(LocalKeyEncryptionProvider(key_file)),
    )
    runner = ReportRunner(
        api_factory=APIFactory(credentials=credentials),
        customer=customer,
        report_repository=PostgresReportRepository(settings),
    )
    runner.run(target_day=args.target_day, target_month=args.target_month)


if __name__ == "__main__":
    main()

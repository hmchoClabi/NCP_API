from __future__ import annotations

import argparse
import time

from database.config import DatabaseSettings
from webapp.repository import PortalRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Retry durable local report artifact cleanup jobs")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--interval-seconds", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1_000:
        parser.error("--limit must be between 1 and 1000.")
    if args.interval_seconds and args.interval_seconds < 60:
        parser.error("--interval-seconds must be 0 or at least 60.")

    repository = PortalRepository(DatabaseSettings.from_env())
    while True:
        retention_queued = repository.enqueue_expired_report_cleanup(limit=args.limit)
        reports = repository.process_requested_report_cleanup(limit=args.limit)
        removed, pending = repository.retry_artifact_cleanup(limit=args.limit)
        print(
            f"Retention requests queued: {retention_queued}; "
            f"reports deleted: {reports['deleted_count']}; "
            f"report requests protected: {reports['protected_count']}; "
            f"report requests failed: {reports['failed_count']}; "
            f"removed artifact files: "
            f"{reports['removed_artifact_files'] + removed}; "
            f"pending artifact rows: {pending}",
            flush=True,
        )
        if not args.interval_seconds:
            return
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()

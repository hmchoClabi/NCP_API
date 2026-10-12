from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import threading
from dataclasses import replace

from app.apifactory import APIFactory
from app.runner import ReportRunner
from database import PostgresReportRepository
from database.config import DatabaseSettings
from utils.common_rest import safe_exception_message
from webapp.jobs import ReportJobRepository
from webapp.repository import PortalRepository
from webapp.security import CredentialCipher, LocalKeyEncryptionProvider


LOGGER = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Process queued NCP report jobs")
    parser.add_argument("--environment", choices=("public", "gov"), required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    settings = DatabaseSettings.from_env()
    expected_role = f"{args.environment}_worker"
    if settings.role != expected_role:
        parser.error(f"REPORT_DB_ROLE must be {expected_role} for this worker.")
    key_file = os.environ["CREDENTIAL_MASTER_KEY_FILE"]
    cipher = CredentialCipher(LocalKeyEncryptionProvider(key_file))
    portal = PortalRepository(settings)
    jobs = ReportJobRepository(settings)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    poll_seconds = max(2, int(os.getenv("WORKER_POLL_SECONDS", "5")))

    while not stop.is_set():
        job = jobs.claim(args.environment, worker_id)
        if not job:
            if args.once:
                break
            stop.wait(poll_seconds)
            continue
        _process_job(job, settings, portal, cipher, jobs)
        if args.once:
            break


def _process_job(job, settings, portal, cipher, jobs) -> None:
    api_factory = None
    try:
        customer, credentials = portal.account_credentials(str(job["cloud_account_id"]), cipher)
        tenant_settings = replace(settings, tenant_id=str(job["tenant_id"]))
        repository = PostgresReportRepository(
            tenant_settings,
            idempotency_suffix=str(job["id"]),
            trigger_type=job["trigger_type"],
        )
        api_factory = APIFactory(credentials=credentials)
        runner = ReportRunner(
            output_dir=os.path.join(
                os.environ.get("REPORT_OUTPUT_DIR", "/app/output/report"),
                customer.customer_id,
                customer.cloud_account_code or str(job["cloud_account_id"]),
                str(job["id"]),
            ),
            api_factory=api_factory,
            customer=customer,
            report_repository=repository,
        )
        target = job["target_value"]
        runner.run(
            target_day=target if job["report_type"] == "DAILY" else None,
            target_week=target if job["report_type"] == "WEEKLY" else None,
            target_month=target if job["report_type"] == "MONTHLY" else None,
            start_datetime=(
                job["period_start"].astimezone(ReportRunner.KST).isoformat()
                if job["report_type"] == "CUSTOM"
                else None
            ),
            end_datetime=(
                job["period_end"].astimezone(ReportRunner.KST).isoformat()
                if job["report_type"] == "CUSTOM"
                else None
            ),
        )
        jobs.complete(str(job["id"]), repository.last_report_run_id)
        LOGGER.info("Completed report job %s.", job["id"])
    except Exception as exc:
        message = safe_exception_message(exc)
        jobs.fail(str(job["id"]), message)
        LOGGER.error("Report job %s failed: %s", job["id"], message)
    finally:
        if api_factory is not None:
            api_factory.clear_cache()


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import logging
import os
import signal
import threading

from database.config import DatabaseSettings
from webapp.jobs import ReportJobRepository

LOGGER = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Enqueue due report schedules")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    repository = ReportJobRepository(DatabaseSettings.from_env())
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    poll_seconds = max(5, int(os.getenv("SCHEDULER_POLL_SECONDS", "30")))
    stale_minutes = max(30, int(os.getenv("WORKER_STALE_MINUTES", "360")))

    while not stop.is_set():
        try:
            stale_count = repository.requeue_stale(stale_minutes)
            if stale_count:
                LOGGER.warning("Requeued %d stale report job(s).", stale_count)
            count = repository.enqueue_due_schedules()
            if count:
                LOGGER.info("Enqueued %d scheduled report job(s).", count)
        except Exception:
            LOGGER.exception("Failed to enqueue scheduled report jobs.")
        if args.once:
            break
        stop.wait(poll_seconds)


if __name__ == "__main__":
    main()

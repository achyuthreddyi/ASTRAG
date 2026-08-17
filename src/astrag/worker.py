"""Ingestion worker: `python -m astrag.worker`.

A separate process on purpose. In-process tasks die with the API, which would
make the crash-recovery requirement untestable.
"""

import logging
import signal
import time

from astrag.ingest.executor import run_once
from astrag.settings import get_settings
from astrag.storage.artifacts import get_artifact_store
from astrag.storage.database import get_sessionmaker

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    store = get_artifact_store()
    sessions = get_sessionmaker()

    running = True

    def stop(*_) -> None:
        nonlocal running
        running = False
        log.info("stopping after the current job")

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    log.info("worker started, polling every %ss", settings.poll_interval_seconds)
    while running:
        with sessions() as db:
            job = run_once(db, store)
        # Polling, not LISTEN/NOTIFY: one query per second against an indexed
        # partial predicate costs nothing, and a broker is stage 10's problem.
        if job is None and running:
            time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    main()

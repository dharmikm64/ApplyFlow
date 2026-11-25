"""Postgres-backed scan worker (research R6).

WORKER_MODE=embedded runs this loop in a daemon thread inside the API process;
WORKER_MODE=external runs it standalone: `python -m app.jobs.worker`.
"""

from __future__ import annotations

import logging
import socket
import threading
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.db import get_sessionmaker
from app.jobs.scan_job import run_scan

log = logging.getLogger(__name__)
STALE_AFTER = timedelta(minutes=2)
MAX_ATTEMPTS = 5
IDLE_SLEEP_SECONDS = 1.0

CLAIM_SQL = text(
    """
    SELECT id, attempt FROM scan_runs
    WHERE status = 'queued'
       OR (status = 'running' AND (heartbeat_at IS NULL OR heartbeat_at < :stale_before))
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
    """
)


def claim_one(worker_id: str) -> uuid.UUID | None:
    sm = get_sessionmaker()
    with sm() as db:
        now = datetime.now(UTC)
        row = db.execute(CLAIM_SQL, {"stale_before": now - STALE_AFTER}).first()
        if row is None:
            db.rollback()
            return None
        run_id, attempt = row
        if attempt + 1 > MAX_ATTEMPTS:
            db.execute(
                text(
                    "UPDATE scan_runs SET status='failed', failure_code='internal_error', "
                    "finished_at=:now WHERE id=:id"
                ),
                {"id": run_id, "now": now},
            )
            db.commit()
            return None
        db.execute(
            text(
                "UPDATE scan_runs SET status='running', worker_id=:w, attempt=attempt+1, "
                "heartbeat_at=:now, started_at=COALESCE(started_at, :now) WHERE id=:id"
            ),
            {"id": run_id, "w": worker_id, "now": now},
        )
        db.commit()
        return run_id


def process_one(worker_id: str) -> bool:
    run_id = claim_one(worker_id)
    if run_id is None:
        return False
    try:
        run_scan(run_id)
    except Exception as exc:  # SimulatedCrash in tests, or a truly unexpected failure
        log.warning("scan run interrupted", extra={"run_id": str(run_id), "error_type": type(exc).__name__})
    return True


def run_until_idle(worker_id: str = "test-worker", max_runs: int = 50) -> int:
    """Process runs until none are claimable (used by tests)."""
    count = 0
    while count < max_runs and process_one(worker_id):
        count += 1
    return count


class EmbeddedWorker:
    def __init__(self) -> None:
        self.worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="scan-worker", daemon=True)

    def start(self) -> EmbeddedWorker:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = process_one(self.worker_id)
            except Exception as exc:  # never let the loop die
                log.error("worker loop error", extra={"error_type": type(exc).__name__})
                worked = False
            if not worked:
                self._stop.wait(IDLE_SLEEP_SECONDS)


def start_embedded_worker() -> EmbeddedWorker:
    return EmbeddedWorker().start()


if __name__ == "__main__":  # external mode
    from app.config import get_settings
    from app.logging import configure_logging

    configure_logging(get_settings().LOG_LEVEL)
    worker = EmbeddedWorker()
    log.info("external scan worker started")
    worker._loop()

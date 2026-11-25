"""Run one scan/sync, resumably (research R6, FR-007..FR-011, FR-041).

Progress is committed after every Gmail list page together with the resume cursor
(segment_index, page_token). Re-running after a crash resumes from the cursor; anything
already processed is skipped by the processed_messages idempotency key.
"""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.orm import Session as DbSession

from app import clock
from app.config import get_settings
from app.db import get_sessionmaker
from app.gmail import get_gmail_client
from app.gmail.client import GmailAuthError, GmailError
from app.models import GmailConnection, RecruitingCycle, ScanRun
from app.pipeline.apply import already_processed, apply_extraction, record_message
from app.pipeline.extraction.extract import extract, parse_message
from app.pipeline.retrieval import fetch_page
from app.pipeline.window import ms_to_utc, parse_seg

log = logging.getLogger(__name__)
HEARTBEAT_SECONDS = 15


class Stop(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _heartbeat_loop(run_id: uuid.UUID, stop: threading.Event) -> None:
    sm = get_sessionmaker()
    while not stop.wait(HEARTBEAT_SECONDS):
        with sm() as db:
            db.execute(
                update(ScanRun)
                .where(ScanRun.id == run_id, ScanRun.status == "running")
                .values(heartbeat_at=datetime.now(UTC))
            )
            db.commit()


def _fail(db: DbSession, run: ScanRun, code: str) -> None:
    run.status = "failed"
    run.failure_code = code
    run.finished_at = datetime.now(UTC)
    db.commit()


def _connection_ok(db: DbSession, user_id: uuid.UUID) -> GmailConnection:
    db.expire_all()
    conn = db.get(GmailConnection, user_id)
    if conn is None:
        raise Stop("gmail_disconnected")
    if conn.status != "connected" or conn.refresh_token_ciphertext is None:
        raise Stop("reconnect_required" if conn.status == "revoked" else "gmail_disconnected")
    return conn


def _mark_revoked(db: DbSession, user_id: uuid.UUID) -> None:
    conn = db.get(GmailConnection, user_id)
    if conn is not None:
        conn.status = "revoked"
        conn.refresh_token_ciphertext = None
        conn.last_error = "invalid_grant"


def run_scan(run_id: uuid.UUID) -> None:
    """Execute (or resume) a claimed run. The caller has already set status='running'."""
    db = get_sessionmaker()()
    stop = threading.Event()
    hb = threading.Thread(target=_heartbeat_loop, args=(run_id, stop), daemon=True)
    hb.start()
    try:
        run = db.get(ScanRun, run_id)
        if run is None or run.status != "running":
            return
        _execute(db, run)
    finally:
        stop.set()
        db.close()


def _execute(db: DbSession, run: ScanRun) -> None:
    user_id = run.user_id
    cycle = db.get(RecruitingCycle, user_id)
    if cycle is None:
        _fail(db, run, "internal_error")
        return
    tz = cycle.timezone
    try:
        conn = _connection_ok(db, user_id)
        client = get_gmail_client(db, conn)
        if cycle.source_gmail_address is None:
            cycle.source_gmail_address = conn.gmail_address
            db.commit()
        with ThreadPoolExecutor(max_workers=get_settings().GMAIL_CONCURRENCY) as pool:
            while run.segment_index < len(run.segments):
                seg_from, seg_to = parse_seg(run.segments[run.segment_index])
                first_page = run.page_token is None
                while True:
                    _connection_ok(db, user_id)  # stop immediately after a disconnect (FR-041)
                    page = fetch_page(
                        client,
                        seg_from=seg_from,
                        seg_to=seg_to,
                        page_token=run.page_token,
                        seen=lambda ids: already_processed(db, user_id, ids),
                        pool=pool,
                        check=lambda: _connection_ok(db, user_id),
                    )
                    if first_page:
                        run.estimated_total = (run.estimated_total or 0) + page.result_size_estimate
                        first_page = False
                    _persist_page(db, run, user_id, tz, page)
                    run.page_token = page.next_page_token
                    run.heartbeat_at = datetime.now(UTC)
                    db.commit()
                    if page.next_page_token is None:
                        break
                run.segment_index += 1
                run.page_token = None
                db.commit()
        _connection_ok(db, user_id)  # a disconnect during the last page still wins
    except Stop as stop:
        db.rollback()
        _fail(db, run, stop.code)
        return
    except GmailAuthError as exc:
        db.rollback()
        log.warning("scan stopped: gmail auth error", extra={"detail": str(exc)})
        _mark_revoked(db, user_id)
        _fail(db, run, "reconnect_required")
        return
    except GmailError as exc:
        db.rollback()
        log.warning("scan failed: gmail unavailable", extra={"detail": str(exc)})
        _fail(db, run, "gmail_unavailable")
        return
    except Exception as exc:
        from app.testing.fixture_gmail import SimulatedCrash

        if isinstance(exc, SimulatedCrash):
            db.rollback()
            raise  # behave like a dead process: leave the run 'running' for reclaim
        db.rollback()
        log.error("scan failed", extra={"error_type": type(exc).__name__, "run_id": str(run.id)})
        _fail(db, run, "internal_error")
        return

    # Success: advance coverage atomically with the run status (FR-011).
    cycle = db.get(RecruitingCycle, user_id)
    if cycle is not None:
        if cycle.covered_from_utc is None or run.window_start_utc < cycle.covered_from_utc:
            cycle.covered_from_utc = run.window_start_utc
        if cycle.covered_to_utc is None or run.window_end_utc > cycle.covered_to_utc:
            cycle.covered_to_utc = run.window_end_utc
    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    db.commit()


def _persist_page(db: DbSession, run: ScanRun, user_id: uuid.UUID, tz: str, page) -> None:
    run.listed += page.listed
    run.screened += len(page.in_window)
    run.candidates += len(page.candidates)
    for meta in page.non_candidates:
        record_message(
            db, user_id, None, gmail_id=meta.id, thread_id=meta.thread_id,
            internal_date=ms_to_utc(meta.internal_date_ms), result=None,
        )
        run.processed += 1
    for full in page.candidates:
        parsed = parse_message(full)
        result = extract(parsed)
        outcome = apply_extraction(db, user_id, parsed, result, tz)
        run.processed += 1
        run.created_apps += int(outcome.created_app)
        run.updated_apps += int(outcome.updated_app)
        run.review_items += outcome.review_items


def create_run(db: DbSession, user_id: uuid.UUID, kind: str, segments: list[dict]) -> ScanRun:
    now = clock.now()
    starts = [parse_seg(s)[0] for s in segments] or [now]
    run = ScanRun(
        user_id=user_id,
        kind=kind,
        status="queued",
        window_start_utc=min(starts),
        window_end_utc=now,
        segments=segments,
        segment_index=0,
    )
    db.add(run)
    db.flush()
    return run

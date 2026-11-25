"""Performance check for SC-002 / SC-007 with a synthetic 3,000-message mailbox (T110).

Runs the real scan pipeline (retrieval, screening, extraction, matching, persistence) against
an in-memory Gmail with simulated per-request latency, on the *_test database.

Usage (from backend/):  APP_ENV=test .venv/bin/python scripts/perf_synthetic_scan.py [latency_ms]
"""

from __future__ import annotations

import os
import random
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

os.environ["APP_ENV"] = "test"
os.environ.setdefault("WORKER_MODE", "off")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "fixtures"))

from build_fixtures import build  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import clock  # noqa: E402
from app.auth import crypto  # noqa: E402
from app.db import get_engine, get_sessionmaker  # noqa: E402
from app.gmail.client import ListPage  # noqa: E402
from app.gmail.parse import full_from_api, meta_from_api  # noqa: E402
from app.jobs import scan_job  # noqa: E402
from app.jobs.worker import run_until_idle  # noqa: E402
from app.models import GmailConnection, RecruitingCycle, User  # noqa: E402
from app.pipeline.window import segments_for_run  # noqa: E402

N_TOTAL = 3000
N_COMPANIES = 120
START = datetime(2026, 7, 1, tzinfo=UTC)
NOW = datetime(2026, 10, 1, tzinfo=UTC)
ROLES = ["Software Engineer", "Data Analyst", "Product Manager", "Designer", "QA Engineer"]


def make_messages(seed: int = 7) -> list[dict]:
    rnd = random.Random(seed)
    msgs = []
    span = (NOW - START).total_seconds()
    for i in range(N_TOTAL):
        when = START + timedelta(seconds=rnd.random() * span)
        if i < N_COMPANIES * 2:  # ~240 recruiting emails: confirmations, then some updates
            c = f"Company{i % N_COMPANIES:03d} Labs"
            role = ROLES[i % len(ROLES)]
            if i < N_COMPANIES:
                body = f"Thanks for applying to {c}. Your application for the {role} role has been received."
                subj = f"Thank you for applying to {c}"
            else:
                body = f"Unfortunately, we will not be moving forward with your application for the {role} role at {c}."
                subj = f"Your application to {c}"
                when = max(when, START + timedelta(days=45))
            src = {"id": f"p{i}", "thread": f"t{i}", "date": when, "from": f"{c} <no-reply@greenhouse.io>",
                   "subject": subj, "body": body}
        elif i < 600:  # job alerts / marketing that pass screening but are noise
            src = {"id": f"p{i}", "thread": f"t{i}", "date": when, "from": "Alerts <jobalerts@linkedin.com>",
                   "subject": "New jobs for you", "body": "Jobs you may be interested in. Apply now.", "unsubscribe": True}
        else:  # ordinary non-recruiting mail
            src = {"id": f"p{i}", "thread": f"t{i}", "date": when, "from": f"Friend {i} <f{i}@mail.example>",
                   "subject": f"Weekend plans {i}", "body": "Want to grab dinner on Saturday?"}
        msgs.append(build(src))
    return msgs


class PerfGmail:
    def __init__(self, msgs: list[dict], latency: float) -> None:
        self.msgs = sorted(msgs, key=lambda m: int(m["internalDate"]), reverse=True)
        self.by_id = {m["id"]: m for m in msgs}
        self.latency = latency
        self.calls = 0

    def _wait(self):
        self.calls += 1
        time.sleep(self.latency)

    def get_profile(self):
        from app.gmail.client import Profile

        return Profile("perf@candidate.test")

    def list_message_ids(self, query, page_token, max_results=500):
        self._wait()
        start = int(page_token or 0)
        page = self.msgs[start : start + max_results]
        nxt = start + max_results
        return ListPage([m["id"] for m in page], str(nxt) if nxt < len(self.msgs) else None, len(self.msgs))

    def get_metadata(self, mid):
        self._wait()
        return meta_from_api(self.by_id[mid])

    def get_full(self, mid):
        self._wait()
        return full_from_api(self.by_id[mid])


def main() -> None:
    latency_ms = float(sys.argv[1]) if len(sys.argv) > 1 else 50.0
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE review_items, application_events, applications, processed_messages, "
                          "scan_runs, recruiting_cycles, gmail_connections, sessions, users CASCADE"))
    clock.set_override(NOW)
    gmail = PerfGmail(make_messages(), latency_ms / 1000)
    scan_job.get_gmail_client = lambda db, conn: gmail  # type: ignore[assignment]

    with get_sessionmaker()() as db:
        user = User(google_sub="perf", email="perf@example.test")
        db.add(user)
        db.flush()
        db.add(RecruitingCycle(user_id=user.id, start_date=date(2026, 7, 1), timezone="UTC"))
        db.add(GmailConnection(user_id=user.id, gmail_address="perf@candidate.test", status="connected",
                               refresh_token_ciphertext=crypto.encrypt("x"), granted_scopes=["gmail.readonly"]))
        segs = segments_for_run(start_date=date(2026, 7, 1), tz="UTC", covered_from=None, covered_to=None,
                                now=NOW, kind="initial")
        scan_job.create_run(db, user.id, "initial", segs)
        db.commit()
        uid = user.id

    t0 = time.perf_counter()
    run_until_idle("perf-worker")
    elapsed = time.perf_counter() - t0

    with get_sessionmaker()() as db:
        run = db.execute(text("SELECT status, listed, screened, candidates, processed, created_apps FROM scan_runs WHERE user_id=:u"),
                         {"u": uid}).one()
    print(f"messages={N_TOTAL} latency={latency_ms:.0f}ms/request concurrency={os.environ.get('GMAIL_CONCURRENCY', '8')}")
    print(f"run: status={run.status} listed={run.listed} screened={run.screened} candidates={run.candidates} "
          f"processed={run.processed} created_apps={run.created_apps} gmail_calls={gmail.calls}")
    print(f"scan time: {elapsed:.1f}s (SC-002 target: <= 600s)")

    # SC-007: returning user's dashboard data (me + applications) after sign-in.
    from fastapi.testclient import TestClient

    from app.auth.sessions import create_session
    from app.main import app

    with get_sessionmaker()() as db:
        raw = create_session(db, uid)
        db.commit()
    with TestClient(app) as c:
        c.cookies.set("af_session", raw)
        t1 = time.perf_counter()
        assert c.get("/api/me").status_code == 200
        r = c.get("/api/applications")
        t_load = time.perf_counter() - t1
    print(f"dashboard data load: {t_load * 1000:.0f}ms for {r.json()['total']} rows (SC-007 target: <= 3s)")


if __name__ == "__main__":
    main()

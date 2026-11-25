"""Two-stage retrieval for one Gmail list page (research R7, FR-007/044).

1. list message IDs in the padded window (no keyword filter),
2. fetch metadata (no body) for unseen IDs with bounded concurrency, apply the exact window,
   screen for recruiting relevance,
3. fetch full content only for candidates; bodies stay in memory.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

from app.gmail.client import GmailClient, MessageFull, MessageMeta
from app.pipeline.screening import screen
from app.pipeline.window import gmail_query, in_window

PAGE_SIZE = 500


@dataclass
class PageResult:
    next_page_token: str | None
    result_size_estimate: int
    listed: int = 0
    in_window: list[MessageMeta] = field(default_factory=list)
    non_candidates: list[MessageMeta] = field(default_factory=list)
    candidates: list[MessageFull] = field(default_factory=list)


def fetch_page(
    client: GmailClient,
    *,
    seg_from: datetime,
    seg_to: datetime,
    page_token: str | None,
    seen: Callable[[list[str]], set[str]],
    pool: ThreadPoolExecutor,
    check: Callable[[], object] = lambda: None,
) -> PageResult:
    """`check()` raises to stop before each batch of Gmail requests (disconnect, FR-041)."""
    page = client.list_message_ids(gmail_query(seg_from, seg_to), page_token, PAGE_SIZE)
    result = PageResult(page.next_page_token, page.result_size_estimate, listed=len(page.ids))
    already = seen(page.ids)
    fresh = [mid for mid in page.ids if mid not in already]

    check()
    metas = list(pool.map(client.get_metadata, fresh))
    # Messages returned only because of the ±1-day query padding are skipped WITHOUT being
    # recorded, so a later back-fill (start date moved earlier) still processes them.
    result.in_window = [m for m in metas if in_window(m.internal_date_ms, seg_from, seg_to)]
    candidate_ids: list[str] = []
    for meta in result.in_window:
        if screen(meta).is_candidate:
            candidate_ids.append(meta.id)
        else:
            result.non_candidates.append(meta)

    check()
    fulls = list(pool.map(client.get_full, candidate_ids))
    result.candidates = sorted(fulls, key=lambda f: (f.meta.internal_date_ms, f.meta.id))
    return result

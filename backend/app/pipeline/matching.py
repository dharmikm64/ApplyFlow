"""Application matching (research R10, FR-021..FR-024). Pure functions.

One row = one application. Matching uses requisition IDs when present, then company +
normalized position. Gmail thread membership is only ever *supporting* evidence. Anything
uncertain becomes Ambiguous (-> review) rather than being merged automatically.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime

LEGAL_SUFFIXES = {
    "inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "co", "gmbh",
    "plc", "sa", "ag", "bv", "pty", "lp", "llp",
}
POSITION_ABBREV = {
    "sr": "senior",
    "jr": "junior",
    "swe": "software engineer",
    "sde": "software development engineer",
    "eng": "engineer",
    "engr": "engineer",
    "mgr": "manager",
    "dev": "developer",
    "pm": "product manager",
    "ii": "2",
    "iii": "3",
    "i": "1",
}
_NON_WORD = re.compile(r"[^a-z0-9]+")
_REQ_IN_TITLE = re.compile(r"(?:\(|\[)?\b(?:req|r|jr|job)?[-#\s]*\d{3,}[\w-]*(?:\)|\])?", re.I)
SIMILARITY_THRESHOLD = 0.6


def normalize_company(name: str | None) -> str | None:
    if not name:
        return None
    tokens = [t for t in _NON_WORD.sub(" ", name.lower()).split() if t]
    tokens = [t for t in tokens if t != "the"]
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens) or None


def normalize_position(title: str | None) -> str | None:
    if not title:
        return None
    value = _REQ_IN_TITLE.sub(" ", title)
    tokens = [t for t in _NON_WORD.sub(" ", value.lower()).split() if t]
    expanded: list[str] = []
    for t in tokens:
        expanded.extend(POSITION_ABBREV.get(t, t).split())
    return " ".join(expanded) or None


def jaccard(a: str, b: str) -> float:
    sa, sb = set(a.split()), set(b.split())
    return len(sa & sb) / len(sa | sb) if sa | sb else 0.0


@dataclass
class Candidate:
    """Summary of an existing application, as needed for matching."""

    id: uuid.UUID
    company_norm: str | None
    position_norm: str | None
    req_id: str | None
    rejected_at: datetime | None = None
    sender_domains: set[str] = field(default_factory=set)
    thread_ids: set[str] = field(default_factory=set)


@dataclass
class Incoming:
    kind: str
    company: str | None
    position: str | None
    req_id: str | None
    occurred_at: datetime
    sender_domain: str
    thread_id: str | None


@dataclass
class MatchResult:
    outcome: str  # "new" | "existing" | "ambiguous" | "unmatchable"
    application_id: uuid.UUID | None = None
    candidates: list[uuid.UUID] = field(default_factory=list)
    reason: str = ""


def _req_eq(a: str | None, b: str | None) -> bool:
    return bool(a and b and a.strip().lower() == b.strip().lower())


def match(inc: Incoming, candidates: list[Candidate]) -> MatchResult:
    company = normalize_company(inc.company)
    position = normalize_position(inc.position)

    if company is None:
        # Without a company only very strong supporting evidence can link the email.
        linked = [
            c for c in candidates
            if inc.thread_id and inc.thread_id in c.thread_ids and inc.sender_domain in c.sender_domains
        ]
        if len(linked) == 1:
            return MatchResult("existing", linked[0].id, reason="same thread and sender, no company")
        return MatchResult("unmatchable", reason="no company identified")

    same_company = [c for c in candidates if c.company_norm == company]

    # 1. Same requisition ID -> same application.
    if inc.req_id:
        by_req = [c for c in same_company if _req_eq(c.req_id, inc.req_id)]
        if len(by_req) == 1:
            return MatchResult("existing", by_req[0].id, reason="same requisition ID")
        if len(by_req) > 1:
            return MatchResult("ambiguous", candidates=[c.id for c in by_req], reason="duplicate requisition IDs")
    # 2. Both have req IDs and they differ -> not this candidate.
    pool = [c for c in same_company if not (inc.req_id and c.req_id and not _req_eq(c.req_id, inc.req_id))]

    if position:
        equal = [c for c in pool if c.position_norm == position]
        if len(equal) == 1:
            c = equal[0]
            # 3. A confirmation dated after a rejection, with no req ID to tell them apart,
            #    may be a re-application -> ask the user.
            if (
                inc.kind == "confirmation"
                and c.rejected_at is not None
                and inc.occurred_at > c.rejected_at
                and not _req_eq(c.req_id, inc.req_id)
            ):
                return MatchResult("ambiguous", candidates=[c.id], reason="possible re-application after rejection")
            return MatchResult("existing", c.id, reason="same company and position")
        if len(equal) > 1:
            return MatchResult("ambiguous", candidates=[c.id for c in equal], reason="several applications for this position")
        # 5. Similar but unequal positions -> ambiguous.
        similar = [
            c for c in pool
            if c.position_norm and jaccard(c.position_norm, position) >= SIMILARITY_THRESHOLD
        ]
        unknown_pos = [
            c for c in pool if c.position_norm is None and inc.sender_domain in c.sender_domains
        ]
        if similar or unknown_pos:
            return MatchResult(
                "ambiguous",
                candidates=[c.id for c in similar + unknown_pos],
                reason="similar position at the same company",
            )
        return MatchResult("new", reason="new position at this company" if pool else "new company")

    # 4. Company known, position missing.
    if len(pool) == 1:
        c = pool[0]
        if inc.sender_domain in c.sender_domains or (inc.thread_id and inc.thread_id in c.thread_ids):
            return MatchResult("existing", c.id, reason="only application at this company, same sender")
        return MatchResult("ambiguous", candidates=[c.id], reason="position not stated")
    if len(pool) > 1:
        return MatchResult("ambiguous", candidates=[c.id for c in pool], reason="position not stated; several applications at this company")
    return MatchResult("new", reason="new company; position not stated")

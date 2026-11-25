"""Metadata relevance screening (research R7). Tuned for recall.

A message becomes a candidate (and is fetched in full) if it has ANY one of:
  (a) a sender domain on the ATS / job-platform list;
  (b) a recruiting local part (careers@, recruiting@, ...);
  (c) a recruiting phrase in the subject or snippet.
Noise (job alerts, marketing) is decided later by extraction, not here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from email.utils import parseaddr

from app.gmail.client import MessageMeta

ATS_DOMAINS = (
    "greenhouse.io",
    "greenhouse-mail.io",
    "lever.co",
    "hire.lever.co",
    "myworkday.com",
    "myworkdayjobs.com",
    "workday.com",
    "ashbyhq.com",
    "icims.com",
    "smartrecruiters.com",
    "jobvite.com",
    "workable.com",
    "workablemail.com",
    "taleo.net",
    "successfactors.com",
    "successfactors.eu",
    "bamboohr.com",
    "recruitee.com",
    "jazzhr.com",
    "applytojob.com",
    "breezy.hr",
    "teamtailor.com",
    "rippling.com",
    "linkedin.com",
    "indeed.com",
    "indeedemail.com",
    "glassdoor.com",
    "ziprecruiter.com",
    "joinhandshake.com",
    "wellfound.com",
    "dice.com",
    "hackerrank.com",
    "codesignal.com",
    "hirevue.com",
    "goodtime.io",
    "calendly.com",
)
RECRUITING_LOCAL_PARTS = (
    "careers",
    "career",
    "recruiting",
    "recruiter",
    "recruitment",
    "talent",
    "jobs",
    "job",
    "hr",
    "hiring",
    "people",
)
RECRUITING_PHRASES = (
    "application",
    "applying",
    "applied",
    "interview",
    "assessment",
    "screening",
    "candidate",
    "candidacy",
    "position",
    "role",
    "requisition",
    "offer",
    "next steps",
    "move forward",
    "moving forward",
    "unfortunately",
)
_PHRASE_RE = re.compile(r"\b(" + "|".join(re.escape(p) for p in RECRUITING_PHRASES) + r")", re.I)
_LOCAL_RE = re.compile(
    r"^(" + "|".join(RECRUITING_LOCAL_PARTS) + r")([._+\-].*)?$", re.I
)


@dataclass
class ScreenResult:
    is_candidate: bool
    signals: list[str] = field(default_factory=list)


def sender_address(meta: MessageMeta) -> tuple[str, str]:
    name, addr = parseaddr(meta.headers.get("From", ""))
    return name.strip().strip('"'), addr.strip().lower()


def domain_of(addr: str) -> str:
    return addr.rsplit("@", 1)[-1] if "@" in addr else ""


def is_ats_domain(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in ATS_DOMAINS)


def screen(meta: MessageMeta) -> ScreenResult:
    _, addr = sender_address(meta)
    signals: list[str] = []
    domain = domain_of(addr)
    if domain and is_ats_domain(domain):
        signals.append(f"ats_domain:{domain}")
    local = addr.split("@", 1)[0] if "@" in addr else ""
    if local and _LOCAL_RE.match(local):
        signals.append(f"local_part:{local}")
    text = f"{meta.headers.get('Subject', '')}\n{meta.snippet}"
    if m := _PHRASE_RE.search(text):
        signals.append(f"phrase:{m.group(1).lower()}")
    return ScreenResult(is_candidate=bool(signals), signals=signals)

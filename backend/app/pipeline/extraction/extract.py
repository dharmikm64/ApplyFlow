"""Deterministic extraction pipeline (research R8, FR-013..FR-020a).

ParsedMessage -> ExtractionResult. Pure functions; no I/O; same input, same output.
Email text is treated strictly as data: nothing in it can change behavior (FR-019).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from dateutil import parser as dateparser

from app.gmail.client import MessageFull
from app.gmail.parse import body_text
from app.pipeline.extraction import ats
from app.pipeline.extraction.rules import (
    FIELD_PATTERNS,
    INVITE_TO_APPLY,
    JOB_ALERT,
    KIND_RULES,
    MARKETING,
    PLATFORM_NAMES,
    REQ_ID,
    SENDER_SUFFIXES,
    STATED_DATE,
)
from app.pipeline.screening import domain_of
from app.pipeline.window import ms_to_utc

EXCERPT_MAX = 300
APP_KINDS = ("confirmation", "progress", "rejection")
NOISE_KINDS = ("job_alert", "invite_to_apply", "marketing")
_APP_SIGNAL = re.compile(r"\b(?:application|applied|applying|candidate|candidacy|interview)\b", re.I)
_SENTENCE_END = re.compile(r"[.!?\n]")
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class ParsedMessage:
    id: str
    thread_id: str | None
    internal_date: datetime
    sender_name: str
    sender_addr: str
    subject: str
    body: str
    list_unsubscribe: bool = False

    @property
    def sender_domain(self) -> str:
        return domain_of(self.sender_addr)

    @property
    def text(self) -> str:
        return f"{self.subject}\n{self.body}"


@dataclass
class ExtractionResult:
    kind: str  # confirmation|progress|rejection|acknowledgment|offer|withdrawal|job_alert|
    #            marketing|invite_to_apply|unclear|not_recruiting
    company: str | None = None
    position: str | None = None
    req_id: str | None = None
    stated_applied_date: date | None = None
    confidence: str = "high"  # high | low
    rule_id: str | None = None
    excerpt: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "company": self.company,
            "position": self.position,
            "req_id": self.req_id,
            "stated_applied_date": self.stated_applied_date.isoformat()
            if self.stated_applied_date
            else None,
            "confidence": self.confidence,
        }


class Extractor(Protocol):
    """Seam for alternative extractors (e.g. the proposed-but-disabled LLM fallback, R9)."""

    def __call__(self, msg: ParsedMessage) -> ExtractionResult: ...


def parse_message(full: MessageFull) -> ParsedMessage:
    from email.utils import parseaddr

    name, addr = parseaddr(full.meta.headers.get("From", ""))
    return ParsedMessage(
        id=full.meta.id,
        thread_id=full.meta.thread_id,
        internal_date=ms_to_utc(full.meta.internal_date_ms),
        sender_name=name.strip().strip('"'),
        sender_addr=addr.strip().lower(),
        subject=full.meta.headers.get("Subject", ""),
        body=body_text(full),
        list_unsubscribe=bool(full.meta.headers.get("List-Unsubscribe")),
    )


# --- helpers ---------------------------------------------------------------------------------
def make_excerpt(text: str, start: int, end: int) -> str:
    left = max((m.end() for m in _SENTENCE_END.finditer(text, 0, start)), default=0)
    m = _SENTENCE_END.search(text, end)
    right = m.end() if m else len(text)
    snippet = _WS.sub(" ", text[left:right]).strip()
    if len(snippet) > EXCERPT_MAX:
        # keep the matched phrase visible
        rel = max(0, start - left - 60)
        snippet = _WS.sub(" ", text[left + rel : left + rel + EXCERPT_MAX]).strip()
        snippet = snippet[: EXCERPT_MAX - 1].rstrip() + "…"
    return snippet


def clean_company(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip().strip(".,;:!-–—'\"").strip()
    value = re.sub(r"^(?i:the)\s+", "", value)
    value = SENDER_SUFFIXES.sub("", value).strip(" -|,.")
    if len(value) < 2 or value.lower() in PLATFORM_NAMES:
        return None
    if value.lower().startswith(("no-reply", "noreply", "do-not-reply")):
        return None
    return value


def clean_position(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip().strip(".,;:!-–—'\"").strip()
    value = re.sub(r"^(?i:the|our|a|an)\s+", "", value)
    value = re.sub(r"\s+(?i:role|position|opening|job)$", "", value).strip()
    if len(value) < 2 or len(value) > 100:
        return None
    return value


def parse_date(raw: str) -> date | None:
    try:
        return dateparser.parse(raw, dayfirst=False, fuzzy=False).date()
    except (ValueError, OverflowError):
        return None


def detect_kind(msg: ParsedMessage) -> tuple[str | None, str | None, re.Match[str] | None, str]:
    """Returns (kind, rule_id, match, source_text)."""
    for source in (msg.subject, msg.body):
        for kind, rule_id, pattern in KIND_RULES:
            if m := pattern.search(source):
                return kind, rule_id, m, source
    return None, None, None, msg.text


def detect_noise(msg: ParsedMessage) -> str | None:
    text = msg.text
    if JOB_ALERT.search(text):
        return "job_alert"
    if INVITE_TO_APPLY.search(text):
        return "invite_to_apply"
    if msg.list_unsubscribe and MARKETING.search(text):
        return "marketing"
    return None


def extract_fields(msg: ParsedMessage) -> tuple[str | None, str | None, str | None]:
    """(company, position, rule_id) from ATS-specific patterns, then generic patterns."""
    company: str | None = None
    position: str | None = None
    rule: str | None = None
    parser = ats.parser_for(msg.sender_domain)
    patterns = (parser.PATTERNS if parser else []) + FIELD_PATTERNS
    for source in (msg.subject, msg.body):
        for rule_id, pattern in patterns:
            for m in pattern.finditer(source):
                groups = m.groupdict()
                c = clean_company(groups.get("company")) if company is None else None
                p = clean_position(groups.get("position")) if position is None else None
                if c:
                    company = c
                    rule = rule or rule_id
                if p:
                    position = p
                    rule = rule or rule_id
                if company and position:
                    return company, position, rule
    if company is None:
        company = company_from_sender(msg)
    return company, position, rule


def company_from_sender(msg: ParsedMessage) -> str | None:
    """Hiring company from the sender display name; never the ATS / job-board brand."""
    parser = ats.parser_for(msg.sender_domain)
    if parser is not None and not parser.DISPLAY_NAME_IS_COMPANY:
        return None
    return clean_company(msg.sender_name)


# --- pipeline -------------------------------------------------------------------------------
def extract(msg: ParsedMessage) -> ExtractionResult:
    kind, rule_id, match, source = detect_kind(msg)
    strong = kind in ("rejection", "confirmation") or rule_id == "progress.strong"
    noise = detect_noise(msg)
    if noise and not strong:
        return ExtractionResult(kind=noise, confidence="high", rule_id=f"noise.{noise}")

    excerpt = make_excerpt(source, match.start(), match.end()) if match else None
    company, position, field_rule = extract_fields(msg)
    req = REQ_ID.search(msg.text)
    stated = None
    if sd := STATED_DATE.search(msg.text):
        stated = parse_date(sd.group("d"))

    if kind is None:
        recruiting = bool(_APP_SIGNAL.search(msg.text))
        if not recruiting:
            return ExtractionResult(kind="not_recruiting", rule_id="no_signal")
        first = _APP_SIGNAL.search(msg.body) or _APP_SIGNAL.search(msg.subject)
        src = msg.body if _APP_SIGNAL.search(msg.body) else msg.subject
        return ExtractionResult(
            kind="unclear",
            company=company,
            position=position,
            req_id=req.group("req") if req else None,
            confidence="low",
            rule_id="unclear.app_signal",
            excerpt=make_excerpt(src, first.start(), first.end()) if first else None,
        )

    confidence = "high" if company else "low"
    return ExtractionResult(
        kind=kind,
        company=company,
        position=position,
        req_id=req.group("req") if req else None,
        stated_applied_date=stated,
        confidence=confidence,
        rule_id=rule_id if not field_rule else f"{rule_id}+{field_rule}",
        excerpt=excerpt,
    )

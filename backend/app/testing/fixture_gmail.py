"""FixtureGmailClient: a synthetic Gmail used ONLY when APP_ENV=test.

Loads messages in Gmail `users.messages.get` (format=full) shape from
backend/tests/fixtures/gmail/*.json and mailbox scenarios from
backend/tests/fixtures/mailboxes/*.yaml. It mirrors the real client's semantics: epoch
`after:`/`before:` filtering on internalDate, Spam/Trash never listed, paging.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.gmail.client import (
    GmailAuthError,
    ListPage,
    MessageFull,
    MessageMeta,
    Profile,
)
from app.gmail.parse import full_from_api, meta_from_api

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
_AFTER = re.compile(r"after:(\d+)")
_BEFORE = re.compile(r"before:(\d+)")


@lru_cache
def load_messages() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in sorted((FIXTURES_DIR / "gmail").glob("*.json")):
        msg = json.loads(path.read_text())
        out[msg["id"]] = msg
    return out


@lru_cache
def load_mailbox(name: str) -> dict[str, Any]:
    path = FIXTURES_DIR / "mailboxes" / f"{name}.yaml"
    if not path.exists():
        raise KeyError(f"unknown fixture mailbox {name!r}")
    return yaml.safe_load(path.read_text())


def list_mailboxes() -> list[str]:
    return sorted(p.stem for p in (FIXTURES_DIR / "mailboxes").glob("*.yaml"))


@dataclass
class MailboxState:
    name: str
    address: str
    message_ids: list[str]
    revoked: bool = False
    page_size: int = 500
    calls: list[str] = field(default_factory=list)
    # Test hook: raise after this many list pages (simulates a crash mid-scan).
    abort_after_pages: int | None = None
    pages_served: int = 0


class SimulatedCrash(RuntimeError):
    pass


_REGISTRY: dict[uuid.UUID, MailboxState] = {}
_LOCK = threading.Lock()


def connect_mailbox(user_id: uuid.UUID, name: str) -> MailboxState:
    box = load_mailbox(name)
    state = MailboxState(
        name=name,
        address=box.get("address", f"{name}@fixture.test"),
        message_ids=list(box.get("messages", [])),
        page_size=int(box.get("page_size", 500)),
    )
    with _LOCK:
        _REGISTRY[user_id] = state
    return state


def get_state(user_id: uuid.UUID) -> MailboxState | None:
    with _LOCK:
        return _REGISTRY.get(user_id)


def drop_state(user_id: uuid.UUID) -> None:
    with _LOCK:
        _REGISTRY.pop(user_id, None)


def reset_registry() -> None:
    with _LOCK:
        _REGISTRY.clear()


class FixtureGmailClient:
    def __init__(self, state: MailboxState) -> None:
        self.state = state
        self._all = load_messages()

    def _check(self, call: str) -> None:
        self.state.calls.append(call)
        if self.state.revoked:
            raise GmailAuthError("invalid_grant")

    def get_profile(self) -> Profile:
        self._check("get_profile")
        return Profile(email_address=self.state.address)

    def list_message_ids(
        self, query: str, page_token: str | None, max_results: int = 500
    ) -> ListPage:
        self._check("list")
        if (
            self.state.abort_after_pages is not None
            and self.state.pages_served >= self.state.abort_after_pages
        ):
            raise SimulatedCrash("simulated worker crash")
        after = int(m.group(1)) * 1000 if (m := _AFTER.search(query)) else None
        before = int(m.group(1)) * 1000 if (m := _BEFORE.search(query)) else None
        matching: list[dict[str, Any]] = []
        for mid in self.state.message_ids:
            msg = self._all.get(mid)
            if msg is None:
                continue
            labels = set(msg.get("labelIds", []))
            if labels & {"SPAM", "TRASH"}:
                continue
            ts = int(msg["internalDate"])
            if after is not None and ts < after:
                continue
            if before is not None and ts >= before:
                continue
            matching.append(msg)
        # Gmail lists newest first.
        matching.sort(key=lambda m: int(m["internalDate"]), reverse=True)
        size = min(max_results, self.state.page_size)
        start = int(page_token) if page_token else 0
        page = matching[start : start + size]
        nxt = start + size
        self.state.pages_served += 1
        return ListPage(
            ids=[m["id"] for m in page],
            next_page_token=str(nxt) if nxt < len(matching) else None,
            result_size_estimate=len(matching),
        )

    def _msg(self, message_id: str) -> dict[str, Any]:
        if message_id not in self.state.message_ids or message_id not in self._all:
            raise KeyError(message_id)
        return self._all[message_id]

    def get_metadata(self, message_id: str) -> MessageMeta:
        self._check("get_metadata")
        return meta_from_api(self._msg(message_id))

    def get_full(self, message_id: str) -> MessageFull:
        self._check("get_full")
        return full_from_api(self._msg(message_id))

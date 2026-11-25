"""GmailClient protocol, data types, and errors (contracts/gmail-fixtures.md).

The scan pipeline depends only on this protocol. The real implementation is
`app.gmail.google_client.GoogleGmailClient`; `app.testing.fixture_gmail.FixtureGmailClient`
exists only for APP_ENV=test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

METADATA_HEADERS = ("From", "Subject", "Date", "List-Unsubscribe", "Reply-To")


class GmailError(Exception):
    pass


class GmailAuthError(GmailError):
    """invalid_grant / revoked / expired: the user must reconnect."""


class GmailRateLimited(GmailError):
    """429 or 403 rateLimitExceeded: retry with backoff."""


class GmailUnavailable(GmailError):
    """5xx or timeout: retry, then fail the run."""


@dataclass(frozen=True)
class Profile:
    email_address: str


@dataclass(frozen=True)
class ListPage:
    ids: list[str]
    next_page_token: str | None
    result_size_estimate: int


@dataclass
class MessageMeta:
    id: str
    thread_id: str | None
    internal_date_ms: int
    label_ids: list[str]
    snippet: str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class MessageFull:
    meta: MessageMeta
    text_plain: str = ""
    text_html: str = ""


class GmailClient(Protocol):
    def get_profile(self) -> Profile: ...

    def list_message_ids(
        self, query: str, page_token: str | None, max_results: int = 500
    ) -> ListPage: ...

    def get_metadata(self, message_id: str) -> MessageMeta: ...

    def get_full(self, message_id: str) -> MessageFull: ...

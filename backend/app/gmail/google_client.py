"""Real Gmail REST client (read-only GET requests only; research R6/R7).

Access tokens are obtained from the refresh token on demand and held only in memory. It is
safe to share one instance across the worker's fetch threads.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.auth.google import TOKEN_URL
from app.config import get_settings
from app.gmail.client import (
    METADATA_HEADERS,
    GmailAuthError,
    GmailRateLimited,
    GmailUnavailable,
    ListPage,
    MessageFull,
    MessageMeta,
    Profile,
)
from app.gmail.parse import full_from_api, meta_from_api

API = "https://gmail.googleapis.com/gmail/v1/users/me"
_RETRYABLE = (GmailRateLimited, GmailUnavailable)

_retry = retry(
    retry=retry_if_exception_type(_RETRYABLE),
    stop=stop_after_attempt(8),
    wait=wait_exponential_jitter(initial=2, max=60),
    reraise=True,
)


class RateLimiter:
    """Thread-safe pacing shared by all fetch threads.

    Gmail allows ~250 quota units per user per second; messages.list and messages.get cost
    5 units each, so ~50 requests/second is the ceiling. We stay below it.
    """

    def __init__(self, per_second: float) -> None:
        self.interval = 1.0 / per_second
        self._lock = threading.Lock()
        self._next = 0.0
        self._paused_until = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next, self._paused_until)
            self._next = slot + self.interval
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    def back_off(self, seconds: float) -> None:
        """After a rate-limit response, pause every thread, not just the one that saw it."""
        with self._lock:
            self._paused_until = max(self._paused_until, time.monotonic() + seconds)


def _google_reason(resp: httpx.Response) -> str:
    """Google's error reason/message only (never request data, tokens, or email content)."""
    try:
        err = resp.json().get("error", {})
        if isinstance(err, dict):
            reasons = [e.get("reason") for e in err.get("errors") or [] if isinstance(e, dict)]
            return f"{err.get('status', '')} {','.join(r for r in reasons if r)} {str(err.get('message', ''))[:200]}".strip()
        return str(err)[:200]
    except ValueError:
        return "non-JSON response"


class GoogleGmailClient:
    def __init__(
        self,
        refresh_token: str,
        http: httpx.Client | None = None,
        max_requests_per_second: float | None = None,
    ) -> None:
        self._refresh_token = refresh_token
        self._limiter = RateLimiter(max_requests_per_second or get_settings().GMAIL_MAX_RPS)
        self._http = http or httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))
        self._lock = threading.Lock()
        self._access_token: str | None = None
        self._expires_at = 0.0

    # -- auth ---------------------------------------------------------------
    def _token(self, force: bool = False) -> str:
        with self._lock:
            if force or not self._access_token or time.time() > self._expires_at - 60:
                self._refresh()
            assert self._access_token is not None
            return self._access_token

    def _refresh(self) -> None:
        s = get_settings()
        try:
            resp = self._http.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                    "client_id": s.GOOGLE_CLIENT_ID,
                    "client_secret": s.GOOGLE_CLIENT_SECRET,
                },
            )
        except httpx.HTTPError as exc:
            raise GmailUnavailable("token endpoint unreachable") from exc
        if resp.status_code in (400, 401):
            # invalid_grant: revoked, expired (7-day testing-mode limit), or password change.
            raise GmailAuthError("invalid_grant")
        if resp.status_code >= 500:
            raise GmailUnavailable(f"token endpoint http {resp.status_code}")
        body = resp.json()
        self._access_token = body["access_token"]
        self._expires_at = time.time() + int(body.get("expires_in", 3600))

    # -- transport ----------------------------------------------------------
    @_retry
    def _get(self, path: str, params: list[tuple[str, str]] | None = None) -> dict[str, Any]:
        for attempt in range(2):
            token = self._token(force=attempt == 1)
            self._limiter.wait()
            try:
                resp = self._http.get(
                    f"{API}{path}", params=params, headers={"Authorization": f"Bearer {token}"}
                )
            except httpx.TimeoutException as exc:
                raise GmailUnavailable("timeout") from exc
            except httpx.HTTPError as exc:
                raise GmailUnavailable(f"network error: {type(exc).__name__}") from exc
            if resp.status_code == 401 and attempt == 0:
                continue  # refresh once and retry
            try:
                return self._handle(resp)
            except GmailRateLimited:
                retry_after = resp.headers.get("Retry-After", "")
                self._limiter.back_off(float(retry_after) if retry_after.isdigit() else 5.0)
                raise
        raise GmailAuthError("unauthorized")

    @staticmethod
    def _handle(resp: httpx.Response) -> dict[str, Any]:
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429:
            raise GmailRateLimited(f"http 429: {_google_reason(resp)}")
        if resp.status_code == 403:
            reasons = {
                e.get("reason")
                for e in (resp.json().get("error", {}).get("errors") or [])
                if isinstance(e, dict)
            }
            if reasons & {"rateLimitExceeded", "userRateLimitExceeded"}:
                raise GmailRateLimited(f"http 403: {_google_reason(resp)}")
            raise GmailAuthError(f"http 403: {_google_reason(resp)}")
        if resp.status_code == 401:
            raise GmailAuthError("unauthorized")
        if resp.status_code >= 500:
            raise GmailUnavailable(f"http {resp.status_code}: {_google_reason(resp)}")
        raise GmailUnavailable(f"http {resp.status_code}: {_google_reason(resp)}")

    # -- GmailClient protocol -----------------------------------------------
    def get_profile(self) -> Profile:
        return Profile(email_address=self._get("/profile")["emailAddress"])

    def list_message_ids(
        self, query: str, page_token: str | None, max_results: int = 500
    ) -> ListPage:
        params = [("q", query), ("maxResults", str(max_results)), ("includeSpamTrash", "false")]
        if page_token:
            params.append(("pageToken", page_token))
        body = self._get("/messages", params)
        return ListPage(
            ids=[m["id"] for m in body.get("messages", []) or []],
            next_page_token=body.get("nextPageToken"),
            result_size_estimate=int(body.get("resultSizeEstimate", 0)),
        )

    def get_metadata(self, message_id: str) -> MessageMeta:
        params = [("format", "metadata")] + [("metadataHeaders", h) for h in METADATA_HEADERS]
        return meta_from_api(self._get(f"/messages/{message_id}", params))

    def get_full(self, message_id: str) -> MessageFull:
        return full_from_api(self._get(f"/messages/{message_id}", [("format", "full")]))

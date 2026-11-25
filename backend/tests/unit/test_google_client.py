"""Real Gmail client behavior with a mocked transport (no network, no real Gmail)."""

import threading
import time

import httpx
import pytest

from app.gmail.client import GmailAuthError, GmailRateLimited
from app.gmail.google_client import GoogleGmailClient, RateLimiter


def test_rate_limiter_paces_concurrent_threads():
    limiter = RateLimiter(per_second=50)
    stamps: list[float] = []
    lock = threading.Lock()

    def worker():
        for _ in range(10):
            limiter.wait()
            with lock:
                stamps.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - t0
    # 80 requests at 50/s must take at least ~1.58 s, regardless of 8 threads.
    assert elapsed >= 79 / 50 - 0.05
    stamps.sort()
    one_second = [s for s in stamps if s - stamps[0] < 1.0]
    assert len(one_second) <= 51


def _client(handler, rps=1000):
    def route(request: httpx.Request):
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "at", "expires_in": 3600})
        return handler(request)

    return GoogleGmailClient("refresh", http=httpx.Client(transport=httpx.MockTransport(route)),
                             max_requests_per_second=rps)


def test_rate_limit_403_is_retried_then_succeeds(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED", "message": "User-rate limit exceeded",
                                                       "errors": [{"reason": "userRateLimitExceeded"}]}})
        assert request.method == "GET"
        return httpx.Response(200, json={"emailAddress": "me@example.test"})

    c = _client(handler)
    c._get.retry.sleep = lambda s: None  # type: ignore[attr-defined]
    assert c.get_profile().email_address == "me@example.test"
    assert calls["n"] == 3


def test_persistent_rate_limit_reports_google_reason(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)

    def handler(request):
        return httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED", "message": "Too many requests",
                                                   "errors": [{"reason": "rateLimitExceeded"}]}})

    c = _client(handler)
    c._get.retry.sleep = lambda s: None  # type: ignore[attr-defined]
    with pytest.raises(GmailRateLimited, match="429.*rateLimitExceeded"):
        c.get_profile()


def test_api_not_enabled_is_auth_error_with_reason():
    def handler(request):
        return httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED", "message": "Gmail API has not been used",
                                                   "errors": [{"reason": "accessNotConfigured"}]}})

    with pytest.raises(GmailAuthError, match="accessNotConfigured"):
        _client(handler).get_profile()

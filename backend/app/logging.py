"""JSON logging with a redaction filter (research R12, Constitution IV).

Secrets, tokens, and email content must never reach log output. The filter drops sensitive
keys from structured `extra` fields and masks token-looking strings in messages.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime

SENSITIVE_KEYS = frozenset(
    {
        "body",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "code",
        "id_token",
        "excerpt",
        "snippet",
        "client_secret",
        "password",
    }
)
_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9._\-~+/]+=*", re.IGNORECASE),
    re.compile(r"ya29\.[A-Za-z0-9._\-]+"),
    re.compile(r"1//[A-Za-z0-9._\-]{20,}"),  # Google refresh-token shape
]
_RESERVED = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}
REDACTED = "[REDACTED]"


def redact_text(value: str) -> str:
    for pat in _PATTERNS:
        value = pat.sub(REDACTED, value)
    return value


def _redact_value(key: str, value: object) -> object:
    if key.lower() in SENSITIVE_KEYS:
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: _redact_value(str(k), v) for k, v in value.items()}
    return value


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key in list(vars(record).keys()):
            if key in _RESERVED:
                continue
            setattr(record, key, _redact_value(key, getattr(record, key)))
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover - malformed format args
            msg = str(record.msg)
        record.msg = redact_text(msg)
        record.args = None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpcore", "authlib", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # Uvicorn access logs include query strings (OAuth `code`); route them through the filter.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers[:] = []
        lg.propagate = True

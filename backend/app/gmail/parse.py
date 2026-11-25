"""Decode Gmail API message payloads into text (in memory only; nothing is persisted)."""

from __future__ import annotations

import base64
import re
import warnings
from typing import Any

from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning

from app.gmail.client import MessageFull, MessageMeta

_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n\s*\n+")


def b64url_decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode()).decode("utf-8", errors="replace")


def headers_dict(payload: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in payload.get("headers", []) or []:
        name = h.get("name", "")
        if name and name not in out:
            out[name] = h.get("value", "")
    return out


def _walk(part: dict[str, Any], plain: list[str], html: list[str]) -> None:
    mime = part.get("mimeType", "")
    data = (part.get("body") or {}).get("data")
    if data and mime == "text/plain":
        plain.append(b64url_decode(data))
    elif data and mime == "text/html":
        html.append(b64url_decode(data))
    for sub in part.get("parts", []) or []:
        _walk(sub, plain, html)


def meta_from_api(msg: dict[str, Any]) -> MessageMeta:
    payload = msg.get("payload") or {}
    return MessageMeta(
        id=msg["id"],
        thread_id=msg.get("threadId"),
        internal_date_ms=int(msg.get("internalDate", 0)),
        label_ids=list(msg.get("labelIds", []) or []),
        snippet=msg.get("snippet", "") or "",
        headers=headers_dict(payload),
    )


def full_from_api(msg: dict[str, Any]) -> MessageFull:
    plain: list[str] = []
    html: list[str] = []
    _walk(msg.get("payload") or {}, plain, html)
    return MessageFull(meta=meta_from_api(msg), text_plain="\n".join(plain), text_html="\n".join(html))


def html_to_text(html: str) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MarkupResemblesLocatorWarning)
        soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head", "title"]):
        tag.decompose()
    for br in soup.find_all(["br", "p", "div", "tr", "li", "h1", "h2", "h3"]):
        br.append("\n")
    return soup.get_text()


def normalize_text(text: str) -> str:
    text = text.replace(" ", " ")
    text = _WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _NL.sub("\n\n", text).strip()


def body_text(full: MessageFull) -> str:
    """Prefer text/plain; fall back to HTML converted to text."""
    if full.text_plain.strip():
        return normalize_text(full.text_plain)
    if full.text_html.strip():
        return normalize_text(html_to_text(full.text_html))
    return ""

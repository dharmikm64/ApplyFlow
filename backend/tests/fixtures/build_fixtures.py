"""Generate Gmail-API-shaped fixture JSON from tests/fixtures/sources/messages.yaml.

Usage: python tests/fixtures/build_fixtures.py
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "sources" / "messages.yaml"
OUT = HERE / "gmail"


def b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def build(src: dict) -> dict:
    raw = src["date"]
    dt = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    headers = [
        {"name": "From", "value": src["from"]},
        {"name": "To", "value": "Jordan Candidate <jordan@candidate.test>"},
        {"name": "Subject", "value": src["subject"]},
        {"name": "Date", "value": format_datetime(dt)},
    ]
    if src.get("unsubscribe"):
        headers.append({"name": "List-Unsubscribe", "value": "<mailto:unsubscribe@list.example>"})
    parts = [{"mimeType": "text/plain", "body": {"data": b64(src["body"])}}]
    if src.get("html"):
        parts.append({"mimeType": "text/html", "body": {"data": b64(src["html"])}})
    snippet = " ".join(src["body"].split())[:160]
    return {
        "id": src["id"],
        "threadId": src["thread"],
        "internalDate": str(int(dt.timestamp() * 1000)),
        "labelIds": src.get("labels", ["INBOX"]),
        "snippet": snippet,
        "payload": {"mimeType": "multipart/alternative", "headers": headers, "parts": parts},
    }


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    messages = yaml.safe_load(SOURCE.read_text())
    ids = set()
    for src in messages:
        assert src["id"] not in ids, f"duplicate id {src['id']}"
        ids.add(src["id"])
        (OUT / f"{src['id']}.json").write_text(json.dumps(build(src), indent=2) + "\n")
    print(f"wrote {len(messages)} fixtures to {OUT}")


if __name__ == "__main__":
    main()

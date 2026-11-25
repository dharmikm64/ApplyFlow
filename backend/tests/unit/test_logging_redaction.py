import json
import logging

from app.logging import REDACTED, JsonFormatter, RedactionFilter


def _render(msg: str, *args, **extra) -> dict:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, None)
    for k, v in extra.items():
        setattr(record, k, v)
    RedactionFilter().filter(record)
    return json.loads(JsonFormatter().format(record))


def test_sensitive_extra_keys_are_dropped():
    out = _render(
        "x",
        refresh_token="1//abc",
        access_token="ya29.secret",
        body="Dear candidate...",
        excerpt="We regret",
        code="4/0Abc",
        id_token="eyJ",
        authorization="Bearer abc",
    )
    for key in ("refresh_token", "access_token", "body", "excerpt", "code", "id_token", "authorization"):
        assert out[key] == REDACTED


def test_token_patterns_in_messages_are_masked():
    out = _render("calling with Bearer ya29.a0AfH6SMBxyz and %s", "ya29.another-token")
    assert "ya29." not in out["msg"]
    assert "Bearer ya29" not in out["msg"]
    assert REDACTED in out["msg"]


def test_refresh_token_shape_is_masked():
    out = _render("token 1//0gABCDEFGHIJKLMNOPQRSTUVWXYZ123456 leaked")
    assert "1//0g" not in out["msg"]


def test_nested_dicts_are_redacted():
    out = _render("x", payload={"refresh_token": "1//x", "ok": "fine"})
    assert out["payload"] == {"refresh_token": REDACTED, "ok": "fine"}

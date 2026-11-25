"""Test-only routes and FixtureGmailClient must never exist outside APP_ENV=test."""

import subprocess
import sys
from pathlib import Path

import pytest

from app.config import Settings

BACKEND = Path(__file__).resolve().parents[2]

PROBE = """
import os
os.environ['APP_ENV'] = {env!r}
os.environ['WORKER_MODE'] = 'off'
os.environ['SESSION_SECRET'] = 'probe-secret-value-123'
os.environ['TOKEN_ENCRYPTION_KEYS'] = 'x'
from app.main import create_app
app = create_app()
paths = {{getattr(r, 'path', '') for r in app.routes}}
assert not any(p.startswith('/test') for p in paths), paths
from app.gmail import get_gmail_client
from app.models import GmailConnection
import app.gmail.google_client as gc
conn = GmailConnection(user_id=None, status='connected', refresh_token_ciphertext=b'x')
import app.auth.crypto as crypto
crypto.decrypt = lambda b: 'refresh'
client = get_gmail_client(None, conn)
assert type(client).__name__ == 'GoogleGmailClient', type(client)
print('ok')
"""


@pytest.mark.parametrize("env", ["development", "production"])
def test_test_routes_absent_outside_test_mode(env):
    result = subprocess.run(
        [sys.executable, "-c", PROBE.format(env=env)],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_test_mode_requires_test_database():
    s = Settings(APP_ENV="test", TEST_DATABASE_URL="postgresql+psycopg://localhost/applyflow")
    with pytest.raises(RuntimeError, match="_test"):
        s.validate_runtime()


def test_test_mode_accepts_test_database():
    Settings(
        APP_ENV="test", TEST_DATABASE_URL="postgresql+psycopg://localhost/applyflow_test"
    ).validate_runtime()

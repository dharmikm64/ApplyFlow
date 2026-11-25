"""Gmail client provider.

Returns the synthetic FixtureGmailClient only when APP_ENV=test; otherwise the real
GoogleGmailClient built from the user's encrypted refresh token.
"""

from __future__ import annotations

from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.gmail.client import GmailAuthError, GmailClient
from app.models import GmailConnection


def get_gmail_client(db: DbSession, conn: GmailConnection) -> GmailClient:
    if conn.status != "connected" or conn.refresh_token_ciphertext is None:
        raise GmailAuthError("not_connected")
    if get_settings().APP_ENV == "test":
        from app.testing import fixture_gmail

        state = fixture_gmail.get_state(conn.user_id)
        if state is None:
            raise GmailAuthError("fixture mailbox not connected")
        return fixture_gmail.FixtureGmailClient(state)

    from app.auth import crypto
    from app.gmail.google_client import GoogleGmailClient

    return GoogleGmailClient(refresh_token=crypto.decrypt(conn.refresh_token_ciphertext))

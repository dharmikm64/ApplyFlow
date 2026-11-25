"""Authlib OAuth registrations for Google (research R2).

Two separate registrations on the same Google OAuth client keep app sign-in (OIDC) and
Gmail authorization (gmail.readonly) as separate grants.
"""

from __future__ import annotations

from functools import lru_cache

from authlib.integrations.starlette_client import OAuth

from app.config import get_settings

GOOGLE_DISCOVERY = "https://accounts.google.com/.well-known/openid-configuration"
GMAIL_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
TOKEN_URL = "https://oauth2.googleapis.com/token"


@lru_cache
def get_oauth() -> OAuth:
    s = get_settings()
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=s.GOOGLE_CLIENT_ID,
        client_secret=s.GOOGLE_CLIENT_SECRET,
        server_metadata_url=GOOGLE_DISCOVERY,
        client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
    )
    oauth.register(
        name="google_gmail",
        client_id=s.GOOGLE_CLIENT_ID,
        client_secret=s.GOOGLE_CLIENT_SECRET,
        server_metadata_url=GOOGLE_DISCOVERY,
        client_kwargs={"scope": GMAIL_READONLY, "code_challenge_method": "S256"},
    )
    return oauth


def redirect_uri(path: str) -> str:
    return get_settings().APP_BASE_URL.rstrip("/") + path

"""Encryption of stored Gmail refresh tokens (research R4).

Keys come from TOKEN_ENCRYPTION_KEYS (environment), never from the database. MultiFernet
encrypts with the first key and decrypts with any, which allows key rotation.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, MultiFernet

from app.config import get_settings


def _fernet() -> MultiFernet:
    keys = get_settings().TOKEN_ENCRYPTION_KEYS
    if not keys:
        raise RuntimeError("TOKEN_ENCRYPTION_KEYS is not configured")
    return MultiFernet([Fernet(k.encode()) for k in keys])


def encrypt(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode())


def decrypt(ciphertext: bytes) -> str:
    return _fernet().decrypt(bytes(ciphertext)).decode()

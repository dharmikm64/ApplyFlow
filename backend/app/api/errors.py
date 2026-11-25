"""Uniform API errors: `{"error": "<code>", "message": "<user-safe text>"}`."""

from __future__ import annotations


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str = "") -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message or code.replace("_", " ").capitalize()


def not_found() -> ApiError:
    # Identical for "doesn't exist" and "belongs to someone else" (FR-040).
    return ApiError(404, "not_found", "Not found.")


def unauthenticated() -> ApiError:
    return ApiError(401, "unauthenticated", "Please sign in.")

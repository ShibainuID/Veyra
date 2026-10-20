"""Opaque bearer tokens for seeded demo users. Only the SHA-256 of a token is stored."""

import hashlib
import secrets


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

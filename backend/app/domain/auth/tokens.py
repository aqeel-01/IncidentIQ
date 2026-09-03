"""JWT access-token helpers."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import Settings


class TokenError(ValueError):
    """Raised when a token cannot be created or decoded."""


def _signing_key(settings: Settings) -> str:
    raw = (settings.jwt_secret_key or "").strip()
    if raw:
        return raw
    if settings.is_production:
        msg = "JWT_SECRET_KEY is required in production"
        raise TokenError(msg)
    # Deterministic development key so local tokens survive process restarts.
    return hashlib.sha256(b"incidentiq-dev-jwt-secret").hexdigest()


def create_access_token(
    *,
    settings: Settings,
    subject: str,
    claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT access token for ``subject``."""

    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
        "type": "access",
    }
    if claims:
        payload.update(claims)
    return jwt.encode(
        payload,
        _signing_key(settings),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(*, settings: Settings, token: str) -> dict[str, Any]:
    """Decode and validate an access token. Raises :class:`TokenError` on failure."""

    try:
        payload = jwt.decode(
            token,
            _signing_key(settings),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        msg = "invalid or expired access token"
        raise TokenError(msg) from exc

    if payload.get("type") != "access":
        msg = "invalid access token type"
        raise TokenError(msg)
    if not payload.get("sub"):
        msg = "access token missing subject"
        raise TokenError(msg)
    return payload

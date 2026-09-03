"""Encrypt and decrypt connector credentials at rest."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings


class ConnectorCredentialError(ValueError):
    """Raised when connector credentials cannot be encrypted or decrypted."""


def _fernet_from_settings(settings: Settings) -> Fernet:
    raw = (settings.connector_secret_key or "").strip()
    if raw:
        try:
            return Fernet(raw.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            msg = "CONNECTOR_SECRET_KEY is not a valid Fernet key"
            raise ConnectorCredentialError(msg) from exc

    if settings.is_production:
        msg = "CONNECTOR_SECRET_KEY is required in production"
        raise ConnectorCredentialError(msg)

    # Deterministic development key so local data remains readable across restarts.
    digest = hashlib.sha256(b"incidentiq-dev-connector-secret").digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_credentials(settings: Settings, credentials: dict[str, Any]) -> str | None:
    """Encrypt a credentials mapping. Empty mappings become ``None``."""

    cleaned = {
        key: value
        for key, value in credentials.items()
        if value is not None and value != ""
    }
    if not cleaned:
        return None
    token = _fernet_from_settings(settings).encrypt(
        json.dumps(cleaned, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    return token.decode("utf-8")


def decrypt_credentials(
    settings: Settings,
    ciphertext: str | None,
) -> dict[str, Any]:
    """Decrypt stored credentials. Missing ciphertext yields an empty mapping."""

    if not ciphertext:
        return {}
    try:
        payload = _fernet_from_settings(settings).decrypt(ciphertext.encode("utf-8"))
    except InvalidToken as exc:
        msg = "stored connector credentials could not be decrypted"
        raise ConnectorCredentialError(msg) from exc
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        msg = "stored connector credentials are malformed"
        raise ConnectorCredentialError(msg)
    return data

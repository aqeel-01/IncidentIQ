"""Password hashing helpers."""

from __future__ import annotations

import bcrypt

# Dummy bcrypt hash used only to keep verification timing similar when a user
# does not exist. Never used as a real password store.
_DUMMY_HASH = bcrypt.hashpw(b"incidentiq-timing-dummy", bcrypt.gensalt()).decode(
    "utf-8"
)


def hash_password(password: str) -> str:
    """Return a bcrypt hash for ``password``."""

    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Return True when ``password`` matches ``hashed_password``."""

    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def verify_password_or_dummy(password: str, hashed_password: str | None) -> bool:
    """Verify ``password``, using a dummy hash when the account is missing."""

    if hashed_password is None:
        verify_password(password, _DUMMY_HASH)
        return False
    return verify_password(password, hashed_password)

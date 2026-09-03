"""Authentication and authorization domain services."""

from __future__ import annotations

from app.domain.auth.passwords import (
    hash_password,
    verify_password,
    verify_password_or_dummy,
)
from app.domain.auth.roles import ROLE_RANK, role_satisfies
from app.domain.auth.service import (
    AuthenticationError,
    AuthorizationError,
    AuthService,
    AuthValidationError,
    BootstrapResult,
    MembershipView,
    TokenPair,
    UserProfile,
)
from app.domain.auth.tokens import create_access_token, decode_access_token

__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "AuthService",
    "AuthValidationError",
    "BootstrapResult",
    "MembershipView",
    "ROLE_RANK",
    "TokenPair",
    "UserProfile",
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "role_satisfies",
    "verify_password",
    "verify_password_or_dummy",
]

"""Password hashing (Argon2id) and JWT issuance/verification.

- Passwords are hashed with Argon2id (via argon2-cffi). Plaintext passwords are
  never stored or logged.
- Two independent signing secrets are used for access vs refresh tokens.
- Refresh tokens carry a rotating ``jti`` so a rotated/blacklisted token can be
  invalidated server-side (see :mod:`app.services.auth_service`).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

_ph = PasswordHasher()

TokenType = Literal["access", "refresh"]


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _ph.check_needs_rehash(password_hash)
    except (InvalidHashError, ValueError):
        return True


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #
def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _secret_for(token_type: TokenType) -> str:
    return settings.jwt_secret if token_type == "access" else settings.jwt_refresh_secret


def create_token(
    *,
    subject: str,
    token_type: TokenType,
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    extra_claims: dict[str, Any] | None = None,
    jti: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return ``(encoded_jwt, claims)``."""
    issued = _now()
    if token_type == "access":
        expires = issued + timedelta(minutes=settings.access_token_ttl_minutes)
    else:
        expires = issued + timedelta(days=settings.refresh_token_ttl_days)

    claims: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iss": settings.jwt_issuer,
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": jti or str(uuid.uuid4()),
    }
    if roles is not None:
        claims["roles"] = roles
    if permissions is not None:
        claims["permissions"] = permissions
    if extra_claims:
        claims.update(extra_claims)

    encoded = jwt.encode(claims, _secret_for(token_type), algorithm=settings.jwt_algorithm)
    return encoded, claims


def decode_token(token: str, *, token_type: TokenType) -> dict[str, Any]:
    """Decode and validate a token. Raises ``jwt.PyJWTError`` on failure."""
    claims = jwt.decode(
        token,
        _secret_for(token_type),
        algorithms=[settings.jwt_algorithm],
        issuer=settings.jwt_issuer,
        options={"require": ["exp", "iat", "sub", "type"]},
    )
    if claims.get("type") != token_type:
        raise jwt.InvalidTokenError("Unexpected token type")
    return claims

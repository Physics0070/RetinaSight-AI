"""Authentication contracts."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.config import settings


def validate_password_policy(value: str) -> str:
    """Length policy is configuration-driven (``RS_PASSWORD_MIN_LENGTH``)."""
    if len(value) < settings.password_min_length:
        raise ValueError(
            f"Password must be at least {settings.password_min_length} characters."
        )
    return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)
    # Optional: lets the offline device tie a session to a known device id.
    device_id: str | None = Field(default=None, max_length=64)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access-token lifetime in seconds.")


class AuthenticatedUser(BaseModel):
    """Identity envelope returned to the client after login/refresh.

    ``permissions`` is advisory for UI rendering only — the backend re-checks
    every permission on every request.
    """

    id: uuid.UUID
    email: EmailStr
    full_name: str
    status: str
    roles: list[str]
    permissions: list[str]
    clinic_id: uuid.UUID | None = None
    patient_id: uuid.UUID | None = None


class LoginResponse(BaseModel):
    tokens: TokenPair
    user: AuthenticatedUser


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _policy(cls, v: str) -> str:
        return validate_password_policy(v)

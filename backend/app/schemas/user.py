"""User, role and permission contracts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.domain.enums import RoleName, UserStatus
from app.schemas.auth import validate_password_policy
from app.schemas.common import ORMModel


class PermissionRead(ORMModel):
    id: uuid.UUID
    code: str
    description: str
    category: str


class RoleRead(ORMModel):
    id: uuid.UUID
    name: str
    display_name: str
    description: str


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str
    role: RoleName
    phone: str | None = Field(default=None, max_length=32)
    # Staff (doctor / health worker) placement.
    clinic_id: uuid.UUID | None = None
    specialty: str | None = Field(default=None, max_length=128)
    license_number: str | None = Field(default=None, max_length=64)
    staff_code: str | None = Field(default=None, max_length=64)

    @field_validator("password")
    @classmethod
    def _policy(cls, v: str) -> str:
        return validate_password_policy(v)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    status: UserStatus | None = None


class UserRead(ORMModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    phone: str | None
    status: str
    last_active_at: datetime | None
    created_at: datetime


class UserDetail(UserRead):
    roles: list[str] = []
    permissions: list[str] = []
    clinic_id: uuid.UUID | None = None
    clinic_name: str | None = None


class RoleAssignRequest(BaseModel):
    role: RoleName


class UserStatusUpdateRequest(BaseModel):
    status: UserStatus
    reason: str | None = Field(default=None, max_length=255)

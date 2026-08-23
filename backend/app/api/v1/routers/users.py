"""User administration endpoints (admin-scoped)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import Access, DbSession, require_permission
from app.domain.enums import Permission, RoleName, UserStatus
from app.schemas.common import Page, PaginationParams
from app.schemas.user import (
    RoleAssignRequest,
    UserCreate,
    UserDetail,
    UserStatusUpdateRequest,
    UserUpdate,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])

ManageUsers = Annotated[Access, Depends(require_permission(Permission.USER_MANAGE))]


@router.get("", response_model=Page[UserDetail])
def list_users(
    access: ManageUsers,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    query: str | None = Query(default=None, description="Search name or email."),
    role: RoleName | None = Query(default=None),
    user_status: UserStatus | None = Query(default=None, alias="status"),
    sort: str = Query(default="created_at"),
    descending: bool = Query(default=True),
) -> Page[UserDetail]:
    return UserService(db).search(
        params=PaginationParams(page=page, page_size=page_size),
        query=query,
        role=role.value if role else None,
        status=user_status.value if user_status else None,
        sort=sort,
        descending=descending,
    )


@router.post("", response_model=UserDetail, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, access: ManageUsers, db: DbSession) -> UserDetail:
    return UserService(db).create_user(payload, actor=access.user)


@router.get("/{user_id}", response_model=UserDetail)
def get_user(user_id: uuid.UUID, access: ManageUsers, db: DbSession) -> UserDetail:
    return UserService(db).get_detail(user_id)


@router.patch("/{user_id}", response_model=UserDetail)
def update_user(
    user_id: uuid.UUID, payload: UserUpdate, access: ManageUsers, db: DbSession
) -> UserDetail:
    return UserService(db).update_user(user_id, payload, actor=access.user)


@router.post("/{user_id}/status", response_model=UserDetail)
def set_user_status(
    user_id: uuid.UUID,
    payload: UserStatusUpdateRequest,
    access: ManageUsers,
    db: DbSession,
) -> UserDetail:
    return UserService(db).set_status(
        user_id, payload.status, actor=access.user, reason=payload.reason
    )


@router.post("/{user_id}/role", response_model=UserDetail)
def change_user_role(
    user_id: uuid.UUID, payload: RoleAssignRequest, access: ManageUsers, db: DbSession
) -> UserDetail:
    return UserService(db).change_role(user_id, payload.role, actor=access.user)

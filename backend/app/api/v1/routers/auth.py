"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.api.deps import Access, CurrentUser, DbSession, client_ip
from app.schemas.auth import (
    AuthenticatedUser,
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    RefreshRequest,
)
from app.schemas.common import MessageResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: DbSession) -> LoginResponse:
    """Exchange credentials for an access + refresh token pair."""
    return AuthService(db).login(
        email=payload.email,
        password=payload.password,
        ip_address=client_ip(request),
    )


@router.post("/refresh", response_model=LoginResponse)
def refresh(payload: RefreshRequest, request: Request, db: DbSession) -> LoginResponse:
    """Rotate a refresh token. The presented token is revoked on success."""
    return AuthService(db).refresh(
        refresh_token=payload.refresh_token,
        ip_address=client_ip(request),
    )


@router.post("/logout", response_model=MessageResponse)
def logout(
    db: DbSession,
    user: CurrentUser,
    payload: RefreshRequest | None = None,
) -> MessageResponse:
    """Revoke the presented refresh token, or all of this user's tokens."""
    revoked = AuthService(db).logout(
        user=user, refresh_token=payload.refresh_token if payload else None
    )
    return MessageResponse(message=f"Signed out. {revoked} session(s) ended.")


@router.get("/me", response_model=AuthenticatedUser)
def me(access: Access) -> AuthenticatedUser:
    """Resolve the caller's identity, roles and effective permissions."""
    return AuthService(access.db).build_identity(access.user)


@router.post(
    "/change-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
def change_password(
    payload: PasswordChangeRequest, db: DbSession, user: CurrentUser
) -> MessageResponse:
    AuthService(db).change_password(
        user=user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return MessageResponse(message="Password updated. Please sign in again on other devices.")

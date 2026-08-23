"""FastAPI dependencies: authentication, authorization and request context.

**Authorization is enforced here, on the server.** Frontend route guards are a
usability affordance only — every protected endpoint declares its required
permission through :func:`require_permission`, and the permission set is
re-resolved from the database on each request (never trusted from the token).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Annotated, Callable

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import (
    AccountInactiveError,
    InvalidTokenError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.security import decode_token
from app.db.session import SessionLocal
from app.domain.enums import AuditAction, AuditResult, Permission, RoleName, UserStatus
from app.models.identity import User
from app.models.patient import Patient
from app.repositories.user_repository import UserRepository
from app.services.audit_service import AuditService
from app.services.rbac_service import RBACService

# auto_error=False so a missing header raises our own typed error envelope.
_bearer = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


def client_ip(request: Request) -> str | None:
    """Best-effort client IP (Render terminates TLS and sets X-Forwarded-For)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> User:
    if credentials is None or not credentials.credentials:
        raise InvalidTokenError("Authentication is required.")

    try:
        claims = decode_token(credentials.credentials, token_type="access")
    except jwt.PyJWTError as exc:
        raise InvalidTokenError() from exc

    try:
        user_id = uuid.UUID(str(claims.get("sub")))
    except (ValueError, TypeError) as exc:
        raise InvalidTokenError() from exc

    user = db.get(User, user_id)
    if user is None:
        raise InvalidTokenError()
    if user.status != UserStatus.ACTIVE.value:
        raise AccountInactiveError()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


class AccessContext:
    """Resolved identity + authorization helpers for a single request."""

    def __init__(self, db: Session, user: User, request: Request) -> None:
        self.db = db
        self.user = user
        self.request = request
        self.rbac = RBACService(db)
        self.audit = AuditService(db)
        self._permissions: set[str] | None = None
        self._roles: set[str] | None = None

    @property
    def permissions(self) -> set[str]:
        if self._permissions is None:
            self._permissions = self.rbac.effective_permissions(self.user.id)
        return self._permissions

    @property
    def roles(self) -> set[str]:
        if self._roles is None:
            self._roles = self.rbac.role_names(self.user.id)
        return self._roles

    @property
    def primary_role(self) -> str | None:
        for role in (RoleName.ADMIN, RoleName.DOCTOR, RoleName.HEALTH_WORKER, RoleName.PATIENT):
            if role.value in self.roles:
                return role.value
        return next(iter(self.roles), None)

    def has(self, permission: Permission | str) -> bool:
        return str(permission) in self.permissions

    def has_role(self, role: RoleName | str) -> bool:
        return str(role) in self.roles

    def deny(self, *, resource_type: str, resource_id: str | uuid.UUID | None = None) -> None:
        """Record the denial, then raise."""
        self.audit.record(
            action=AuditAction.ACCESS_DENIED,
            result=AuditResult.DENIED,
            actor=self.user,
            actor_role=self.primary_role,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=client_ip(self.request),
            context={"path": self.request.url.path, "method": self.request.method},
        )
        self.db.commit()
        raise PermissionDeniedError()

    def require(self, permission: Permission | str, *, resource_type: str = "endpoint") -> None:
        if not self.has(permission):
            self.deny(resource_type=resource_type, resource_id=str(permission))

    def user_clinic_id(self) -> uuid.UUID | None:
        """The clinic this staff member belongs to, if any."""
        from app.models.organization import Doctor, HealthWorker

        for model in (HealthWorker, Doctor):
            profile = (
                self.db.query(model).filter(model.user_id == self.user.id).one_or_none()
            )
            if profile is not None:
                return profile.clinic_id
        return None

    # ---------------------------------------------------------------- #
    # Patient-record isolation
    # ---------------------------------------------------------------- #
    def resolve_own_patient(self) -> Patient:
        """The patient record linked to the signed-in portal account."""
        patient = (
            self.db.query(Patient).filter(Patient.portal_user_id == self.user.id).one_or_none()
        )
        if patient is None:
            raise NotFoundError("No patient record is linked to this account.")
        return patient

    def authorize_patient(self, patient_id: uuid.UUID) -> Patient:
        """Return the patient only if this user may access that record.

        Staff need ``PATIENT_VIEW``; a patient may only reach their own record.
        Any other attempt is audited as a denial.
        """
        patient = self.db.get(Patient, patient_id)
        if patient is None:
            raise NotFoundError("Patient not found.")

        if self.has(Permission.PATIENT_VIEW):
            return patient

        if self.has(Permission.PATIENT_VIEW_SELF) and patient.portal_user_id == self.user.id:
            return patient

        self.deny(resource_type="patient", resource_id=patient_id)
        raise PermissionDeniedError()  # pragma: no cover - deny() always raises


def get_access_context(request: Request, db: DbSession, user: CurrentUser) -> AccessContext:
    return AccessContext(db, user, request)


Access = Annotated[AccessContext, Depends(get_access_context)]


def require_permission(permission: Permission | str) -> Callable[..., AccessContext]:
    """Route guard factory: ``dependencies=[Depends(require_permission(...))]``
    or inject the returned context to reuse it in the handler."""

    def _guard(access: Access) -> AccessContext:
        access.require(permission)
        return access

    return _guard


def require_any_permission(*permissions: Permission | str) -> Callable[..., AccessContext]:
    def _guard(access: Access) -> AccessContext:
        if not any(access.has(p) for p in permissions):
            access.deny(resource_type="endpoint", resource_id=",".join(str(p) for p in permissions))
        return access

    return _guard


def require_role(*roles: RoleName | str) -> Callable[..., AccessContext]:
    def _guard(access: Access) -> AccessContext:
        if not any(access.has_role(r) for r in roles):
            access.deny(resource_type="role", resource_id=",".join(str(r) for r in roles))
        return access

    return _guard

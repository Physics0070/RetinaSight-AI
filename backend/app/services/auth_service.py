"""Authentication: login, refresh-token rotation, logout, password change.

Refresh-token rotation
----------------------
Every refresh issues a NEW refresh token and marks the presented one as
revoked + ``replaced_by_jti``. If a already-revoked token is presented again
(replay / theft), the entire token family for that user is revoked.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import (
    AccountInactiveError,
    AuthenticationError,
    InvalidTokenError,
)
from app.core.logging import get_logger
from app.core.rate_limit import login_key, login_limiter
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.domain.enums import AuditAction, AuditResult, RoleName, UserStatus
from app.models.identity import RefreshToken, User
from app.repositories.user_repository import RefreshTokenRepository, UserRepository
from app.schemas.auth import AuthenticatedUser, LoginResponse, TokenPair
from app.services.audit_service import AuditService

logger = get_logger(__name__)


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.refresh_tokens = RefreshTokenRepository(db)
        self.audit = AuditService(db)
        self._last_refresh_jti: str | None = None

    # ------------------------------------------------------------------ #
    # Login
    # ------------------------------------------------------------------ #
    def login(
        self, *, email: str, password: str, ip_address: str | None = None
    ) -> LoginResponse:
        # Raise the cost of online password guessing. Keyed on IP + email so an
        # attacker cannot lock a legitimate user out from a different address.
        rate_key = login_key(ip_address, email)
        login_limiter.check(rate_key)

        user = self.users.get_by_email(email)

        # Uniform failure: never reveal whether the email exists.
        if user is None or not verify_password(password, user.password_hash):
            self.audit.record(
                action=AuditAction.LOGIN_FAILED,
                result=AuditResult.FAILURE,
                actor_email=email,
                ip_address=ip_address,
                context={"reason": "invalid_credentials"},
            )
            self.db.commit()
            raise AuthenticationError()

        if user.status != UserStatus.ACTIVE.value:
            self.audit.record(
                action=AuditAction.LOGIN_FAILED,
                result=AuditResult.DENIED,
                actor=user,
                ip_address=ip_address,
                context={"reason": "account_not_active", "status": user.status},
            )
            self.db.commit()
            raise AccountInactiveError()

        # Transparently upgrade the hash if Argon2 parameters have changed.
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        # A genuine sign-in clears the counter, so a user who mistyped twice is
        # not penalised for the rest of the window.
        login_limiter.reset(rate_key)

        self.users.touch_last_active(user)
        tokens = self._issue_token_pair(user)

        self.audit.record(
            action=AuditAction.LOGIN,
            result=AuditResult.SUCCESS,
            actor=user,
            actor_role=",".join(self.users.role_names(user.id)),
            ip_address=ip_address,
        )
        self.db.commit()
        return LoginResponse(tokens=tokens, user=self.build_identity(user))

    # ------------------------------------------------------------------ #
    # Refresh (with rotation + replay detection)
    # ------------------------------------------------------------------ #
    def refresh(self, *, refresh_token: str, ip_address: str | None = None) -> LoginResponse:
        try:
            claims = decode_token(refresh_token, token_type="refresh")
        except jwt.PyJWTError as exc:
            raise InvalidTokenError() from exc

        jti = claims.get("jti")
        stored = self.refresh_tokens.get_by_jti(jti) if jti else None
        if stored is None:
            raise InvalidTokenError()

        if stored.revoked:
            # Replay of a rotated token → assume compromise, revoke the family.
            revoked = self.refresh_tokens.revoke_all_for_user(stored.user_id)
            self.audit.record(
                action=AuditAction.LOGIN_FAILED,
                result=AuditResult.DENIED,
                ip_address=ip_address,
                resource_type="refresh_token",
                resource_id=stored.user_id,
                context={"reason": "refresh_token_replay", "revoked_count": revoked},
            )
            self.db.commit()
            logger.warning("Refresh-token replay detected; revoked %s tokens", revoked)
            raise InvalidTokenError()

        if stored.expires_at.replace(tzinfo=timezone.utc) < datetime.now(tz=timezone.utc):
            raise InvalidTokenError()

        user = self.users.get(stored.user_id)
        if user is None:
            raise InvalidTokenError()
        if user.status != UserStatus.ACTIVE.value:
            raise AccountInactiveError()

        new_tokens = self._issue_token_pair(user)
        stored.revoked = True
        stored.replaced_by_jti = self._last_refresh_jti
        self.db.flush()

        self.audit.record(
            action=AuditAction.TOKEN_REFRESHED,
            result=AuditResult.SUCCESS,
            actor=user,
            ip_address=ip_address,
        )
        self.db.commit()
        return LoginResponse(tokens=new_tokens, user=self.build_identity(user))

    # ------------------------------------------------------------------ #
    # Logout
    # ------------------------------------------------------------------ #
    def logout(self, *, user: User, refresh_token: str | None = None) -> int:
        """Revoke the presented token, or every token for the user."""
        revoked = 0
        if refresh_token:
            try:
                claims = decode_token(refresh_token, token_type="refresh")
                stored = self.refresh_tokens.get_by_jti(claims.get("jti", ""))
                if stored and stored.user_id == user.id and not stored.revoked:
                    stored.revoked = True
                    revoked = 1
            except jwt.PyJWTError:
                revoked = 0
        else:
            revoked = self.refresh_tokens.revoke_all_for_user(user.id)

        self.audit.record(action=AuditAction.LOGOUT, actor=user, context={"revoked": revoked})
        self.db.commit()
        return revoked

    # ------------------------------------------------------------------ #
    # Password change
    # ------------------------------------------------------------------ #
    def change_password(self, *, user: User, current_password: str, new_password: str) -> None:
        if not verify_password(current_password, user.password_hash):
            raise AuthenticationError("Your current password is incorrect.")
        user.password_hash = hash_password(new_password)
        # Force re-authentication everywhere else.
        self.refresh_tokens.revoke_all_for_user(user.id)
        self.audit.record(
            action=AuditAction.USER_UPDATED,
            actor=user,
            resource_type="user",
            resource_id=user.id,
            context={"change": "password"},
        )
        self.db.commit()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def build_identity(self, user: User) -> AuthenticatedUser:
        roles = self.users.role_names(user.id)
        permissions = self.users.permission_codes(user.id)
        return AuthenticatedUser(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            status=user.status,
            roles=roles,
            permissions=permissions,
            clinic_id=self._resolve_clinic_id(user, roles),
            patient_id=self._resolve_patient_id(user, roles),
        )

    def _issue_token_pair(self, user: User) -> TokenPair:
        roles = self.users.role_names(user.id)
        permissions = self.users.permission_codes(user.id)

        access, _ = create_token(
            subject=str(user.id),
            token_type="access",
            roles=roles,
            permissions=permissions,
        )
        refresh_jti = str(uuid.uuid4())
        refresh, refresh_claims = create_token(
            subject=str(user.id), token_type="refresh", jti=refresh_jti
        )
        self._last_refresh_jti = refresh_jti

        self.db.add(
            RefreshToken(
                user_id=user.id,
                jti=refresh_jti,
                expires_at=datetime.fromtimestamp(refresh_claims["exp"], tz=timezone.utc),
            )
        )
        self.db.flush()

        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=settings.access_token_ttl_minutes * 60,
        )

    def _resolve_clinic_id(self, user: User, roles: list[str]) -> uuid.UUID | None:
        from app.models.organization import Doctor, HealthWorker

        if RoleName.DOCTOR.value in roles:
            doctor = self.db.query(Doctor).filter(Doctor.user_id == user.id).one_or_none()
            return doctor.clinic_id if doctor else None
        if RoleName.HEALTH_WORKER.value in roles:
            hw = self.db.query(HealthWorker).filter(HealthWorker.user_id == user.id).one_or_none()
            return hw.clinic_id if hw else None
        return None

    def _resolve_patient_id(self, user: User, roles: list[str]) -> uuid.UUID | None:
        from app.models.patient import Patient

        if RoleName.PATIENT.value not in roles:
            return None
        patient = self.db.query(Patient).filter(Patient.portal_user_id == user.id).one_or_none()
        return patient.id if patient else None

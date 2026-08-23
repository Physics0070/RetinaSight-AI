"""User lifecycle: creation with role + staff profile, search, status changes."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.security import hash_password
from app.domain.enums import AuditAction, RoleName, UserStatus
from app.models.identity import User
from app.models.organization import Clinic, Doctor, HealthWorker
from app.repositories.user_repository import UserRepository
from app.schemas.common import Page, PaginationParams
from app.schemas.user import UserCreate, UserDetail, UserRead, UserUpdate
from app.services.audit_service import AuditService
from app.services.rbac_service import RBACService


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.rbac = RBACService(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------------ #
    def create_user(self, payload: UserCreate, *, actor: User | None = None) -> UserDetail:
        if self.users.get_by_email(payload.email):
            raise ConflictError("An account with that email already exists.")

        if payload.clinic_id is not None and self.db.get(Clinic, payload.clinic_id) is None:
            raise NotFoundError("The selected clinic does not exist.")

        user = User(
            email=str(payload.email).strip().lower(),
            password_hash=hash_password(payload.password),
            full_name=payload.full_name.strip(),
            phone=payload.phone,
            status=UserStatus.ACTIVE.value,
        )
        self.db.add(user)
        self.db.flush()

        self.rbac.assign_role(user_id=user.id, role_name=payload.role)
        self._create_staff_profile(user, payload)

        self.audit.record(
            action=AuditAction.USER_CREATED,
            actor=actor,
            resource_type="user",
            resource_id=user.id,
            context={"role": str(payload.role)},
        )
        self.db.commit()
        return self.get_detail(user.id)

    def _create_staff_profile(self, user: User, payload: UserCreate) -> None:
        """Doctors and health workers get a profile row linking them to a clinic."""
        if payload.role == RoleName.DOCTOR:
            self.db.add(
                Doctor(
                    user_id=user.id,
                    clinic_id=payload.clinic_id,
                    specialty=payload.specialty or "ophthalmology",
                    license_number=payload.license_number,
                )
            )
        elif payload.role == RoleName.HEALTH_WORKER:
            self.db.add(
                HealthWorker(
                    user_id=user.id,
                    clinic_id=payload.clinic_id,
                    staff_code=payload.staff_code,
                )
            )
        self.db.flush()

    # ------------------------------------------------------------------ #
    def get_detail(self, user_id: uuid.UUID) -> UserDetail:
        user = self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found.")

        clinic_id, clinic_name = self._resolve_clinic(user)
        return UserDetail(
            **UserRead.model_validate(user).model_dump(),
            roles=self.users.role_names(user.id),
            permissions=self.users.permission_codes(user.id),
            clinic_id=clinic_id,
            clinic_name=clinic_name,
        )

    def _resolve_clinic(self, user: User) -> tuple[uuid.UUID | None, str | None]:
        doctor = self.db.query(Doctor).filter(Doctor.user_id == user.id).one_or_none()
        worker = (
            self.db.query(HealthWorker).filter(HealthWorker.user_id == user.id).one_or_none()
        )
        profile = doctor or worker
        if profile is None or profile.clinic_id is None:
            return None, None
        clinic = self.db.get(Clinic, profile.clinic_id)
        return profile.clinic_id, clinic.name if clinic else None

    # ------------------------------------------------------------------ #
    def search(
        self,
        *,
        params: PaginationParams,
        query: str | None = None,
        role: str | None = None,
        status: str | None = None,
        sort: str = "created_at",
        descending: bool = True,
    ) -> Page[UserDetail]:
        stmt = self.users.search_statement(
            query=query, role=role, status=status, sort=sort, descending=descending
        )
        rows, total = self.users.paginate(stmt, limit=params.page_size, offset=params.offset)
        items = [self.get_detail(row.id) for row in rows]
        return Page.build(items, total, params)

    # ------------------------------------------------------------------ #
    def update_user(
        self, user_id: uuid.UUID, payload: UserUpdate, *, actor: User | None = None
    ) -> UserDetail:
        user = self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found.")

        changed: dict[str, str] = {}
        if payload.full_name is not None:
            user.full_name = payload.full_name.strip()
            changed["full_name"] = "updated"
        if payload.phone is not None:
            user.phone = payload.phone
            changed["phone"] = "updated"
        if payload.status is not None:
            user.status = payload.status.value
            changed["status"] = payload.status.value

        self.db.flush()
        self.audit.record(
            action=AuditAction.USER_UPDATED,
            actor=actor,
            resource_type="user",
            resource_id=user.id,
            context=changed,
        )
        self.db.commit()
        return self.get_detail(user.id)

    def set_status(
        self,
        user_id: uuid.UUID,
        new_status: UserStatus,
        *,
        actor: User | None = None,
        reason: str | None = None,
    ) -> UserDetail:
        user = self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        if actor is not None and actor.id == user.id and new_status != UserStatus.ACTIVE:
            raise ValidationError("You cannot deactivate your own account.")

        user.status = new_status.value
        if new_status != UserStatus.ACTIVE:
            # Deactivation must immediately end existing sessions.
            from app.repositories.user_repository import RefreshTokenRepository

            RefreshTokenRepository(self.db).revoke_all_for_user(user.id)

        self.db.flush()
        self.audit.record(
            action=AuditAction.USER_UPDATED,
            actor=actor,
            resource_type="user",
            resource_id=user.id,
            context={"status": new_status.value, "reason": reason or ""},
        )
        self.db.commit()
        return self.get_detail(user.id)

    def change_role(
        self, user_id: uuid.UUID, role: RoleName, *, actor: User | None = None
    ) -> UserDetail:
        user = self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        if actor is not None and actor.id == user.id:
            raise ValidationError("You cannot change your own role.")

        previous = self.users.role_names(user.id)
        self.rbac.replace_role(user_id=user.id, role_name=role)
        self.audit.record(
            action=AuditAction.ROLE_CHANGED,
            actor=actor,
            resource_type="user",
            resource_id=user.id,
            context={"from": ",".join(previous), "to": role.value},
        )
        self.db.commit()
        return self.get_detail(user.id)

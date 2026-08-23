"""User, role-assignment and refresh-token persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.models.identity import (
    Permission,
    RefreshToken,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(func_lower(User.email) == email.strip().lower()).limit(1)
        return self.db.execute(stmt).scalar_one_or_none()

    def search_statement(
        self,
        *,
        query: str | None = None,
        role: str | None = None,
        status: str | None = None,
        sort: str = "created_at",
        descending: bool = True,
    ) -> Select:
        stmt = select(User)
        if query:
            like = f"%{query.strip().lower()}%"
            stmt = stmt.where(
                or_(func_lower(User.email).like(like), func_lower(User.full_name).like(like))
            )
        if status:
            stmt = stmt.where(User.status == status)
        if role:
            stmt = (
                stmt.join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.name == role)
            )
        sort_column = getattr(User, sort, User.created_at)
        return stmt.order_by(sort_column.desc() if descending else sort_column.asc())

    def role_names(self, user_id: uuid.UUID) -> list[str]:
        stmt = (
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        return list(self.db.execute(stmt).scalars().all())

    def permission_codes(self, user_id: uuid.UUID) -> list[str]:
        """Effective permissions = union of all permissions of the user's roles."""
        stmt = (
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
            .distinct()
        )
        return sorted(self.db.execute(stmt).scalars().all())

    def assign_role(self, user_id: uuid.UUID, role_id: uuid.UUID) -> UserRole:
        existing = self.db.execute(
            select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
        ).scalar_one_or_none()
        if existing:
            return existing
        link = UserRole(user_id=user_id, role_id=role_id)
        self.db.add(link)
        self.db.flush()
        return link

    def clear_roles(self, user_id: uuid.UUID) -> None:
        for link in self.db.execute(
            select(UserRole).where(UserRole.user_id == user_id)
        ).scalars().all():
            self.db.delete(link)
        self.db.flush()

    def touch_last_active(self, user: User) -> None:
        user.last_active_at = datetime.now(tz=timezone.utc)
        self.db.flush()


class RoleRepository(BaseRepository[Role]):
    model = Role

    def get_by_name(self, name: str) -> Role | None:
        return self.get_by(name=name)

    def all_with_permissions(self) -> Sequence[Role]:
        return self.db.execute(select(Role).order_by(Role.name)).scalars().all()


class PermissionRepository(BaseRepository[Permission]):
    model = Permission

    def get_by_code(self, code: str) -> Permission | None:
        return self.get_by(code=code)

    def codes_for_role(self, role_id: uuid.UUID) -> list[str]:
        stmt = (
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        return sorted(self.db.execute(stmt).scalars().all())


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    def get_by_jti(self, jti: str) -> RefreshToken | None:
        return self.get_by(jti=jti)

    def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        rows = self.db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False)
            )
        ).scalars().all()
        for row in rows:
            row.revoked = True
        self.db.flush()
        return len(rows)


def func_lower(column):  # noqa: ANN001, ANN201
    """Case-insensitive comparison helper (portable SQLite/PostgreSQL)."""
    from sqlalchemy import func

    return func.lower(column)

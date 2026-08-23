"""RBAC: policy seeding, permission resolution and access guards.

Authorization is resolved from the database on every request. Tokens carry a
permission list purely as a UI hint — it is never trusted for enforcement.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, PermissionDeniedError
from app.domain.enums import Permission as PermissionEnum
from app.domain.enums import RoleName
from app.domain.rbac_matrix import (
    DEFAULT_ROLE_PERMISSIONS,
    PERMISSION_DESCRIPTIONS,
    ROLE_DEFINITIONS,
)
from app.models.identity import Permission, Role, RolePermission, User
from app.repositories.user_repository import (
    PermissionRepository,
    RoleRepository,
    UserRepository,
)


class RBACService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.roles = RoleRepository(db)
        self.permissions = PermissionRepository(db)

    # ------------------------------------------------------------------ #
    # Seeding (idempotent)
    # ------------------------------------------------------------------ #
    def seed_policy(self) -> dict[str, int]:
        """Create missing roles/permissions and grant default links.

        Idempotent and additive: existing grants are preserved so that
        administrator customisations survive a redeploy.
        """
        created_permissions = 0
        created_roles = 0
        created_links = 0

        code_to_permission: dict[str, Permission] = {}
        for perm in PermissionEnum:
            description, category = PERMISSION_DESCRIPTIONS.get(perm, ("", "general"))
            existing = self.permissions.get_by_code(perm.value)
            if existing is None:
                existing = Permission(
                    code=perm.value, description=description, category=category
                )
                self.db.add(existing)
                self.db.flush()
                created_permissions += 1
            code_to_permission[perm.value] = existing

        for role_name, meta in ROLE_DEFINITIONS.items():
            role = self.roles.get_by_name(role_name.value)
            if role is None:
                role = Role(
                    name=role_name.value,
                    display_name=meta["display_name"],
                    description=meta["description"],
                    is_system=True,
                )
                self.db.add(role)
                self.db.flush()
                created_roles += 1

            existing_codes = set(self.permissions.codes_for_role(role.id))
            for perm in DEFAULT_ROLE_PERMISSIONS.get(role_name, []):
                if perm.value in existing_codes:
                    continue
                self.db.add(
                    RolePermission(
                        role_id=role.id, permission_id=code_to_permission[perm.value].id
                    )
                )
                created_links += 1

        self.db.flush()
        return {
            "permissions_created": created_permissions,
            "roles_created": created_roles,
            "grants_created": created_links,
        }

    # ------------------------------------------------------------------ #
    # Resolution
    # ------------------------------------------------------------------ #
    def effective_permissions(self, user_id: uuid.UUID) -> set[str]:
        return set(self.users.permission_codes(user_id))

    def role_names(self, user_id: uuid.UUID) -> set[str]:
        return set(self.users.role_names(user_id))

    def has_permission(self, user: User, permission: PermissionEnum | str) -> bool:
        return str(permission) in self.effective_permissions(user.id)

    def has_role(self, user: User, role: RoleName | str) -> bool:
        return str(role) in self.role_names(user.id)

    def require_permission(self, user: User, permission: PermissionEnum | str) -> None:
        if not self.has_permission(user, permission):
            raise PermissionDeniedError()

    # ------------------------------------------------------------------ #
    # Role assignment
    # ------------------------------------------------------------------ #
    def assign_role(self, *, user_id: uuid.UUID, role_name: RoleName | str) -> None:
        role = self.roles.get_by_name(str(role_name))
        if role is None:
            raise NotFoundError(f"Role '{role_name}' is not defined.")
        self.users.assign_role(user_id, role.id)

    def replace_role(self, *, user_id: uuid.UUID, role_name: RoleName | str) -> None:
        self.users.clear_roles(user_id)
        self.assign_role(user_id=user_id, role_name=role_name)

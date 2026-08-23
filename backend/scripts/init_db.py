"""Initialise the database: create schema, seed the RBAC policy, bootstrap admin.

Idempotent — safe to re-run. Intended for local development and first-time
environment setup. Schema changes in a real deployment go through Alembic.

Usage:
    python -m scripts.init_db
"""

from __future__ import annotations

import sys

from email_validator import EmailNotValidError, validate_email

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.domain.enums import RoleName, UserStatus
from app.models import User  # noqa: F401  (registers all mappers)
from app.repositories.user_repository import UserRepository
from app.services.rbac_service import RBACService

logger = get_logger(__name__)


def create_schema() -> None:
    Base.metadata.create_all(engine)
    logger.info("Schema ready (%s tables).", len(Base.metadata.tables))


def seed_policy() -> None:
    with SessionLocal() as db:
        stats = RBACService(db).seed_policy()
        db.commit()
        logger.info(
            "RBAC policy seeded: %s permissions, %s roles, %s grants created.",
            stats["permissions_created"],
            stats["roles_created"],
            stats["grants_created"],
        )


def bootstrap_admin() -> None:
    """Create the initial administrator if no admin exists yet.

    Credentials come from RS_SEED_ADMIN_* environment variables. In production
    these MUST be set to real secret values before first run.
    """
    # Fail loudly rather than creating an account that can never sign in:
    # the login endpoint validates the address, so a reserved TLD (.local,
    # .test, .example) here would produce a permanently locked-out admin.
    try:
        validate_email(settings.seed_admin_email, check_deliverability=False)
    except EmailNotValidError as exc:
        logger.error(
            "RS_SEED_ADMIN_EMAIL (%s) is not a valid login address: %s",
            settings.seed_admin_email,
            exc,
        )
        sys.exit(1)

    with SessionLocal() as db:
        users = UserRepository(db)
        if users.get_by_email(settings.seed_admin_email):
            logger.info("Bootstrap admin already exists; nothing to do.")
            return

        if settings.is_production and settings.seed_admin_password.startswith("ChangeMe"):
            logger.error(
                "Refusing to create a production admin with the default password. "
                "Set RS_SEED_ADMIN_PASSWORD to a real secret."
            )
            sys.exit(1)

        admin = User(
            email=settings.seed_admin_email.strip().lower(),
            password_hash=hash_password(settings.seed_admin_password),
            full_name="Platform Administrator",
            status=UserStatus.ACTIVE.value,
        )
        db.add(admin)
        db.flush()
        RBACService(db).assign_role(user_id=admin.id, role_name=RoleName.ADMIN)
        db.commit()
        logger.info("Bootstrap admin created: %s", admin.email)


def main() -> None:
    logger.info("Initialising database at %s", "sqlite (dev)" if settings.is_sqlite else "postgresql")
    create_schema()
    seed_policy()
    bootstrap_admin()
    logger.info("Database initialisation complete.")


if __name__ == "__main__":
    main()

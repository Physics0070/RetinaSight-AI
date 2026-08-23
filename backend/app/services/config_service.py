"""Runtime configuration service.

The single read path for clinical/business rules. Engines never embed
thresholds — they ask this service, which reads ``system_configuration`` and
falls back to the seeded defaults if a key is missing.

Every write is versioned and audited.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.domain.config_defaults import DEFAULT_CONFIGURATION
from app.domain.enums import AuditAction
from app.models.identity import User
from app.models.system import FeatureFlag, SystemConfiguration
from app.repositories.base import BaseRepository
from app.services.audit_service import AuditService

logger = get_logger(__name__)


class ConfigurationRepository(BaseRepository[SystemConfiguration]):
    model = SystemConfiguration


class FeatureFlagRepository(BaseRepository[FeatureFlag]):
    model = FeatureFlag


class ConfigService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ConfigurationRepository(db)
        self.flags = FeatureFlagRepository(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------------ #
    # Seeding
    # ------------------------------------------------------------------ #
    def seed_defaults(self) -> int:
        """Insert any missing configuration keys. Never overwrites edits."""
        created = 0
        for key, spec in DEFAULT_CONFIGURATION.items():
            if self.repo.get_by(key=key) is not None:
                continue
            self.db.add(
                SystemConfiguration(
                    key=key,
                    value=spec["value"],
                    category=spec.get("category", "general"),
                    description=spec.get("description", ""),
                    is_editable=spec.get("is_editable", True),
                    version=1,
                )
            )
            created += 1
        self.db.flush()
        return created

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    def get(self, key: str) -> dict[str, Any]:
        """Stored value, or the seeded default if the key has not been created."""
        row = self.repo.get_by(key=key)
        if row is not None:
            return row.value
        default = DEFAULT_CONFIGURATION.get(key)
        if default is None:
            raise NotFoundError(f"Configuration '{key}' is not defined.")
        logger.debug("Configuration '%s' not in database; using seeded default.", key)
        return default["value"]

    def get_value(self, key: str, field: str, fallback: Any = None) -> Any:
        return self.get(key).get(field, fallback)

    def list_all(self, *, category: str | None = None) -> list[SystemConfiguration]:
        filters: dict[str, Any] = {"category": category} if category else {}
        rows = list(self.repo.list(**filters))
        return sorted(rows, key=lambda r: (r.category, r.key))

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #
    def set(
        self, key: str, value: dict[str, Any], *, actor: User | None = None
    ) -> SystemConfiguration:
        if not isinstance(value, dict):
            raise ValidationError("Configuration values must be objects.")

        row = self.repo.get_by(key=key)
        if row is None:
            spec = DEFAULT_CONFIGURATION.get(key)
            if spec is None:
                raise NotFoundError(f"Configuration '{key}' is not defined.")
            row = SystemConfiguration(
                key=key,
                value=value,
                category=spec.get("category", "general"),
                description=spec.get("description", ""),
                version=1,
            )
            self.db.add(row)
        else:
            if not row.is_editable:
                raise ValidationError(f"Configuration '{key}' is not editable.")
            row.value = value
            row.version += 1

        row.updated_by_user_id = actor.id if actor else None
        self.db.flush()

        self.audit.record(
            action=AuditAction.CONFIG_CHANGED,
            actor=actor,
            resource_type="system_configuration",
            resource_id=key,
            # The new value is recorded for traceability; configuration is not
            # patient data.
            context={"version": row.version, "keys": sorted(value.keys())},
        )
        self.db.commit()
        return row

    def reset_to_default(self, key: str, *, actor: User | None = None) -> SystemConfiguration:
        spec = DEFAULT_CONFIGURATION.get(key)
        if spec is None:
            raise NotFoundError(f"Configuration '{key}' is not defined.")
        return self.set(key, spec["value"], actor=actor)

    # ------------------------------------------------------------------ #
    # Feature flags
    # ------------------------------------------------------------------ #
    def is_enabled(self, key: str, *, default: bool = False) -> bool:
        flag = self.flags.get_by(key=key)
        return flag.enabled if flag else default

    def set_flag(
        self, key: str, enabled: bool, *, actor: User | None = None, description: str = ""
    ) -> FeatureFlag:
        flag = self.flags.get_by(key=key)
        if flag is None:
            flag = FeatureFlag(key=key, enabled=enabled, description=description)
            self.db.add(flag)
        else:
            flag.enabled = enabled
        flag.updated_by_user_id = actor.id if actor else None
        self.db.flush()

        self.audit.record(
            action=AuditAction.CONFIG_CHANGED,
            actor=actor,
            resource_type="feature_flag",
            resource_id=key,
            context={"enabled": enabled},
        )
        self.db.commit()
        return flag

    def list_flags(self) -> list[FeatureFlag]:
        return sorted(self.flags.list(), key=lambda f: f.key)

"""System-level models: sync queue, audit log, runtime configuration, feature flags."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.domain.enums import SyncStatus


class SyncQueueItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Server-side mirror of an offline device's outbound queue item.

    ``local_id`` + ``entity_type`` is unique, giving idempotent replay: a retried
    upload updates the existing row instead of duplicating a clinical record.
    """

    __tablename__ = "sync_queue"
    __table_args__ = (UniqueConstraint("local_id", "entity_type"),)

    local_id: Mapped[str] = mapped_column(String(64), index=True)
    server_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    operation: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(
        String(16), default=SyncStatus.PENDING.value, index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )


class AuditLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Append-only audit trail. Never stores raw patient data or credentials."""

    __tablename__ = "audit_logs"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(48), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    result: Mapped[str] = mapped_column(String(16), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Non-sensitive contextual metadata only.
    context: Mapped[dict] = mapped_column(JSON, default=dict)


class SystemConfiguration(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Runtime-editable business/clinical configuration.

    Values live here (not in code) so risk thresholds, quality cut-offs and
    referral rules can be tuned and audited without a redeploy.
    """

    __tablename__ = "system_configuration"

    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    category: Mapped[str] = mapped_column(String(64), default="general", index=True)
    description: Mapped[str] = mapped_column(String(512), default="")
    is_editable: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class FeatureFlag(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(String(512), default="")
    rollout_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

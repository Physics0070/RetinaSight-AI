"""Patient medical history and prescriptions.

Both are **clinician-authored** records. Nothing here is produced by the model:
the AI screens and explains, a licensed clinician decides. That separation is
why prescriptions carry the prescriber's user id and are never writable by the
inference path.

History entries are editable and soft-deleted rather than destroyed, because a
medical record that can be silently rewritten is not a medical record. Every
create/update/remove is audited by the service layer.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PatientHistoryEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One typed fact in a patient's medical history."""

    __tablename__ = "patient_history_entries"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )
    # condition | medication | allergy | procedure | family_history | observation | note
    entry_type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When the fact happened clinically — distinct from created_at, which is
    # when it was typed in. Backdating history is normal and must be possible.
    occurred_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Free-form but bounded, e.g. "ongoing", "resolved", "severe".
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)

    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Soft delete: the row stays, so an audit trail of what was once recorded
    # survives. Reads filter this out by default.
    is_removed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    removed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Prescription(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A prescription written by a clinician for a patient.

    ``items`` holds the prescribed drugs as a JSON list of
    ``{name, dose, frequency, duration, instructions}``. A prescription is
    dispensed as one document, so its lines are stored and revised together
    rather than as independently editable rows.
    """

    __tablename__ = "prescriptions"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )
    # Optional provenance: the screening that prompted this prescription.
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("screening_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # The prescribing clinician. Never nullable in practice at write time; the
    # FK is SET NULL only so deleting a user cannot destroy the record.
    prescribed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    items: Mapped[list] = mapped_column(JSON, default=list)
    diagnosis: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # active | completed | discontinued
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)

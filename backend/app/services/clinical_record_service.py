"""Medical history and prescribing.

Both are clinician-authored: the AI never writes here. Every mutation is
audited, and history entries are soft-deleted so the record of what was once
recorded survives a correction — a medical record that can be silently
rewritten is not a medical record.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.domain.enums import AuditAction, PrescriptionStatus
from app.models.clinical_record import PatientHistoryEntry, Prescription
from app.models.identity import User
from app.services.audit_service import AuditService


class ClinicalRecordService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    # ---------------------------------------------------------------- history
    def history_for(
        self, patient_id: uuid.UUID, *, include_removed: bool = False
    ) -> list[PatientHistoryEntry]:
        """Newest clinical event first; undated entries fall back to entry time."""
        stmt = select(PatientHistoryEntry).where(
            PatientHistoryEntry.patient_id == patient_id
        )
        if not include_removed:
            stmt = stmt.where(PatientHistoryEntry.is_removed.is_(False))
        rows = list(self.db.execute(stmt).scalars().all())
        rows.sort(
            key=lambda e: (
                e.occurred_on.isoformat() if e.occurred_on else "",
                e.created_at.isoformat(),
            ),
            reverse=True,
        )
        return rows

    def add_history(
        self,
        patient_id: uuid.UUID,
        *,
        entry_type: str,
        title: str,
        detail: str | None = None,
        occurred_on=None,
        status: str | None = None,
        actor: User | None = None,
    ) -> PatientHistoryEntry:
        entry = PatientHistoryEntry(
            patient_id=patient_id,
            entry_type=entry_type,
            title=title.strip(),
            detail=detail,
            occurred_on=occurred_on,
            status=status,
            recorded_by_user_id=actor.id if actor else None,
        )
        self.db.add(entry)
        self.db.flush()

        self.audit.record(
            action=AuditAction.HISTORY_ENTRY_ADDED,
            actor=actor,
            resource_type="patient_history_entry",
            resource_id=entry.id,
            # The clinical detail itself is not copied into the audit log.
            context={"patient_id": str(patient_id), "entry_type": entry_type},
        )
        self.db.commit()
        return entry

    def get_history_entry(self, entry_id: uuid.UUID) -> PatientHistoryEntry:
        entry = self.db.get(PatientHistoryEntry, entry_id)
        if entry is None or entry.is_removed:
            raise NotFoundError("History entry not found.")
        return entry

    def update_history(
        self, entry_id: uuid.UUID, changes: dict, *, actor: User | None = None
    ) -> PatientHistoryEntry:
        entry = self.get_history_entry(entry_id)

        applied: list[str] = []
        for field in ("entry_type", "title", "detail", "occurred_on", "status"):
            if field in changes and changes[field] is not None:
                value = changes[field]
                if field == "title":
                    value = str(value).strip()
                    if not value:
                        raise ValidationError("Title cannot be empty.")
                setattr(entry, field, value)
                applied.append(field)

        if not applied:
            return entry

        entry.updated_by_user_id = actor.id if actor else None
        self.db.flush()
        self.audit.record(
            action=AuditAction.HISTORY_ENTRY_UPDATED,
            actor=actor,
            resource_type="patient_history_entry",
            resource_id=entry.id,
            # Which fields changed, never their clinical content.
            context={"patient_id": str(entry.patient_id), "fields": sorted(applied)},
        )
        self.db.commit()
        return entry

    def remove_history(self, entry_id: uuid.UUID, *, actor: User | None = None) -> None:
        """Soft delete — the row stays so the record of it survives."""
        entry = self.get_history_entry(entry_id)
        entry.is_removed = True
        entry.removed_at = datetime.now(tz=timezone.utc)
        entry.updated_by_user_id = actor.id if actor else None
        self.db.flush()
        self.audit.record(
            action=AuditAction.HISTORY_ENTRY_REMOVED,
            actor=actor,
            resource_type="patient_history_entry",
            resource_id=entry.id,
            context={"patient_id": str(entry.patient_id)},
        )
        self.db.commit()

    # ---------------------------------------------------------- prescriptions
    def prescriptions_for(self, patient_id: uuid.UUID) -> list[Prescription]:
        stmt = (
            select(Prescription)
            .where(Prescription.patient_id == patient_id)
            .order_by(Prescription.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_prescription(self, prescription_id: uuid.UUID) -> Prescription:
        prescription = self.db.get(Prescription, prescription_id)
        if prescription is None:
            raise NotFoundError("Prescription not found.")
        return prescription

    def prescribe(
        self,
        patient_id: uuid.UUID,
        *,
        items: list[dict],
        diagnosis: str | None = None,
        notes: str | None = None,
        session_id: uuid.UUID | None = None,
        valid_until=None,
        actor: User | None = None,
    ) -> Prescription:
        if not items:
            raise ValidationError("A prescription needs at least one medicine.")
        # The prescriber is the signature on the document; without an
        # identified clinician this is not a prescription.
        if actor is None:
            raise ValidationError("A prescription must be attributed to a clinician.")

        prescription = Prescription(
            patient_id=patient_id,
            session_id=session_id,
            prescribed_by_user_id=actor.id,
            items=items,
            diagnosis=diagnosis,
            notes=notes,
            valid_until=valid_until,
            status=PrescriptionStatus.ACTIVE.value,
        )
        self.db.add(prescription)
        self.db.flush()

        self.audit.record(
            action=AuditAction.PRESCRIPTION_ISSUED,
            actor=actor,
            resource_type="prescription",
            resource_id=prescription.id,
            # Count only — drug names are clinical content, not audit metadata.
            context={"patient_id": str(patient_id), "item_count": len(items)},
        )
        self.db.commit()
        return prescription

    def revise_prescription(
        self, prescription_id: uuid.UUID, changes: dict, *, actor: User | None = None
    ) -> Prescription:
        prescription = self.get_prescription(prescription_id)

        applied: list[str] = []
        for field in ("status", "items", "diagnosis", "notes", "valid_until"):
            if field in changes and changes[field] is not None:
                setattr(prescription, field, changes[field])
                applied.append(field)

        if not applied:
            return prescription

        self.db.flush()
        self.audit.record(
            action=AuditAction.PRESCRIPTION_UPDATED,
            actor=actor,
            resource_type="prescription",
            resource_id=prescription.id,
            context={
                "patient_id": str(prescription.patient_id),
                "fields": sorted(applied),
            },
        )
        self.db.commit()
        return prescription

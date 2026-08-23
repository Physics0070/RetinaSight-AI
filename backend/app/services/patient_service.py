"""Patient registration, consent and lookup.

Only information needed for DR screening and referral is collected.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.domain.enums import AuditAction, ConsentType
from app.models.identity import User
from app.models.patient import Patient, PatientConsent
from app.repositories.base import BaseRepository
from app.services.audit_service import AuditService


class PatientRepository(BaseRepository[Patient]):
    model = Patient

    def search_statement(
        self, *, query: str | None = None, clinic_id: uuid.UUID | None = None
    ) -> Select:
        from sqlalchemy import func

        stmt = select(Patient)
        if query:
            like = f"%{query.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Patient.full_name).like(like),
                    func.lower(Patient.patient_code).like(like),
                )
            )
        if clinic_id is not None:
            stmt = stmt.where(Patient.clinic_id == clinic_id)
        return stmt.order_by(Patient.created_at.desc())


class PatientService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = PatientRepository(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------------ #
    def register(
        self,
        *,
        full_name: str,
        patient_code: str | None = None,
        date_of_birth=None,
        sex: str | None = None,
        phone: str | None = None,
        has_diabetes: bool | None = None,
        diabetes_duration_years: int | None = None,
        clinic_id: uuid.UUID | None = None,
        actor: User | None = None,
        consents: dict[str, bool] | None = None,
    ) -> Patient:
        code = (patient_code or self._generate_code()).strip()
        if self.repo.get_by(patient_code=code) is not None:
            raise ConflictError(f"Patient code '{code}' is already in use.")

        patient = Patient(
            patient_code=code,
            full_name=full_name.strip(),
            date_of_birth=date_of_birth,
            sex=sex,
            phone=phone,
            has_diabetes=has_diabetes,
            diabetes_duration_years=diabetes_duration_years,
            clinic_id=clinic_id,
            registered_by_user_id=actor.id if actor else None,
        )
        self.db.add(patient)
        self.db.flush()

        # Screening consent is a precondition for imaging, recorded explicitly.
        for consent_type, granted in (consents or {}).items():
            self._record_consent(patient, consent_type, granted, actor)

        self.audit.record(
            action=AuditAction.PATIENT_CREATED,
            actor=actor,
            resource_type="patient",
            resource_id=patient.id,
            # Patient name is deliberately not written to the audit log.
            context={"patient_code": code, "clinic_id": str(clinic_id) if clinic_id else None},
        )
        self.db.commit()
        return patient

    def _record_consent(
        self, patient: Patient, consent_type: str, granted: bool, actor: User | None
    ) -> PatientConsent:
        try:
            resolved = ConsentType(consent_type)
        except ValueError as exc:
            raise ValidationError(f"Unknown consent type '{consent_type}'.") from exc

        consent = PatientConsent(
            patient_id=patient.id,
            consent_type=resolved.value,
            granted=granted,
            granted_at=datetime.now(tz=timezone.utc) if granted else None,
            recorded_by_user_id=actor.id if actor else None,
        )
        self.db.add(consent)
        self.db.flush()
        return consent

    def record_consent(
        self,
        patient_id: uuid.UUID,
        *,
        consent_type: str,
        granted: bool,
        actor: User | None = None,
    ) -> PatientConsent:
        patient = self.get(patient_id)
        consent = self._record_consent(patient, consent_type, granted, actor)
        self.audit.record(
            action=AuditAction.CONSENT_RECORDED,
            actor=actor,
            resource_type="patient",
            resource_id=patient.id,
            context={"consent_type": consent_type, "granted": granted},
        )
        self.db.commit()
        return consent

    def has_consent(self, patient_id: uuid.UUID, consent_type: ConsentType) -> bool:
        """Latest recorded decision for this consent type."""
        row = self.db.execute(
            select(PatientConsent)
            .where(
                PatientConsent.patient_id == patient_id,
                PatientConsent.consent_type == consent_type.value,
            )
            .order_by(PatientConsent.created_at.desc())
            .limit(1)
        ).scalars().first()
        return bool(row and row.granted)

    # ------------------------------------------------------------------ #
    def get(self, patient_id: uuid.UUID) -> Patient:
        patient = self.repo.get(patient_id)
        if patient is None:
            raise NotFoundError("Patient not found.")
        return patient

    def consents_for(self, patient_id: uuid.UUID) -> list[PatientConsent]:
        return list(
            self.db.execute(
                select(PatientConsent)
                .where(PatientConsent.patient_id == patient_id)
                .order_by(PatientConsent.created_at.desc())
            ).scalars().all()
        )

    def update(
        self, patient_id: uuid.UUID, changes: dict, *, actor: User | None = None
    ) -> Patient:
        patient = self.get(patient_id)
        allowed = {
            "full_name",
            "date_of_birth",
            "sex",
            "phone",
            "has_diabetes",
            "diabetes_duration_years",
            "clinic_id",
        }
        applied = []
        for field, value in changes.items():
            if field in allowed and value is not None:
                setattr(patient, field, value)
                applied.append(field)

        self.db.flush()
        self.audit.record(
            action=AuditAction.PATIENT_UPDATED,
            actor=actor,
            resource_type="patient",
            resource_id=patient.id,
            context={"fields": applied},
        )
        self.db.commit()
        return patient

    @staticmethod
    def _generate_code() -> str:
        return f"RS-{uuid.uuid4().hex[:10].upper()}"

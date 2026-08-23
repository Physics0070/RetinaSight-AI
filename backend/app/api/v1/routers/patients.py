"""Patient registration and lookup.

``/patients/me`` serves the patient portal and resolves strictly to the caller's
own record. Every ``/{patient_id}`` route runs through ``authorize_patient``,
which grants staff access by permission and a patient access only to themselves.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import Access, DbSession, require_permission
from app.domain.enums import Permission
from app.schemas.common import Page, PaginationParams
from app.schemas.screening import (
    ConsentInput,
    ConsentRead,
    PatientCreate,
    PatientRead,
    PatientUpdate,
)
from app.services.patient_service import PatientRepository, PatientService

router = APIRouter(prefix="/patients", tags=["patients"])

CanCreate = Annotated[Access, Depends(require_permission(Permission.PATIENT_CREATE))]
CanView = Annotated[Access, Depends(require_permission(Permission.PATIENT_VIEW))]
CanUpdate = Annotated[Access, Depends(require_permission(Permission.PATIENT_UPDATE))]


# --- patient-portal self routes (declared before "/{patient_id}") ---------- #
@router.get("/me", response_model=PatientRead)
def get_own_record(access: Access) -> PatientRead:
    return PatientRead.model_validate(access.resolve_own_patient())


@router.get("/me/consents", response_model=list[ConsentRead])
def get_own_consents(access: Access, db: DbSession) -> list[ConsentRead]:
    patient = access.resolve_own_patient()
    return [
        ConsentRead.model_validate(c) for c in PatientService(db).consents_for(patient.id)
    ]


# --- staff routes ---------------------------------------------------------- #
@router.get("", response_model=Page[PatientRead])
def list_patients(
    access: CanView,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    query: str | None = Query(default=None, description="Search name or patient code."),
    clinic_id: uuid.UUID | None = Query(default=None),
) -> Page[PatientRead]:
    repo = PatientRepository(db)
    params = PaginationParams(page=page, page_size=page_size)
    stmt = repo.search_statement(query=query, clinic_id=clinic_id)
    rows, total = repo.paginate(stmt, limit=params.page_size, offset=params.offset)
    return Page.build([PatientRead.model_validate(r) for r in rows], total, params)


@router.post("", response_model=PatientRead, status_code=status.HTTP_201_CREATED)
def register_patient(
    payload: PatientCreate, access: CanCreate, db: DbSession
) -> PatientRead:
    patient = PatientService(db).register(
        full_name=payload.full_name,
        patient_code=payload.patient_code,
        date_of_birth=payload.date_of_birth,
        sex=payload.sex,
        phone=payload.phone,
        has_diabetes=payload.has_diabetes,
        diabetes_duration_years=payload.diabetes_duration_years,
        clinic_id=payload.clinic_id or access.user_clinic_id(),
        actor=access.user,
        consents={c.consent_type.value: c.granted for c in payload.consents},
    )
    return PatientRead.model_validate(patient)


@router.get("/{patient_id}", response_model=PatientRead)
def get_patient(patient_id: uuid.UUID, access: Access) -> PatientRead:
    return PatientRead.model_validate(access.authorize_patient(patient_id))


@router.patch("/{patient_id}", response_model=PatientRead)
def update_patient(
    patient_id: uuid.UUID, payload: PatientUpdate, access: CanUpdate, db: DbSession
) -> PatientRead:
    access.authorize_patient(patient_id)
    patient = PatientService(db).update(
        patient_id, payload.model_dump(exclude_unset=True), actor=access.user
    )
    return PatientRead.model_validate(patient)


@router.get("/{patient_id}/consents", response_model=list[ConsentRead])
def list_consents(patient_id: uuid.UUID, access: Access, db: DbSession) -> list[ConsentRead]:
    access.authorize_patient(patient_id)
    return [
        ConsentRead.model_validate(c) for c in PatientService(db).consents_for(patient_id)
    ]


@router.post(
    "/{patient_id}/consents",
    response_model=ConsentRead,
    status_code=status.HTTP_201_CREATED,
)
def record_consent(
    patient_id: uuid.UUID, payload: ConsentInput, access: CanUpdate, db: DbSession
) -> ConsentRead:
    access.authorize_patient(patient_id)
    consent = PatientService(db).record_consent(
        patient_id,
        consent_type=payload.consent_type.value,
        granted=payload.granted,
        actor=access.user,
    )
    return ConsentRead.model_validate(consent)

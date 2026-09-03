"""Medical history and prescriptions.

Every route runs through ``authorize_patient``, which grants staff access by
permission and a patient access only to their own record — so a doctor cannot
read a patient outside their remit, and a patient cannot read anyone else.

Writing is separated from reading by permission: a health worker may read
history for context at capture time, only a clinician may write it, and only a
clinician may prescribe. An administrator gets read-only oversight and is
deliberately given no prescribing authority.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import Access, DbSession, require_permission
from app.domain.enums import Permission
from app.schemas.clinical_record import (
    HistoryEntryCreate,
    HistoryEntryRead,
    HistoryEntryUpdate,
    PrescriptionCreate,
    PrescriptionRead,
    PrescriptionUpdate,
)
from app.services.clinical_record_service import ClinicalRecordService

router = APIRouter(tags=["clinical record"])

CanViewHistory = Annotated[Access, Depends(require_permission(Permission.HISTORY_VIEW))]
CanManageHistory = Annotated[Access, Depends(require_permission(Permission.HISTORY_MANAGE))]
CanViewRx = Annotated[Access, Depends(require_permission(Permission.PRESCRIPTION_VIEW))]
CanWriteRx = Annotated[Access, Depends(require_permission(Permission.PRESCRIPTION_WRITE))]


# --------------------------------------------------------------------------- #
# Patient-portal self routes (declared before "/{patient_id}" equivalents)
# --------------------------------------------------------------------------- #
@router.get("/patients/me/history", response_model=list[HistoryEntryRead])
def own_history(access: Access, db: DbSession) -> list[HistoryEntryRead]:
    patient = access.resolve_own_patient()
    return [
        HistoryEntryRead.model_validate(e)
        for e in ClinicalRecordService(db).history_for(patient.id)
    ]


@router.get("/patients/me/prescriptions", response_model=list[PrescriptionRead])
def own_prescriptions(access: Access, db: DbSession) -> list[PrescriptionRead]:
    patient = access.resolve_own_patient()
    return [
        PrescriptionRead.model_validate(p)
        for p in ClinicalRecordService(db).prescriptions_for(patient.id)
    ]


# --------------------------------------------------------------------------- #
# Medical history
# --------------------------------------------------------------------------- #
@router.get("/patients/{patient_id}/history", response_model=list[HistoryEntryRead])
def list_history(
    patient_id: uuid.UUID,
    access: CanViewHistory,
    db: DbSession,
    include_removed: bool = Query(
        default=False, description="Include soft-deleted entries (audit view)."
    ),
) -> list[HistoryEntryRead]:
    access.authorize_patient(patient_id)
    entries = ClinicalRecordService(db).history_for(
        patient_id, include_removed=include_removed
    )
    return [HistoryEntryRead.model_validate(e) for e in entries]


@router.post(
    "/patients/{patient_id}/history",
    response_model=HistoryEntryRead,
    status_code=status.HTTP_201_CREATED,
)
def add_history(
    patient_id: uuid.UUID,
    payload: HistoryEntryCreate,
    access: CanManageHistory,
    db: DbSession,
) -> HistoryEntryRead:
    access.authorize_patient(patient_id)
    entry = ClinicalRecordService(db).add_history(
        patient_id,
        entry_type=payload.entry_type.value,
        title=payload.title,
        detail=payload.detail,
        occurred_on=payload.occurred_on,
        status=payload.status,
        actor=access.user,
    )
    return HistoryEntryRead.model_validate(entry)


@router.patch("/history/{entry_id}", response_model=HistoryEntryRead)
def update_history(
    entry_id: uuid.UUID,
    payload: HistoryEntryUpdate,
    access: CanManageHistory,
    db: DbSession,
) -> HistoryEntryRead:
    service = ClinicalRecordService(db)
    # Resolve first, then authorise against the OWNING patient — otherwise an
    # entry id would be a way around the patient-scoped access check.
    entry = service.get_history_entry(entry_id)
    access.authorize_patient(entry.patient_id)

    changes = payload.model_dump(exclude_unset=True)
    if "entry_type" in changes and changes["entry_type"] is not None:
        changes["entry_type"] = changes["entry_type"].value
    updated = service.update_history(entry_id, changes, actor=access.user)
    return HistoryEntryRead.model_validate(updated)


@router.delete("/history/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_history(entry_id: uuid.UUID, access: CanManageHistory, db: DbSession) -> None:
    service = ClinicalRecordService(db)
    entry = service.get_history_entry(entry_id)
    access.authorize_patient(entry.patient_id)
    service.remove_history(entry_id, actor=access.user)


# --------------------------------------------------------------------------- #
# Prescriptions
# --------------------------------------------------------------------------- #
@router.get(
    "/patients/{patient_id}/prescriptions", response_model=list[PrescriptionRead]
)
def list_prescriptions(
    patient_id: uuid.UUID, access: CanViewRx, db: DbSession
) -> list[PrescriptionRead]:
    access.authorize_patient(patient_id)
    return [
        PrescriptionRead.model_validate(p)
        for p in ClinicalRecordService(db).prescriptions_for(patient_id)
    ]


@router.post(
    "/patients/{patient_id}/prescriptions",
    response_model=PrescriptionRead,
    status_code=status.HTTP_201_CREATED,
)
def prescribe(
    patient_id: uuid.UUID,
    payload: PrescriptionCreate,
    access: CanWriteRx,
    db: DbSession,
) -> PrescriptionRead:
    access.authorize_patient(patient_id)
    prescription = ClinicalRecordService(db).prescribe(
        patient_id,
        items=[item.model_dump() for item in payload.items],
        diagnosis=payload.diagnosis,
        notes=payload.notes,
        session_id=payload.session_id,
        valid_until=payload.valid_until,
        actor=access.user,
    )
    return PrescriptionRead.model_validate(prescription)


@router.patch("/prescriptions/{prescription_id}", response_model=PrescriptionRead)
def revise_prescription(
    prescription_id: uuid.UUID,
    payload: PrescriptionUpdate,
    access: CanWriteRx,
    db: DbSession,
) -> PrescriptionRead:
    service = ClinicalRecordService(db)
    prescription = service.get_prescription(prescription_id)
    access.authorize_patient(prescription.patient_id)

    changes = payload.model_dump(exclude_unset=True)
    if changes.get("status") is not None:
        changes["status"] = changes["status"].value
    if changes.get("items") is not None:
        changes["items"] = [dict(item) for item in changes["items"]]
    revised = service.revise_prescription(prescription_id, changes, actor=access.user)
    return PrescriptionRead.model_validate(revised)

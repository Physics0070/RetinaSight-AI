"""Screening workflow endpoints.

Mirrors the state machine: start -> capture -> quality -> inference ->
explanation -> risk -> referral -> review -> follow-up -> complete, with
explicit exits (cancel, save-and-exit) available throughout.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from app.api.deps import Access, DbSession, require_permission
from app.core.config import settings
from app.domain.enums import EyeSide, Permission
from app.ml.explainability import GRADCAM_CAVEAT
from app.schemas.common import MessageResponse, Page, PaginationParams
from app.schemas.image import RetinalImageRead
from app.schemas.screening import (
    CancelRequest,
    CaptureResponse,
    ExplanationWithUrls,
    InferenceResultRead,
    InferenceRunResponse,
    PatientRead,
    QualityAssessmentRead,
    ReferralRead,
    RetakeRequest,
    RiskAssessmentRead,
    ScreeningSessionDetail,
    ScreeningSessionRead,
    ScreeningStartRequest,
)
from app.services.inference_service import InferenceService
from app.services.screening_service import ScreeningService
from app.services.screening_state_machine import STATE_LABELS, coerce, is_terminal
from app.storage import get_storage_provider

router = APIRouter(prefix="/screenings", tags=["screenings"])

CanScreen = Annotated[Access, Depends(require_permission(Permission.SCREENING_CREATE))]
CanViewScreening = Annotated[Access, Depends(require_permission(Permission.SCREENING_VIEW))]
CanInfer = Annotated[Access, Depends(require_permission(Permission.INFERENCE_RUN))]

AI_DISCLAIMER = (
    "AI-assisted screening support. This is not a diagnosis. "
    "Clinical review by a qualified clinician is required."
)


def _label(state: str) -> str:
    return STATE_LABELS.get(coerce(state), state)


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
@router.post("", response_model=ScreeningSessionRead, status_code=status.HTTP_201_CREATED)
def start_screening(
    payload: ScreeningStartRequest, access: CanScreen, db: DbSession
) -> ScreeningSessionRead:
    """Open a screening session. Requires recorded screening consent."""
    access.authorize_patient(payload.patient_id)
    session = ScreeningService(db).start_screening(
        patient_id=payload.patient_id,
        actor=access.user,
        clinic_id=payload.clinic_id or access.user_clinic_id(),
        local_id=payload.local_id,
        captured_offline=payload.captured_offline,
    )
    return ScreeningSessionRead.model_validate(session)


@router.get("", response_model=Page[ScreeningSessionRead])
def list_screenings(
    access: CanViewScreening,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    patient_id: uuid.UUID | None = Query(default=None),
    state: str | None = Query(default=None),
) -> Page[ScreeningSessionRead]:
    from sqlalchemy import select

    from app.models.screening import ScreeningSession

    params = PaginationParams(page=page, page_size=page_size)
    stmt = select(ScreeningSession)
    if patient_id is not None:
        access.authorize_patient(patient_id)
        stmt = stmt.where(ScreeningSession.patient_id == patient_id)
    if state:
        stmt = stmt.where(ScreeningSession.state == state)
    stmt = stmt.order_by(ScreeningSession.created_at.desc())

    service = ScreeningService(db)
    rows, total = service.sessions.paginate(
        stmt, limit=params.page_size, offset=params.offset
    )
    return Page.build(
        [ScreeningSessionRead.model_validate(r) for r in rows], total, params
    )


@router.get("/{session_id}", response_model=ScreeningSessionDetail)
def get_screening(
    session_id: uuid.UUID, access: CanViewScreening, db: DbSession
) -> ScreeningSessionDetail:
    """Full workflow snapshot — enough for a client to resume the session."""
    service = ScreeningService(db)
    snapshot = service.workflow_snapshot(session_id)
    session = snapshot["session"]
    access.authorize_patient(session.patient_id)

    quality = service.quality.for_session(session_id)
    return ScreeningSessionDetail(
        **ScreeningSessionRead.model_validate(session).model_dump(),
        state_label=_label(session.state),
        available_transitions=snapshot["available_transitions"],
        is_terminal=is_terminal(session.state),
        patient=PatientRead.model_validate(service.patients.get(session.patient_id)),
        images=[RetinalImageRead.model_validate(i) for i in snapshot["images"]],
        quality=[QualityAssessmentRead.model_validate(q) for q in quality],
        results=[InferenceResultRead.model_validate(r) for r in snapshot["results"]],
        risk=(
            RiskAssessmentRead.model_validate(snapshot["risk"])
            if snapshot["risk"]
            else None
        ),
        referral=(
            ReferralRead.model_validate(snapshot["referral"])
            if snapshot["referral"]
            else None
        ),
    )


# --------------------------------------------------------------------------- #
# Capture + quality gate
# --------------------------------------------------------------------------- #
@router.post("/{session_id}/capture", response_model=CaptureResponse)
async def capture_eye(
    session_id: uuid.UUID,
    access: CanScreen,
    db: DbSession,
    file: Annotated[UploadFile, File(description="Retinal capture (JPEG/PNG/WebP).")],
    eye_side: Annotated[EyeSide, Form()],
    local_id: Annotated[str | None, Form()] = None,
    captured_offline: Annotated[bool, Form()] = False,
) -> CaptureResponse:
    """Store a capture and run the quality gate in one step."""
    service = ScreeningService(db)
    access.authorize_patient(service.get(session_id).patient_id)

    outcome = service.capture_eye(
        session_id=session_id,
        eye_side=eye_side,
        data=await file.read(),
        actor=access.user,
        local_id=local_id,
        captured_offline=captured_offline,
    )
    return CaptureResponse(
        image=RetinalImageRead.model_validate(outcome.image),
        quality=QualityAssessmentRead.model_validate(outcome.quality),
        retake_required=outcome.retake_required,
        session_state=outcome.session_state,
        state_label=_label(outcome.session_state),
    )


@router.post("/{session_id}/retake", response_model=ScreeningSessionRead)
def request_retake(
    session_id: uuid.UUID, payload: RetakeRequest, access: CanScreen, db: DbSession
) -> ScreeningSessionRead:
    service = ScreeningService(db)
    access.authorize_patient(service.get(session_id).patient_id)
    session = service.request_retake(session_id, payload.eye_side, actor=access.user)
    return ScreeningSessionRead.model_validate(session)


@router.post("/{session_id}/ready", response_model=ScreeningSessionRead)
def mark_ready(
    session_id: uuid.UUID, access: CanScreen, db: DbSession
) -> ScreeningSessionRead:
    """Proceed with the captures obtained so far (e.g. single-eye screening)."""
    service = ScreeningService(db)
    access.authorize_patient(service.get(session_id).patient_id)
    return ScreeningSessionRead.model_validate(service.mark_ready_for_inference(session_id))


@router.get("/{session_id}/quality", response_model=list[QualityAssessmentRead])
def get_quality(
    session_id: uuid.UUID, access: CanViewScreening, db: DbSession
) -> list[QualityAssessmentRead]:
    service = ScreeningService(db)
    access.authorize_patient(service.get(session_id).patient_id)
    return [
        QualityAssessmentRead.model_validate(q) for q in service.quality.for_session(session_id)
    ]


# --------------------------------------------------------------------------- #
# Inference / explanation / risk / referral
# --------------------------------------------------------------------------- #
@router.post("/{session_id}/inference", response_model=InferenceRunResponse)
def run_inference(
    session_id: uuid.UUID,
    access: CanInfer,
    db: DbSession,
    force: bool = Query(default=False, description="Re-run even if a result exists."),
) -> InferenceRunResponse:
    """Run AI screening. Output is decision support, never a diagnosis."""
    service = ScreeningService(db)
    access.authorize_patient(service.get(session_id).patient_id)

    outcome = service.run_inference(session_id, actor=access.user, force=force)
    return InferenceRunResponse(
        results=[InferenceResultRead.model_validate(r) for r in outcome["results"]],
        worst=(
            InferenceResultRead.model_validate(outcome["worst"])
            if outcome["worst"]
            else None
        ),
        risk=(
            RiskAssessmentRead.model_validate(outcome["risk"]) if outcome["risk"] else None
        ),
        quality_blocked=outcome["quality_blocked"],
        model_status=service.inference.provider_status(),
        disclaimer=AI_DISCLAIMER,
    )


@router.get("/{session_id}/results", response_model=list[InferenceResultRead])
def get_results(
    session_id: uuid.UUID, access: CanViewScreening, db: DbSession
) -> list[InferenceResultRead]:
    service = ScreeningService(db)
    access.authorize_patient(service.get(session_id).patient_id)
    return [
        InferenceResultRead.model_validate(r)
        for r in service.inference.results_for_session(session_id)
    ]


@router.get(
    "/{session_id}/explanations",
    response_model=list[ExplanationWithUrls],
)
def get_explanations(
    session_id: uuid.UUID, access: CanViewScreening, db: DbSession
) -> list[ExplanationWithUrls]:
    """Grad-CAM saliency for each result, with signed image URLs."""
    service = ScreeningService(db)
    access.authorize_patient(service.get(session_id).patient_id)
    storage = get_storage_provider()

    explanations: list[ExplanationWithUrls] = []
    for result in service.inference.results_for_session(session_id):
        explanation = service.inference.explanation_for(result.id)
        if explanation is None:
            continue
        explanations.append(
            ExplanationWithUrls(
                **{
                    k: v
                    for k, v in explanation.__dict__.items()
                    if k
                    in {
                        "id",
                        "inference_result_id",
                        "method",
                        "affected_regions",
                        "model_version",
                        "is_development_model",
                        "created_at",
                    }
                },
                heatmap_url=(
                    storage.generate_signed_url(explanation.heatmap_storage_key)
                    if explanation.heatmap_storage_key
                    else None
                ),
                overlay_url=(
                    storage.generate_signed_url(explanation.overlay_storage_key)
                    if explanation.overlay_storage_key
                    else None
                ),
                caveat=GRADCAM_CAVEAT,
            )
        )
    return explanations


@router.get("/{session_id}/risk", response_model=RiskAssessmentRead | None)
def get_risk(
    session_id: uuid.UUID, access: CanViewScreening, db: DbSession
) -> RiskAssessmentRead | None:
    service = ScreeningService(db)
    access.authorize_patient(service.get(session_id).patient_id)
    risk = service.latest_risk(session_id)
    return RiskAssessmentRead.model_validate(risk) if risk else None


@router.post("/{session_id}/referral", response_model=ReferralRead | None)
def create_referral(
    session_id: uuid.UUID,
    access: Annotated[Access, Depends(require_permission(Permission.REFERRAL_CREATE))],
    db: DbSession,
) -> ReferralRead | None:
    service = ScreeningService(db)
    access.authorize_patient(service.get(session_id).patient_id)
    referral = service.create_referral(session_id, actor=access.user)
    return ReferralRead.model_validate(referral) if referral else None


@router.post("/{session_id}/submit-review", response_model=MessageResponse)
def submit_for_review(
    session_id: uuid.UUID, access: CanScreen, db: DbSession
) -> MessageResponse:
    service = ScreeningService(db)
    access.authorize_patient(service.get(session_id).patient_id)
    service.submit_for_review(session_id, actor=access.user)
    return MessageResponse(message="Sent for clinical review.")


# --------------------------------------------------------------------------- #
# Exit points
# --------------------------------------------------------------------------- #
@router.post("/{session_id}/complete", response_model=ScreeningSessionRead)
def complete_screening(
    session_id: uuid.UUID, access: CanScreen, db: DbSession
) -> ScreeningSessionRead:
    service = ScreeningService(db)
    access.authorize_patient(service.get(session_id).patient_id)
    return ScreeningSessionRead.model_validate(
        service.complete(session_id, actor=access.user)
    )


@router.post("/{session_id}/cancel", response_model=ScreeningSessionRead)
def cancel_screening(
    session_id: uuid.UUID, payload: CancelRequest, access: CanScreen, db: DbSession
) -> ScreeningSessionRead:
    """Always available while the screening is open."""
    service = ScreeningService(db)
    access.authorize_patient(service.get(session_id).patient_id)
    return ScreeningSessionRead.model_validate(
        service.cancel(session_id, reason=payload.reason, actor=access.user)
    )


@router.post("/{session_id}/save-exit", response_model=ScreeningSessionRead)
def save_and_exit(
    session_id: uuid.UUID, access: CanScreen, db: DbSession
) -> ScreeningSessionRead:
    """Persist progress and leave; the session stays resumable."""
    service = ScreeningService(db)
    access.authorize_patient(service.get(session_id).patient_id)
    return ScreeningSessionRead.model_validate(service.save_and_exit(session_id))

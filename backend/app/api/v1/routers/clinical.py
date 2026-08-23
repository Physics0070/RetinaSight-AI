"""Clinical review, referrals and follow-ups — the doctor's workspace API."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from app.api.deps import Access, DbSession, require_permission
from app.core.errors import NotFoundError
from app.domain.enums import FollowUpStatus, Permission, ReviewStatus
from app.models.patient import Patient
from app.models.screening import (
    FollowUp,
    InferenceResult,
    QualityAssessment,
    Referral,
    RiskAssessment,
    ScreeningSession,
)
from app.schemas.common import MessageResponse, Page, PaginationParams
from app.schemas.screening import (
    ClinicalReviewRead,
    FollowUpCreate,
    FollowUpRead,
    InferenceResultRead,
    PatientRead,
    ReferralRead,
    ReviewCompleteRequest,
    RiskAssessmentRead,
    RiskQueueItem,
    ScreeningSessionRead,
)
from app.services.review_service import ReviewRepository, ReviewService
from app.services.screening_service import ScreeningService

router = APIRouter(tags=["clinical"])

CanReview = Annotated[Access, Depends(require_permission(Permission.CLINICAL_REVIEW))]
CanViewReferrals = Annotated[Access, Depends(require_permission(Permission.REFERRAL_VIEW))]
CanManageFollowUps = Annotated[
    Access, Depends(require_permission(Permission.FOLLOWUP_MANAGE))
]


# --------------------------------------------------------------------------- #
# Risk queue + reviews
# --------------------------------------------------------------------------- #
@router.get("/reviews/queue", response_model=Page[RiskQueueItem])
def risk_queue(
    access: CanReview,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    review_status: str | None = Query(default=ReviewStatus.PENDING.value, alias="status"),
    risk_level: str | None = Query(default=None),
    mine_only: bool = Query(default=False),
) -> Page[RiskQueueItem]:
    """Cases awaiting attention, most urgent first."""
    from app.services.inference_service import severity_rank

    repo = ReviewRepository(db)
    params = PaginationParams(page=page, page_size=page_size)
    stmt = repo.queue_statement(
        status=review_status,
        risk_level=risk_level,
        reviewer_id=access.user.id if mine_only else None,
    )

    from sqlalchemy import func

    total = int(
        db.execute(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        ).scalar_one()
    )
    rows = db.execute(stmt.limit(params.page_size).offset(params.offset)).all()

    items: list[RiskQueueItem] = []
    for review, risk in rows:
        session = db.get(ScreeningSession, review.session_id)
        patient = db.get(Patient, review.patient_id)
        if session is None or patient is None:
            continue

        results = list(
            db.execute(
                select(InferenceResult).where(
                    InferenceResult.session_id == session.id,
                    InferenceResult.category.is_not(None),
                )
            ).scalars().all()
        )
        worst = max(results, key=lambda r: severity_rank(r.category)) if results else None
        assessments = list(
            db.execute(
                select(QualityAssessment).where(QualityAssessment.session_id == session.id)
            ).scalars().all()
        )

        items.append(
            RiskQueueItem(
                review=ClinicalReviewRead.model_validate(review),
                session=ScreeningSessionRead.model_validate(session),
                patient=PatientRead.model_validate(patient),
                risk=RiskAssessmentRead.model_validate(risk) if risk else None,
                worst_result=(
                    InferenceResultRead.model_validate(worst) if worst else None
                ),
                quality_acceptable=bool(assessments)
                and all(a.is_acceptable for a in assessments),
            )
        )

    return Page.build(items, total, params)


@router.get("/reviews/{review_id}", response_model=ClinicalReviewRead)
def get_review(review_id: uuid.UUID, access: CanReview, db: DbSession) -> ClinicalReviewRead:
    review = ReviewService(db).get(review_id)
    access.authorize_patient(review.patient_id)
    return ClinicalReviewRead.model_validate(review)


@router.post("/reviews/{review_id}/claim", response_model=ClinicalReviewRead)
def claim_review(
    review_id: uuid.UUID, access: CanReview, db: DbSession
) -> ClinicalReviewRead:
    """Take ownership so two clinicians don't review the same case."""
    service = ReviewService(db)
    access.authorize_patient(service.get(review_id).patient_id)
    return ClinicalReviewRead.model_validate(service.claim(review_id, reviewer=access.user))


@router.post("/reviews/{review_id}/release", response_model=ClinicalReviewRead)
def release_review(
    review_id: uuid.UUID, access: CanReview, db: DbSession
) -> ClinicalReviewRead:
    """Exit without deciding — the case returns to the queue."""
    service = ReviewService(db)
    access.authorize_patient(service.get(review_id).patient_id)
    return ClinicalReviewRead.model_validate(service.release(review_id))


@router.post("/reviews/{review_id}/complete", response_model=ClinicalReviewRead)
def complete_review(
    review_id: uuid.UUID,
    payload: ReviewCompleteRequest,
    access: CanReview,
    db: DbSession,
) -> ClinicalReviewRead:
    """Record the clinician's decision, optionally scheduling a follow-up."""
    service = ReviewService(db)
    review = service.get(review_id)
    access.authorize_patient(review.patient_id)

    completed = service.complete(
        review_id,
        reviewer=access.user,
        decision=payload.decision,
        clinician_category=(
            payload.clinician_category.value if payload.clinician_category else None
        ),
        notes=payload.notes,
        agrees_with_ai=payload.agrees_with_ai,
    )

    if payload.follow_up_due is not None:
        ScreeningService(db).create_follow_up(
            session_id=completed.session_id,
            due_date=payload.follow_up_due,
            instructions=payload.follow_up_instructions,
            review_id=completed.id,
            actor=access.user,
        )

    return ClinicalReviewRead.model_validate(completed)


# --------------------------------------------------------------------------- #
# Referrals
# --------------------------------------------------------------------------- #
@router.get("/referrals", response_model=Page[ReferralRead])
def list_referrals(
    access: CanViewReferrals,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    referral_status: str | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    patient_id: uuid.UUID | None = Query(default=None),
) -> Page[ReferralRead]:
    params = PaginationParams(page=page, page_size=page_size)
    stmt = select(Referral)
    if referral_status:
        stmt = stmt.where(Referral.status == referral_status)
    if priority:
        stmt = stmt.where(Referral.priority == priority)
    if patient_id is not None:
        access.authorize_patient(patient_id)
        stmt = stmt.where(Referral.patient_id == patient_id)
    stmt = stmt.order_by(Referral.created_at.desc())

    from sqlalchemy import func

    total = int(
        db.execute(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        ).scalar_one()
    )
    rows = db.execute(stmt.limit(params.page_size).offset(params.offset)).scalars().all()
    return Page.build([ReferralRead.model_validate(r) for r in rows], total, params)


@router.get("/referrals/{referral_id}", response_model=ReferralRead)
def get_referral(
    referral_id: uuid.UUID, access: CanViewReferrals, db: DbSession
) -> ReferralRead:
    referral = db.get(Referral, referral_id)
    if referral is None:
        raise NotFoundError("Referral not found.")
    access.authorize_patient(referral.patient_id)
    return ReferralRead.model_validate(referral)


# --------------------------------------------------------------------------- #
# Follow-ups
# --------------------------------------------------------------------------- #
@router.get("/followups", response_model=Page[FollowUpRead])
def list_follow_ups(
    access: Access,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    follow_up_status: str | None = Query(default=None, alias="status"),
    due_before: date | None = Query(default=None),
    patient_id: uuid.UUID | None = Query(default=None),
) -> Page[FollowUpRead]:
    params = PaginationParams(page=page, page_size=page_size)
    stmt = select(FollowUp)

    if patient_id is not None:
        access.authorize_patient(patient_id)
        stmt = stmt.where(FollowUp.patient_id == patient_id)
    elif not access.has(Permission.PATIENT_VIEW):
        # A patient may only ever see their own follow-ups.
        stmt = stmt.where(FollowUp.patient_id == access.resolve_own_patient().id)

    if follow_up_status:
        stmt = stmt.where(FollowUp.status == follow_up_status)
    if due_before is not None:
        stmt = stmt.where(FollowUp.due_date <= due_before)
    stmt = stmt.order_by(FollowUp.due_date.asc())

    from sqlalchemy import func

    total = int(
        db.execute(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        ).scalar_one()
    )
    rows = db.execute(stmt.limit(params.page_size).offset(params.offset)).scalars().all()
    return Page.build([FollowUpRead.model_validate(r) for r in rows], total, params)


@router.post(
    "/followups", response_model=FollowUpRead, status_code=status.HTTP_201_CREATED
)
def create_follow_up(
    payload: FollowUpCreate, access: CanManageFollowUps, db: DbSession
) -> FollowUpRead:
    service = ScreeningService(db)
    access.authorize_patient(service.get(payload.session_id).patient_id)
    follow_up = service.create_follow_up(
        session_id=payload.session_id,
        due_date=payload.due_date,
        instructions=payload.instructions,
        actor=access.user,
    )
    return FollowUpRead.model_validate(follow_up)


@router.post("/followups/{follow_up_id}/complete", response_model=FollowUpRead)
def complete_follow_up(
    follow_up_id: uuid.UUID, access: CanManageFollowUps, db: DbSession
) -> FollowUpRead:
    from datetime import datetime, timezone

    follow_up = db.get(FollowUp, follow_up_id)
    if follow_up is None:
        raise NotFoundError("Follow-up not found.")
    access.authorize_patient(follow_up.patient_id)

    follow_up.status = FollowUpStatus.COMPLETED.value
    follow_up.completed_at = datetime.now(tz=timezone.utc)
    db.commit()
    return FollowUpRead.model_validate(follow_up)


@router.post("/followups/{follow_up_id}/cancel", response_model=MessageResponse)
def cancel_follow_up(
    follow_up_id: uuid.UUID, access: CanManageFollowUps, db: DbSession
) -> MessageResponse:
    follow_up = db.get(FollowUp, follow_up_id)
    if follow_up is None:
        raise NotFoundError("Follow-up not found.")
    access.authorize_patient(follow_up.patient_id)

    follow_up.status = FollowUpStatus.CANCELLED.value
    db.commit()
    return MessageResponse(message="Follow-up cancelled.")

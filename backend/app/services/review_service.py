"""Clinical review: the doctor's decision on a screening.

The clinician is the decision-maker. AI output is context, never the verdict —
which is why the review records the clinician's own category alongside whether
they agreed with the model.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, WorkflowError
from app.domain.enums import (
    AuditAction,
    ReferralStatus,
    ReviewDecision,
    ReviewStatus,
    RiskLevel,
    ScreeningState,
)
from app.models.identity import User
from app.models.organization import Doctor
from app.models.screening import (
    ClinicalReview,
    InferenceResult,
    Referral,
    RiskAssessment,
    ScreeningSession,
)
from app.repositories.base import BaseRepository
from app.services.audit_service import AuditService
from app.services.screening_state_machine import assert_transition


class ReviewRepository(BaseRepository[ClinicalReview]):
    model = ClinicalReview

    def queue_statement(
        self,
        *,
        status: str | None = None,
        risk_level: str | None = None,
        reviewer_id: uuid.UUID | None = None,
    ) -> Select:
        """The risk queue, ordered so the most urgent cases surface first."""
        severity = {
            RiskLevel.URGENT.value: 0,
            RiskLevel.HIGH.value: 1,
            RiskLevel.MODERATE.value: 2,
            RiskLevel.LOW.value: 3,
        }
        stmt = (
            select(ClinicalReview, RiskAssessment)
            .join(
                RiskAssessment,
                RiskAssessment.session_id == ClinicalReview.session_id,
                isouter=True,
            )
        )
        if status:
            stmt = stmt.where(ClinicalReview.status == status)
        if risk_level:
            stmt = stmt.where(RiskAssessment.risk_level == risk_level)
        if reviewer_id is not None:
            stmt = stmt.where(ClinicalReview.reviewer_user_id == reviewer_id)

        ordering = _severity_ordering(severity)
        return stmt.order_by(ordering, ClinicalReview.created_at.asc())


def _severity_ordering(severity: dict[str, int]):  # noqa: ANN201
    from sqlalchemy import case

    return case(severity, value=RiskAssessment.risk_level, else_=99)


class ReviewService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ReviewRepository(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------------ #
    def get(self, review_id: uuid.UUID) -> ClinicalReview:
        review = self.repo.get(review_id)
        if review is None:
            raise NotFoundError("Review not found.")
        return review

    def for_session(self, session_id: uuid.UUID) -> ClinicalReview | None:
        return self.repo.get_by(session_id=session_id)

    def claim(self, review_id: uuid.UUID, *, reviewer: User) -> ClinicalReview:
        """Take ownership of a case so two clinicians don't duplicate work."""
        review = self.get(review_id)
        if review.status == ReviewStatus.COMPLETED.value:
            raise WorkflowError("This case has already been reviewed.")
        review.reviewer_user_id = reviewer.id
        review.status = ReviewStatus.IN_REVIEW.value
        self.db.flush()
        self.db.commit()
        return review

    def release(self, review_id: uuid.UUID) -> ClinicalReview:
        """Return an unfinished case to the queue — an explicit exit point."""
        review = self.get(review_id)
        if review.status == ReviewStatus.COMPLETED.value:
            return review
        review.reviewer_user_id = None
        review.status = ReviewStatus.PENDING.value
        self.db.flush()
        self.db.commit()
        return review

    # ------------------------------------------------------------------ #
    def complete(
        self,
        review_id: uuid.UUID,
        *,
        reviewer: User,
        decision: ReviewDecision,
        clinician_category: str | None = None,
        notes: str | None = None,
        agrees_with_ai: bool | None = None,
    ) -> ClinicalReview:
        review = self.get(review_id)
        if review.status == ReviewStatus.COMPLETED.value:
            raise WorkflowError("This case has already been reviewed.")

        session = self.db.get(ScreeningSession, review.session_id)
        if session is None:
            raise NotFoundError("The screening for this review no longer exists.")

        if agrees_with_ai is None and clinician_category:
            agrees_with_ai = self._matches_ai(review.session_id, clinician_category)

        review.reviewer_user_id = reviewer.id
        review.status = ReviewStatus.COMPLETED.value
        review.decision = decision.value
        review.clinician_category = clinician_category
        review.agrees_with_ai = agrees_with_ai
        review.notes = notes
        review.reviewed_at = datetime.now(tz=timezone.utc)
        self.db.flush()

        if session.state != ScreeningState.DOCTOR_REVIEW.value:
            try:
                assert_transition(session.state, ScreeningState.DOCTOR_REVIEW)
                session.state = ScreeningState.DOCTOR_REVIEW.value
            except WorkflowError:
                # Session already progressed past review; leave its state alone.
                pass

        self._acknowledge_referral(review)

        self.audit.record(
            action=AuditAction.DOCTOR_REVIEWED,
            actor=reviewer,
            resource_type="clinical_review",
            resource_id=review.id,
            context={
                "session_id": str(review.session_id),
                "decision": decision.value,
                "agrees_with_ai": agrees_with_ai,
                # Clinical notes are patient data and stay out of the audit log.
            },
        )
        self.db.commit()
        return review

    def _acknowledge_referral(self, review: ClinicalReview) -> None:
        referral = self.db.execute(
            select(Referral).where(Referral.session_id == review.session_id)
        ).scalars().first()
        if referral and referral.status == ReferralStatus.CREATED.value:
            referral.status = ReferralStatus.ACKNOWLEDGED.value
            referral.acknowledged_at = datetime.now(tz=timezone.utc)
            review.referral_id = referral.id
            self.db.flush()

    def _matches_ai(self, session_id: uuid.UUID, clinician_category: str) -> bool | None:
        from app.services.inference_service import severity_rank

        results = list(
            self.db.execute(
                select(InferenceResult).where(
                    InferenceResult.session_id == session_id,
                    InferenceResult.category.is_not(None),
                )
            ).scalars().all()
        )
        if not results:
            return None
        worst = max(results, key=lambda r: severity_rank(r.category))
        return worst.category == clinician_category

    # ------------------------------------------------------------------ #
    def doctor_profile(self, user: User) -> Doctor | None:
        return self.db.execute(
            select(Doctor).where(Doctor.user_id == user.id)
        ).scalars().first()

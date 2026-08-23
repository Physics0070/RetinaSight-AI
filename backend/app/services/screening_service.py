"""Screening workflow orchestration.

One service owns the clinical workflow loop:

    start -> select patient -> capture -> quality gate -> (retake) ->
    inference -> explanation -> risk -> referral -> review -> follow-up -> complete

Each operation is independently callable and testable, guards its own state
transition, and leaves the session in a state the caller can resume from — so a
device that loses power or connectivity mid-screening can pick up where it
stopped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError, WorkflowError
from app.core.logging import get_logger
from app.domain.enums import (
    AuditAction,
    ConsentType,
    EyeSide,
    FollowUpStatus,
    ReferralStatus,
    ReviewStatus,
    ScreeningState,
    SyncStatus,
)
from app.models.identity import User
from app.models.screening import (
    ClinicalReview,
    FollowUp,
    Referral,
    RetinalImage,
    RiskAssessment,
    ScreeningSession,
)
from app.repositories.screening_repository import (
    RetinalImageRepository,
    ScreeningSessionRepository,
)
from app.services.audit_service import AuditService
from app.services.image_service import ImageService
from app.services.inference_service import InferenceService
from app.services.patient_service import PatientService
from app.services.quality_service import QualityService
from app.services.referral_engine import ReferralEngine
from app.services.risk_engine import RiskEngine, RiskInput
from app.services.screening_state_machine import (
    assert_not_terminal,
    assert_transition,
    available_transitions,
)

logger = get_logger(__name__)


@dataclass
class CaptureOutcome:
    image: RetinalImage
    quality: object
    retake_required: bool
    session_state: str


class ScreeningService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.sessions = ScreeningSessionRepository(db)
        self.images = RetinalImageRepository(db)
        self.audit = AuditService(db)
        self.patients = PatientService(db)
        self.image_service = ImageService(db)
        self.quality = QualityService(db)
        self.inference = InferenceService(db)

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def start_screening(
        self,
        *,
        patient_id: uuid.UUID,
        actor: User | None = None,
        clinic_id: uuid.UUID | None = None,
        local_id: str | None = None,
        captured_offline: bool = False,
    ) -> ScreeningSession:
        # Idempotent for offline replay.
        if local_id:
            existing = self.sessions.get_by_local_id(local_id)
            if existing is not None:
                return existing

        patient = self.patients.get(patient_id)
        if not self.patients.has_consent(patient.id, ConsentType.SCREENING):
            raise ValidationError(
                "Screening consent has not been recorded for this patient."
            )

        session = ScreeningSession(
            local_id=local_id,
            patient_id=patient.id,
            clinic_id=clinic_id or patient.clinic_id,
            conducted_by_user_id=actor.id if actor else None,
            state=ScreeningState.PATIENT_SELECTED.value,
            started_at=datetime.now(tz=timezone.utc),
            captured_offline=captured_offline,
            sync_status=(
                SyncStatus.PENDING.value if captured_offline else SyncStatus.SYNCED.value
            ),
        )
        self.db.add(session)
        self.db.flush()

        self.audit.record(
            action=AuditAction.SCREENING_STARTED,
            actor=actor,
            resource_type="screening_session",
            resource_id=session.id,
            context={"patient_id": str(patient.id)},
        )
        self.db.commit()
        return session

    def get(self, session_id: uuid.UUID) -> ScreeningSession:
        session = self.sessions.get(session_id)
        if session is None:
            raise NotFoundError("Screening session not found.")
        return session

    def _move_to(self, session: ScreeningSession, target: ScreeningState) -> None:
        assert_transition(session.state, target)
        session.state = target.value
        self.db.flush()

    # ------------------------------------------------------------------ #
    # Capture + quality gate
    # ------------------------------------------------------------------ #
    def begin_capture(
        self, session_id: uuid.UUID, eye_side: EyeSide, *, actor: User | None = None
    ) -> ScreeningSession:
        session = self.get(session_id)
        assert_not_terminal(session.state)
        target = (
            ScreeningState.CAPTURE_LEFT_EYE
            if eye_side == EyeSide.LEFT
            else ScreeningState.CAPTURE_RIGHT_EYE
        )
        self._move_to(session, target)
        self.db.commit()
        return session

    def capture_eye(
        self,
        *,
        session_id: uuid.UUID,
        eye_side: EyeSide,
        data: bytes,
        actor: User | None = None,
        local_id: str | None = None,
        captured_offline: bool = False,
    ) -> CaptureOutcome:
        """Store one capture and immediately run the quality gate."""
        session = self.get(session_id)
        assert_not_terminal(session.state)

        capture_state = (
            ScreeningState.CAPTURE_LEFT_EYE
            if eye_side == EyeSide.LEFT
            else ScreeningState.CAPTURE_RIGHT_EYE
        )
        if session.state != capture_state.value:
            self._move_to(session, capture_state)

        image = self.image_service.store_capture(
            session_id=session.id,
            eye_side=eye_side,
            data=data,
            uploaded_by=actor,
            local_id=local_id,
            captured_offline=captured_offline,
        )

        self._move_to(session, ScreeningState.QUALITY_CHECK)
        assessment = self.quality.assess_image(image, actor=actor)

        if assessment.is_acceptable:
            # Ready only when every required eye has an acceptable capture.
            self._move_to(
                session,
                ScreeningState.READY_FOR_INFERENCE
                if self._all_eyes_acceptable(session.id)
                else ScreeningState.CAPTURE_RIGHT_EYE
                if eye_side == EyeSide.LEFT
                else ScreeningState.CAPTURE_LEFT_EYE,
            )
        else:
            self._move_to(session, ScreeningState.RETAKE_REQUIRED)

        self.db.commit()
        return CaptureOutcome(
            image=image,
            quality=assessment,
            retake_required=not assessment.is_acceptable,
            session_state=session.state,
        )

    def request_retake(
        self, session_id: uuid.UUID, eye_side: EyeSide, *, actor: User | None = None
    ) -> ScreeningSession:
        session = self.get(session_id)
        assert_not_terminal(session.state)
        target = (
            ScreeningState.CAPTURE_LEFT_EYE
            if eye_side == EyeSide.LEFT
            else ScreeningState.CAPTURE_RIGHT_EYE
        )
        self._move_to(session, target)
        self.db.commit()
        return session

    def _all_eyes_acceptable(self, session_id: uuid.UUID) -> bool:
        """Both eyes captured with an acceptable image."""
        for side in (EyeSide.LEFT, EyeSide.RIGHT):
            image = self.images.active_for_eye(session_id, side.value)
            if image is None:
                return False
            assessment = self.quality.repo.get_by(image_id=image.id)
            if assessment is None or not assessment.is_acceptable:
                return False
        return True

    def mark_ready_for_inference(self, session_id: uuid.UUID) -> ScreeningSession:
        """Proceed with the captures obtained so far (single-eye screening).

        Idempotent: capturing a second acceptable eye already advances the
        session, so a client that then calls this explicitly must not be met
        with an error about a transition it did not ask for.
        """
        session = self.get(session_id)
        acceptable = [
            image
            for image in self.images.for_session(session_id, active_only=True)
            if (a := self.quality.repo.get_by(image_id=image.id)) and a.is_acceptable
        ]
        if not acceptable:
            raise WorkflowError("No image has passed the quality gate yet.")

        if session.state != ScreeningState.READY_FOR_INFERENCE.value:
            self._move_to(session, ScreeningState.READY_FOR_INFERENCE)
            self.db.commit()
        return session

    # ------------------------------------------------------------------ #
    # Inference -> risk -> referral
    # ------------------------------------------------------------------ #
    def run_inference(
        self, session_id: uuid.UUID, *, actor: User | None = None, force: bool = False
    ) -> dict:
        session = self.get(session_id)
        assert_not_terminal(session.state)

        if session.state != ScreeningState.READY_FOR_INFERENCE.value:
            self._move_to(session, ScreeningState.READY_FOR_INFERENCE)
        self._move_to(session, ScreeningState.INFERENCE_RUNNING)
        self.db.commit()

        try:
            outcome = self.inference.run_for_session(session.id, actor=actor, force=force)
        except Exception:
            session.state = ScreeningState.ERROR.value
            self.db.commit()
            raise

        session = self.get(session_id)
        self._move_to(session, ScreeningState.RESULT_AVAILABLE)
        if any(self.inference.explanation_for(r.id) for r in outcome.results):
            self._move_to(session, ScreeningState.EXPLANATION_AVAILABLE)
        self.db.commit()

        risk = self.calculate_risk(session.id, actor=actor)
        return {
            "results": outcome.results,
            "worst": outcome.worst,
            "quality_blocked": outcome.quality_blocked,
            "risk": risk,
        }

    def calculate_risk(
        self, session_id: uuid.UUID, *, actor: User | None = None
    ) -> RiskAssessment:
        session = self.get(session_id)
        results = self.inference.results_for_session(session.id)
        completed = [r for r in results if r.category]
        if not completed:
            raise WorkflowError("No screening result is available to assess.")

        from app.services.inference_service import severity_rank

        worst = max(completed, key=lambda r: severity_rank(r.category))
        quality_ok = self._all_captures_acceptable(session.id)

        outcome = RiskEngine(self.db).evaluate(
            RiskInput(
                category=worst.category,
                confidence=worst.confidence,
                quality_acceptable=quality_ok,
                is_development_model=worst.is_development_model,
                patient_context=self._patient_context(session.patient_id),
            )
        )

        assessment = RiskAssessment(
            session_id=session.id,
            inference_result_id=worst.id,
            risk_level=outcome.risk_level,
            priority=outcome.risk_level,
            reason=outcome.reason,
            recommended_action=outcome.recommended_action,
            requires_clinician_review=outcome.requires_clinician_review,
            rule_id=outcome.rule_id,
            rules_snapshot={**outcome.rules_snapshot, "notes": outcome.notes},
        )
        self.db.add(assessment)
        self.db.flush()

        if outcome.requires_clinician_review:
            self._ensure_review_pending(session)

        self.audit.record(
            action=AuditAction.RISK_ASSESSED,
            actor=actor,
            resource_type="risk_assessment",
            resource_id=assessment.id,
            context={
                "session_id": str(session.id),
                "risk_level": outcome.risk_level,
                "rule_id": outcome.rule_id,
            },
        )
        self.db.commit()
        return assessment

    def _all_captures_acceptable(self, session_id: uuid.UUID) -> bool:
        images = self.images.for_session(session_id, active_only=True)
        if not images:
            return False
        return all(
            (a := self.quality.repo.get_by(image_id=image.id)) and a.is_acceptable
            for image in images
        )

    def _patient_context(self, patient_id: uuid.UUID) -> dict:
        patient = self.patients.get(patient_id)
        return {
            "has_diabetes": patient.has_diabetes,
            "diabetes_duration_years": patient.diabetes_duration_years,
        }

    def create_referral(
        self, session_id: uuid.UUID, *, actor: User | None = None
    ) -> Referral | None:
        session = self.get(session_id)
        assessment = self.latest_risk(session.id)
        if assessment is None:
            raise WorkflowError("Risk must be assessed before creating a referral.")

        decision = ReferralEngine(self.db).decide(
            risk_level=assessment.risk_level,
            reason=assessment.reason,
            origin_clinic_id=session.clinic_id,
        )
        if not decision.should_create_referral:
            return None

        existing = self.db.execute(
            select(Referral).where(Referral.session_id == session.id)
        ).scalars().first()
        if existing is not None:
            return existing

        if session.state != ScreeningState.REFERRAL_PENDING.value:
            self._move_to(session, ScreeningState.REFERRAL_PENDING)

        referral = Referral(
            session_id=session.id,
            patient_id=session.patient_id,
            risk_assessment_id=assessment.id,
            to_clinic_id=decision.routed_clinic_id,
            assigned_doctor_id=decision.routed_doctor_id,
            priority=decision.priority,
            status=ReferralStatus.CREATED.value,
            reason=decision.reason or assessment.reason,
            created_by_user_id=actor.id if actor else None,
        )
        self.db.add(referral)
        self.db.flush()
        self._move_to(session, ScreeningState.REFERRAL_CREATED)

        self.audit.record(
            action=AuditAction.REFERRAL_CREATED,
            actor=actor,
            resource_type="referral",
            resource_id=referral.id,
            context={"session_id": str(session.id), "priority": decision.priority},
        )
        self.db.commit()
        return referral

    def latest_risk(self, session_id: uuid.UUID) -> RiskAssessment | None:
        return self.db.execute(
            select(RiskAssessment)
            .where(RiskAssessment.session_id == session_id)
            .order_by(RiskAssessment.created_at.desc())
            .limit(1)
        ).scalars().first()

    # ------------------------------------------------------------------ #
    # Review handoff
    # ------------------------------------------------------------------ #
    def _ensure_review_pending(self, session: ScreeningSession) -> ClinicalReview:
        existing = self.db.execute(
            select(ClinicalReview).where(ClinicalReview.session_id == session.id)
        ).scalars().first()
        if existing is not None:
            return existing
        review = ClinicalReview(
            session_id=session.id,
            patient_id=session.patient_id,
            status=ReviewStatus.PENDING.value,
        )
        self.db.add(review)
        self.db.flush()
        return review

    def submit_for_review(
        self, session_id: uuid.UUID, *, actor: User | None = None
    ) -> ClinicalReview:
        session = self.get(session_id)
        review = self._ensure_review_pending(session)
        if session.state != ScreeningState.DOCTOR_REVIEW.value:
            self._move_to(session, ScreeningState.DOCTOR_REVIEW)
        self.db.commit()
        return review

    # ------------------------------------------------------------------ #
    # Exit points
    # ------------------------------------------------------------------ #
    def complete(
        self, session_id: uuid.UUID, *, actor: User | None = None
    ) -> ScreeningSession:
        session = self.get(session_id)
        assert_not_terminal(session.state)
        self._move_to(session, ScreeningState.COMPLETED)
        session.completed_at = datetime.now(tz=timezone.utc)
        self.db.commit()
        return session

    def cancel(
        self, session_id: uuid.UUID, *, reason: str | None = None, actor: User | None = None
    ) -> ScreeningSession:
        """Always available while a screening is open — never trap the user."""
        session = self.get(session_id)
        assert_not_terminal(session.state)
        self._move_to(session, ScreeningState.CANCELLED)
        session.cancelled_reason = (reason or "").strip()[:255] or None
        self.audit.record(
            action=AuditAction.SCREENING_STARTED,
            actor=actor,
            resource_type="screening_session",
            resource_id=session.id,
            context={"event": "cancelled", "reason": session.cancelled_reason or ""},
        )
        self.db.commit()
        return session

    def save_and_exit(self, session_id: uuid.UUID) -> ScreeningSession:
        """Persist progress and leave the session resumable."""
        session = self.get(session_id)
        self.db.commit()
        return session

    # ------------------------------------------------------------------ #
    def workflow_snapshot(self, session_id: uuid.UUID) -> dict:
        """Everything a client needs to resume or render this workflow."""
        session = self.get(session_id)
        images = self.images.for_session(session.id)
        results = self.inference.results_for_session(session.id)
        risk = self.latest_risk(session.id)
        referral = self.db.execute(
            select(Referral).where(Referral.session_id == session.id)
        ).scalars().first()
        review = self.db.execute(
            select(ClinicalReview).where(ClinicalReview.session_id == session.id)
        ).scalars().first()

        return {
            "session": session,
            "images": images,
            "results": results,
            "risk": risk,
            "referral": referral,
            "review": review,
            "available_transitions": available_transitions(session.state),
        }

    # ------------------------------------------------------------------ #
    def create_follow_up(
        self,
        *,
        session_id: uuid.UUID,
        due_date,
        instructions: str | None = None,
        review_id: uuid.UUID | None = None,
        actor: User | None = None,
    ) -> FollowUp:
        session = self.get(session_id)
        follow_up = FollowUp(
            patient_id=session.patient_id,
            session_id=session.id,
            review_id=review_id,
            due_date=due_date,
            status=FollowUpStatus.SCHEDULED.value,
            instructions=instructions,
            created_by_user_id=actor.id if actor else None,
        )
        self.db.add(follow_up)
        self.db.flush()

        if session.state == ScreeningState.DOCTOR_REVIEW.value:
            self._move_to(session, ScreeningState.FOLLOW_UP)

        self.audit.record(
            action=AuditAction.FOLLOWUP_CREATED,
            actor=actor,
            resource_type="follow_up",
            resource_id=follow_up.id,
            context={"session_id": str(session.id), "due_date": str(due_date)},
        )
        self.db.commit()
        return follow_up

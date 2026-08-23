"""Screening workflow: state machine, orchestration, and the full end-to-end flow."""

from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.errors import ValidationError, WorkflowError
from app.domain.enums import (
    ConsentType,
    EyeSide,
    ReviewDecision,
    RoleName,
    ScreeningState,
)
from app.services.config_service import ConfigService
from app.services.patient_service import PatientService
from app.services.review_service import ReviewService
from app.services.screening_service import ScreeningService
from app.services.screening_state_machine import (
    TERMINAL_STATES,
    TRANSITIONS,
    assert_transition,
    available_transitions,
    can_transition,
    is_terminal,
)
from app.storage.local import LocalFileSystemStorage
from tests.test_ml_pipeline import synthetic_fundus


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def storage_root(monkeypatch, tmp_path):
    provider = LocalFileSystemStorage(root=str(tmp_path / "object-store"))
    from app.storage import factory

    monkeypatch.setattr(factory, "_provider", provider)
    monkeypatch.setattr("app.services.image_service.get_storage_provider", lambda: provider)
    monkeypatch.setattr("app.services.quality_service.get_storage_provider", lambda: provider)
    monkeypatch.setattr("app.services.inference_service.get_storage_provider", lambda: provider)
    return provider


@pytest.fixture
def seeded_config(db_session: Session) -> ConfigService:
    service = ConfigService(db_session)
    service.seed_defaults()
    db_session.commit()
    return service


@pytest.fixture
def consented_patient(db_session: Session, make_user):
    worker = make_user("hw@example.com", RoleName.HEALTH_WORKER)
    patient = PatientService(db_session).register(
        full_name="Consented Patient",
        has_diabetes=True,
        actor=worker,
        consents={ConsentType.SCREENING.value: True},
    )
    return patient, worker


# --------------------------------------------------------------------------- #
# State machine
# --------------------------------------------------------------------------- #
def test_happy_path_transitions_are_legal() -> None:
    path = [
        ScreeningState.IDLE,
        ScreeningState.PATIENT_SELECTED,
        ScreeningState.CAPTURE_LEFT_EYE,
        ScreeningState.QUALITY_CHECK,
        ScreeningState.READY_FOR_INFERENCE,
        ScreeningState.INFERENCE_RUNNING,
        ScreeningState.RESULT_AVAILABLE,
        ScreeningState.EXPLANATION_AVAILABLE,
        ScreeningState.REFERRAL_PENDING,
        ScreeningState.REFERRAL_CREATED,
        ScreeningState.DOCTOR_REVIEW,
        ScreeningState.FOLLOW_UP,
        ScreeningState.COMPLETED,
    ]
    for current, target in zip(path, path[1:]):
        assert can_transition(current, target), f"{current} -> {target} should be legal"


def test_illegal_transitions_are_refused() -> None:
    # Screening before any image has been captured.
    with pytest.raises(WorkflowError):
        assert_transition(ScreeningState.IDLE, ScreeningState.INFERENCE_RUNNING)
    # Reviewing a session that never produced a result.
    with pytest.raises(WorkflowError):
        assert_transition(ScreeningState.PATIENT_SELECTED, ScreeningState.DOCTOR_REVIEW)


def test_terminal_states_have_no_exits() -> None:
    for state in TERMINAL_STATES:
        assert TRANSITIONS[state] == set()
        assert is_terminal(state)


def test_every_open_state_offers_an_exit() -> None:
    """No state may trap the user."""
    for state, targets in TRANSITIONS.items():
        if state in TERMINAL_STATES:
            continue
        assert targets & {ScreeningState.CANCELLED, ScreeningState.COMPLETED}, (
            f"{state.value} offers no way out"
        )


def test_quality_failure_routes_to_retake() -> None:
    assert can_transition(ScreeningState.QUALITY_CHECK, ScreeningState.RETAKE_REQUIRED)
    assert can_transition(ScreeningState.RETAKE_REQUIRED, ScreeningState.CAPTURE_LEFT_EYE)


def test_unknown_state_is_rejected() -> None:
    with pytest.raises(WorkflowError):
        available_transitions("not_a_state")


# --------------------------------------------------------------------------- #
# Consent gate
# --------------------------------------------------------------------------- #
def test_screening_requires_recorded_consent(db_session: Session, make_user) -> None:
    worker = make_user("noconsent@example.com", RoleName.HEALTH_WORKER)
    patient = PatientService(db_session).register(
        full_name="Unconsented Patient", actor=worker
    )

    with pytest.raises(ValidationError, match="consent"):
        ScreeningService(db_session).start_screening(
            patient_id=patient.id, actor=worker
        )


def test_screening_starts_once_consent_is_recorded(
    db_session: Session, consented_patient
) -> None:
    patient, worker = consented_patient

    session = ScreeningService(db_session).start_screening(
        patient_id=patient.id, actor=worker
    )

    assert session.state == ScreeningState.PATIENT_SELECTED.value


def test_repeated_start_with_same_local_id_is_idempotent(
    db_session: Session, consented_patient
) -> None:
    patient, worker = consented_patient
    service = ScreeningService(db_session)

    first = service.start_screening(
        patient_id=patient.id, actor=worker, local_id="device-session-1"
    )
    second = service.start_screening(
        patient_id=patient.id, actor=worker, local_id="device-session-1"
    )

    assert first.id == second.id


# --------------------------------------------------------------------------- #
# Capture + quality gate
# --------------------------------------------------------------------------- #
def test_good_capture_advances_the_workflow(
    db_session: Session, consented_patient, storage_root, seeded_config
) -> None:
    patient, worker = consented_patient
    service = ScreeningService(db_session)
    session = service.start_screening(patient_id=patient.id, actor=worker)

    outcome = service.capture_eye(
        session_id=session.id,
        eye_side=EyeSide.LEFT,
        data=synthetic_fundus(),
        actor=worker,
    )

    assert outcome.retake_required is False
    assert outcome.quality.is_acceptable is True
    assert outcome.session_state == ScreeningState.CAPTURE_RIGHT_EYE.value


def test_poor_capture_forces_a_retake(
    db_session: Session, consented_patient, storage_root, seeded_config
) -> None:
    patient, worker = consented_patient
    service = ScreeningService(db_session)
    session = service.start_screening(patient_id=patient.id, actor=worker)

    outcome = service.capture_eye(
        session_id=session.id,
        eye_side=EyeSide.LEFT,
        data=synthetic_fundus(blur=True),
        actor=worker,
    )

    assert outcome.retake_required is True
    assert outcome.session_state == ScreeningState.RETAKE_REQUIRED.value
    assert outcome.quality.recommendations


def test_inference_is_blocked_until_quality_passes(
    db_session: Session, consented_patient, storage_root, seeded_config
) -> None:
    """A rejected image must never reach the model."""
    patient, worker = consented_patient
    service = ScreeningService(db_session)
    session = service.start_screening(patient_id=patient.id, actor=worker)
    service.capture_eye(
        session_id=session.id,
        eye_side=EyeSide.LEFT,
        data=synthetic_fundus(blur=True),
        actor=worker,
    )

    with pytest.raises(WorkflowError):
        service.run_inference(session.id, actor=worker)


def test_both_eyes_captured_makes_session_ready(
    db_session: Session, consented_patient, storage_root, seeded_config
) -> None:
    patient, worker = consented_patient
    service = ScreeningService(db_session)
    session = service.start_screening(patient_id=patient.id, actor=worker)

    service.capture_eye(
        session_id=session.id, eye_side=EyeSide.LEFT, data=synthetic_fundus(), actor=worker
    )
    outcome = service.capture_eye(
        session_id=session.id,
        eye_side=EyeSide.RIGHT,
        data=synthetic_fundus(size=328),
        actor=worker,
    )

    assert outcome.session_state == ScreeningState.READY_FOR_INFERENCE.value


# --------------------------------------------------------------------------- #
# Inference -> risk -> referral
# --------------------------------------------------------------------------- #
def test_inference_produces_result_risk_and_explanation(
    db_session: Session, consented_patient, storage_root, seeded_config
) -> None:
    patient, worker = consented_patient
    service = ScreeningService(db_session)
    session = service.start_screening(patient_id=patient.id, actor=worker)
    service.capture_eye(
        session_id=session.id, eye_side=EyeSide.LEFT, data=synthetic_fundus(), actor=worker
    )
    service.mark_ready_for_inference(session.id)

    outcome = service.run_inference(session.id, actor=worker)

    assert outcome["worst"].category is not None
    assert outcome["risk"] is not None
    assert outcome["risk"].requires_clinician_review is True
    assert service.inference.explanation_for(outcome["worst"].id) is not None


def test_development_model_results_are_flagged(
    db_session: Session, consented_patient, storage_root, seeded_config
) -> None:
    """The pipeline must never present placeholder output as a real screening."""
    patient, worker = consented_patient
    service = ScreeningService(db_session)
    session = service.start_screening(patient_id=patient.id, actor=worker)
    service.capture_eye(
        session_id=session.id, eye_side=EyeSide.LEFT, data=synthetic_fundus(), actor=worker
    )
    service.mark_ready_for_inference(session.id)

    outcome = service.run_inference(session.id, actor=worker)

    assert outcome["worst"].is_development_model is True
    status = service.inference.provider_status()
    assert status["is_development_model"] is True
    assert status["clinically_validated"] is False


def test_inference_is_idempotent(
    db_session: Session, consented_patient, storage_root, seeded_config
) -> None:
    patient, worker = consented_patient
    service = ScreeningService(db_session)
    session = service.start_screening(patient_id=patient.id, actor=worker)
    service.capture_eye(
        session_id=session.id, eye_side=EyeSide.LEFT, data=synthetic_fundus(), actor=worker
    )
    service.mark_ready_for_inference(session.id)
    first = service.run_inference(session.id, actor=worker)

    image = service.images.active_for_eye(session.id, EyeSide.LEFT.value)
    again = service.inference.run_for_image(image, actor=worker)

    assert again.id == first["worst"].id


# --------------------------------------------------------------------------- #
# Exit points
# --------------------------------------------------------------------------- #
def test_screening_can_always_be_cancelled(
    db_session: Session, consented_patient, storage_root, seeded_config
) -> None:
    patient, worker = consented_patient
    service = ScreeningService(db_session)
    session = service.start_screening(patient_id=patient.id, actor=worker)

    cancelled = service.cancel(session.id, reason="Patient left", actor=worker)

    assert cancelled.state == ScreeningState.CANCELLED.value
    assert cancelled.cancelled_reason == "Patient left"


def test_a_closed_screening_cannot_be_modified(
    db_session: Session, consented_patient, storage_root, seeded_config
) -> None:
    patient, worker = consented_patient
    service = ScreeningService(db_session)
    session = service.start_screening(patient_id=patient.id, actor=worker)
    service.cancel(session.id, actor=worker)

    with pytest.raises(WorkflowError):
        service.capture_eye(
            session_id=session.id,
            eye_side=EyeSide.LEFT,
            data=synthetic_fundus(),
            actor=worker,
        )


# --------------------------------------------------------------------------- #
# End-to-end (spec §73)
# --------------------------------------------------------------------------- #
def test_full_screening_to_follow_up_flow(
    db_session: Session, consented_patient, storage_root, seeded_config, make_user
) -> None:
    """Patient -> consent -> capture -> quality -> AI -> Grad-CAM -> risk ->
    referral -> clinician review -> follow-up -> completed."""
    patient, worker = consented_patient
    doctor = make_user("reviewer@example.com", RoleName.DOCTOR)
    service = ScreeningService(db_session)

    session = service.start_screening(patient_id=patient.id, actor=worker)
    service.capture_eye(
        session_id=session.id, eye_side=EyeSide.LEFT, data=synthetic_fundus(), actor=worker
    )
    service.capture_eye(
        session_id=session.id,
        eye_side=EyeSide.RIGHT,
        data=synthetic_fundus(size=328),
        actor=worker,
    )

    outcome = service.run_inference(session.id, actor=worker)
    assert outcome["risk"] is not None

    service.create_referral(session.id, actor=worker)
    review = service.submit_for_review(session.id, actor=worker)

    review_service = ReviewService(db_session)
    review_service.claim(review.id, reviewer=doctor)
    completed = review_service.complete(
        review.id,
        reviewer=doctor,
        decision=ReviewDecision.CONFIRM_AI,
        clinician_category=outcome["worst"].category,
        notes="Reviewed against the retinal images and heatmap.",
    )

    assert completed.reviewer_user_id == doctor.id
    assert completed.agrees_with_ai is True

    from datetime import date, timedelta

    follow_up = service.create_follow_up(
        session_id=session.id,
        due_date=date.today() + timedelta(days=90),
        instructions="Repeat screening in three months.",
        review_id=completed.id,
        actor=doctor,
    )
    assert follow_up.status == "scheduled"

    final = service.complete(session.id, actor=worker)
    assert final.state == ScreeningState.COMPLETED.value


def test_workflow_snapshot_lets_a_client_resume(
    db_session: Session, consented_patient, storage_root, seeded_config
) -> None:
    patient, worker = consented_patient
    service = ScreeningService(db_session)
    session = service.start_screening(patient_id=patient.id, actor=worker)
    service.capture_eye(
        session_id=session.id, eye_side=EyeSide.LEFT, data=synthetic_fundus(), actor=worker
    )

    snapshot = service.workflow_snapshot(session.id)

    assert snapshot["session"].id == session.id
    assert len(snapshot["images"]) == 1
    assert snapshot["available_transitions"]

"""Screening workflow state machine.

Workflow state lives in exactly one place. Every transition is checked against
this table, so an out-of-order action (screening before the quality gate,
reviewing a cancelled session) fails loudly instead of corrupting a record.

Every non-terminal state offers an exit: the user can always cancel or save and
leave. No state traps the user.
"""

from __future__ import annotations

from app.core.errors import WorkflowError
from app.domain.enums import ScreeningState as S

# state -> states legally reachable from it
TRANSITIONS: dict[S, set[S]] = {
    S.IDLE: {S.PATIENT_SELECTED, S.CANCELLED},
    S.PATIENT_SELECTED: {S.CAPTURE_LEFT_EYE, S.CAPTURE_RIGHT_EYE, S.CANCELLED},
    # READY_FOR_INFERENCE is reachable directly from a capture state so a
    # single-eye screening can proceed with one acceptable image. The service
    # still verifies at least one capture passed the quality gate.
    S.CAPTURE_LEFT_EYE: {
        S.QUALITY_CHECK,
        S.CAPTURE_RIGHT_EYE,
        S.READY_FOR_INFERENCE,
        S.CANCELLED,
        S.ERROR,
    },
    S.CAPTURE_RIGHT_EYE: {
        S.QUALITY_CHECK,
        S.CAPTURE_LEFT_EYE,
        S.READY_FOR_INFERENCE,
        S.CANCELLED,
        S.ERROR,
    },
    S.QUALITY_CHECK: {
        S.RETAKE_REQUIRED,
        S.READY_FOR_INFERENCE,
        S.CAPTURE_LEFT_EYE,
        S.CAPTURE_RIGHT_EYE,
        S.CANCELLED,
        S.ERROR,
    },
    S.RETAKE_REQUIRED: {S.CAPTURE_LEFT_EYE, S.CAPTURE_RIGHT_EYE, S.CANCELLED},
    S.READY_FOR_INFERENCE: {S.INFERENCE_RUNNING, S.CAPTURE_LEFT_EYE, S.CAPTURE_RIGHT_EYE, S.CANCELLED},
    S.INFERENCE_RUNNING: {S.RESULT_AVAILABLE, S.ERROR, S.CANCELLED},
    S.RESULT_AVAILABLE: {
        S.EXPLANATION_AVAILABLE,
        S.REFERRAL_PENDING,
        S.DOCTOR_REVIEW,
        S.COMPLETED,
        S.CANCELLED,
    },
    S.EXPLANATION_AVAILABLE: {
        S.REFERRAL_PENDING,
        S.DOCTOR_REVIEW,
        S.COMPLETED,
        S.CANCELLED,
    },
    S.REFERRAL_PENDING: {S.REFERRAL_CREATED, S.DOCTOR_REVIEW, S.COMPLETED, S.CANCELLED},
    S.REFERRAL_CREATED: {S.DOCTOR_REVIEW, S.SYNC_PENDING, S.COMPLETED, S.CANCELLED},
    S.DOCTOR_REVIEW: {S.FOLLOW_UP, S.COMPLETED, S.CANCELLED},
    S.FOLLOW_UP: {S.COMPLETED, S.CANCELLED},
    S.SYNC_PENDING: {S.SYNCED, S.ERROR, S.CANCELLED},
    S.SYNCED: {S.DOCTOR_REVIEW, S.COMPLETED},
    # Recoverable failure: the workflow can resume at capture.
    S.ERROR: {S.CAPTURE_LEFT_EYE, S.CAPTURE_RIGHT_EYE, S.CANCELLED, S.SYNC_PENDING},
    # Terminal
    S.COMPLETED: set(),
    S.CANCELLED: set(),
}

TERMINAL_STATES: frozenset[S] = frozenset({S.COMPLETED, S.CANCELLED})

# Human-readable label for each state, shown in workflow UIs.
STATE_LABELS: dict[S, str] = {
    S.IDLE: "Not started",
    S.PATIENT_SELECTED: "Patient selected",
    S.CAPTURE_LEFT_EYE: "Capturing left eye",
    S.CAPTURE_RIGHT_EYE: "Capturing right eye",
    S.QUALITY_CHECK: "Checking image quality",
    S.RETAKE_REQUIRED: "Retake required",
    S.READY_FOR_INFERENCE: "Ready for screening",
    S.INFERENCE_RUNNING: "Screening in progress",
    S.RESULT_AVAILABLE: "Result available",
    S.EXPLANATION_AVAILABLE: "Explanation available",
    S.REFERRAL_PENDING: "Referral pending",
    S.REFERRAL_CREATED: "Referral created",
    S.DOCTOR_REVIEW: "Awaiting clinical review",
    S.FOLLOW_UP: "Follow-up scheduled",
    S.COMPLETED: "Completed",
    S.CANCELLED: "Cancelled",
    S.SYNC_PENDING: "Waiting to sync",
    S.SYNCED: "Synced",
    S.ERROR: "Needs attention",
}


def coerce(state: str | S) -> S:
    if isinstance(state, S):
        return state
    try:
        return S(str(state))
    except ValueError as exc:
        raise WorkflowError(f"Unknown screening state '{state}'.") from exc


def can_transition(current: str | S, target: str | S) -> bool:
    return coerce(target) in TRANSITIONS.get(coerce(current), set())


def assert_transition(current: str | S, target: str | S) -> S:
    """Validate a transition, returning the target state."""
    source, destination = coerce(current), coerce(target)
    if destination not in TRANSITIONS.get(source, set()):
        raise WorkflowError(
            f"Cannot move from '{STATE_LABELS.get(source, source.value)}' to "
            f"'{STATE_LABELS.get(destination, destination.value)}'."
        )
    return destination


def is_terminal(state: str | S) -> bool:
    return coerce(state) in TERMINAL_STATES


def available_transitions(current: str | S) -> list[str]:
    return sorted(s.value for s in TRANSITIONS.get(coerce(current), set()))


def assert_not_terminal(state: str | S) -> None:
    if is_terminal(state):
        raise WorkflowError("This screening is already closed and cannot be changed.")

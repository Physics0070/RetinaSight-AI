"""Canonical domain vocabulary.

These are stable *domain* constants (medical grading scale, workflow states,
lifecycle statuses) — the set of values the system can represent. They are NOT
business configuration: tunable rules (risk thresholds, quality cut-offs,
referral routing) live in the database and are served by the config service.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """str-valued Enum (stores/serializes as its value)."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


# --------------------------------------------------------------------------- #
# Identity / access
# --------------------------------------------------------------------------- #
class RoleName(StrEnum):
    ADMIN = "admin"
    HEALTH_WORKER = "health_worker"
    DOCTOR = "doctor"
    PATIENT = "patient"


class UserStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


class Permission(StrEnum):
    """Fine-grained, DB-backed permissions (seeded into ``permissions``)."""

    PATIENT_VIEW_SELF = "PATIENT_VIEW_SELF"
    PATIENT_VIEW = "PATIENT_VIEW"
    PATIENT_CREATE = "PATIENT_CREATE"
    PATIENT_UPDATE = "PATIENT_UPDATE"
    SCREENING_CREATE = "SCREENING_CREATE"
    SCREENING_VIEW = "SCREENING_VIEW"
    IMAGE_VIEW = "IMAGE_VIEW"
    IMAGE_UPLOAD = "IMAGE_UPLOAD"
    INFERENCE_RUN = "INFERENCE_RUN"
    EXPLANATION_VIEW = "EXPLANATION_VIEW"
    RISK_VIEW = "RISK_VIEW"
    REFERRAL_CREATE = "REFERRAL_CREATE"
    REFERRAL_VIEW = "REFERRAL_VIEW"
    CLINICAL_REVIEW = "CLINICAL_REVIEW"
    FOLLOWUP_MANAGE = "FOLLOWUP_MANAGE"
    SYNC_WRITE = "SYNC_WRITE"
    USER_MANAGE = "USER_MANAGE"
    CLINIC_MANAGE = "CLINIC_MANAGE"
    MODEL_MANAGE = "MODEL_MANAGE"
    CONFIG_MANAGE = "CONFIG_MANAGE"
    AUDIT_VIEW = "AUDIT_VIEW"
    SYSTEM_VIEW = "SYSTEM_VIEW"


# --------------------------------------------------------------------------- #
# Consent
# --------------------------------------------------------------------------- #
class ConsentType(StrEnum):
    SCREENING = "screening"
    DATA_STORAGE = "data_storage"
    REFERRAL_SHARING = "referral_sharing"


# --------------------------------------------------------------------------- #
# Screening workflow (state machine — see app.services.screening_state_machine)
# --------------------------------------------------------------------------- #
class ScreeningState(StrEnum):
    IDLE = "idle"
    PATIENT_SELECTED = "patient_selected"
    CAPTURE_LEFT_EYE = "capture_left_eye"
    CAPTURE_RIGHT_EYE = "capture_right_eye"
    QUALITY_CHECK = "quality_check"
    RETAKE_REQUIRED = "retake_required"
    READY_FOR_INFERENCE = "ready_for_inference"
    INFERENCE_RUNNING = "inference_running"
    RESULT_AVAILABLE = "result_available"
    EXPLANATION_AVAILABLE = "explanation_available"
    REFERRAL_PENDING = "referral_pending"
    REFERRAL_CREATED = "referral_created"
    DOCTOR_REVIEW = "doctor_review"
    FOLLOW_UP = "follow_up"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    SYNC_PENDING = "sync_pending"
    SYNCED = "synced"
    ERROR = "error"


class EyeSide(StrEnum):
    LEFT = "left"
    RIGHT = "right"


# --------------------------------------------------------------------------- #
# Image quality gate
# --------------------------------------------------------------------------- #
class QualityGateResult(StrEnum):
    ACCEPTABLE = "acceptable"
    RETAKE_REQUIRED = "retake_required"


class QualityIssue(StrEnum):
    BLUR = "blur"
    LOW_LIGHT = "low_light"
    OVEREXPOSED = "overexposed"
    POOR_FRAMING = "poor_framing"
    RETINA_NOT_VISIBLE = "retina_not_visible"
    LOW_RESOLUTION = "low_resolution"


# --------------------------------------------------------------------------- #
# AI screening / models
# --------------------------------------------------------------------------- #
class ScreeningCategory(StrEnum):
    """Five-class diabetic retinopathy grading scale."""

    NO_DR = "no_dr"
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    PROLIFERATIVE = "proliferative"


class ModelFramework(StrEnum):
    PYTORCH = "pytorch"
    ONNX = "onnx"
    TFLITE = "tflite"
    DEVELOPMENT = "development"


class DeploymentTarget(StrEnum):
    EDGE_TFLITE = "edge_tflite"
    EDGE_ONNX = "edge_onnx"
    CLOUD = "cloud"
    DEVELOPMENT = "development"


class ModelStatus(StrEnum):
    REGISTERED = "registered"
    VALIDATING = "validating"
    DEPLOYED = "deployed"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class ValidationStatus(StrEnum):
    NOT_VALIDATED = "not_validated"
    IN_VALIDATION = "in_validation"
    VALIDATED = "validated"
    FAILED = "failed"


class InferenceMode(StrEnum):
    ON_DEVICE = "on_device"
    CLOUD_SYNC = "cloud_sync"
    CLOUD_WORKER = "cloud_worker"
    DEVELOPMENT = "development"


class InferenceStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# --------------------------------------------------------------------------- #
# Risk / referral / review / follow-up
# --------------------------------------------------------------------------- #
class RiskLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    URGENT = "urgent"


class ReferralPriority(StrEnum):
    ROUTINE = "routine"
    CONSULTATION = "consultation"
    URGENT = "urgent"


class ReferralStatus(StrEnum):
    PENDING = "pending"
    CREATED = "created"
    ACKNOWLEDGED = "acknowledged"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReviewDecision(StrEnum):
    CONFIRM_AI = "confirm_ai"
    REVISE = "revise"
    REFER = "refer"
    ROUTINE_FOLLOW_UP = "routine_follow_up"
    DISMISS = "dismiss"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"


class FollowUpStatus(StrEnum):
    SCHEDULED = "scheduled"
    DUE = "due"
    COMPLETED = "completed"
    MISSED = "missed"
    CANCELLED = "cancelled"


# --------------------------------------------------------------------------- #
# Sync
# --------------------------------------------------------------------------- #
class SyncStatus(StrEnum):
    PENDING = "pending"
    UPLOADING = "uploading"
    SYNCED = "synced"
    FAILED = "failed"
    RETRYING = "retrying"


class SyncOperation(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class SyncEntityType(StrEnum):
    PATIENT = "patient"
    SCREENING_SESSION = "screening_session"
    RETINAL_IMAGE = "retinal_image"
    QUALITY_ASSESSMENT = "quality_assessment"
    INFERENCE_RESULT = "inference_result"
    EXPLANATION = "explanation"
    RISK_ASSESSMENT = "risk_assessment"
    REFERRAL = "referral"
    CLINICAL_REVIEW = "clinical_review"
    FOLLOW_UP = "follow_up"


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
class AuditAction(StrEnum):
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    TOKEN_REFRESHED = "token_refreshed"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    ROLE_CHANGED = "role_changed"
    PATIENT_CREATED = "patient_created"
    PATIENT_UPDATED = "patient_updated"
    CONSENT_RECORDED = "consent_recorded"
    SCREENING_STARTED = "screening_started"
    IMAGE_CAPTURED = "image_captured"
    IMAGE_UPLOADED = "image_uploaded"
    QUALITY_ASSESSED = "quality_assessed"
    INFERENCE_COMPLETED = "inference_completed"
    EXPLANATION_GENERATED = "explanation_generated"
    RISK_ASSESSED = "risk_assessed"
    REFERRAL_CREATED = "referral_created"
    DOCTOR_REVIEWED = "doctor_reviewed"
    FOLLOWUP_CREATED = "followup_created"
    CONFIG_CHANGED = "config_changed"
    MODEL_REGISTERED = "model_registered"
    MODEL_STATUS_CHANGED = "model_status_changed"
    SYNC_PROCESSED = "sync_processed"
    ACCESS_DENIED = "access_denied"


class AuditResult(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"

"""Screening workflow contracts."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.domain.enums import (
    ConsentType,
    EyeSide,
    ReviewDecision,
    ScreeningCategory,
)
from app.schemas.common import ORMModel
from app.schemas.image import RetinalImageRead


# --------------------------------------------------------------------------- #
# Patients
# --------------------------------------------------------------------------- #
class ConsentInput(BaseModel):
    consent_type: ConsentType
    granted: bool


class PatientCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    patient_code: str | None = Field(default=None, max_length=64)
    date_of_birth: date | None = None
    sex: str | None = Field(default=None, max_length=16)
    phone: str | None = Field(default=None, max_length=32)
    has_diabetes: bool | None = None
    diabetes_duration_years: int | None = Field(default=None, ge=0, le=120)
    clinic_id: uuid.UUID | None = None
    consents: list[ConsentInput] = Field(default_factory=list)


class PatientUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    date_of_birth: date | None = None
    sex: str | None = Field(default=None, max_length=16)
    phone: str | None = Field(default=None, max_length=32)
    has_diabetes: bool | None = None
    diabetes_duration_years: int | None = Field(default=None, ge=0, le=120)
    clinic_id: uuid.UUID | None = None


class PatientRead(ORMModel):
    id: uuid.UUID
    patient_code: str
    full_name: str
    date_of_birth: date | None
    sex: str | None
    phone: str | None
    has_diabetes: bool | None
    diabetes_duration_years: int | None
    clinic_id: uuid.UUID | None
    created_at: datetime


class ConsentRead(ORMModel):
    id: uuid.UUID
    consent_type: str
    granted: bool
    granted_at: datetime | None
    created_at: datetime


# --------------------------------------------------------------------------- #
# Quality
# --------------------------------------------------------------------------- #
class QualityAssessmentRead(ORMModel):
    id: uuid.UUID
    image_id: uuid.UUID
    session_id: uuid.UUID
    is_acceptable: bool
    result: str
    overall_score: float
    blur_score: float
    lighting_score: float
    framing_score: float
    retinal_visibility_score: float
    issues: list
    recommendations: list
    assessed_on_device: bool
    created_at: datetime


# --------------------------------------------------------------------------- #
# Inference / explanation / risk
# --------------------------------------------------------------------------- #
class ExplanationRead(ORMModel):
    id: uuid.UUID
    inference_result_id: uuid.UUID
    method: str
    affected_regions: list
    model_version: str | None
    is_development_model: bool
    created_at: datetime


class ExplanationWithUrls(ExplanationRead):
    heatmap_url: str | None = None
    overlay_url: str | None = None
    caveat: str


class InferenceResultRead(ORMModel):
    id: uuid.UUID
    session_id: uuid.UUID
    image_id: uuid.UUID | None
    status: str
    eye_side: str | None
    category: str | None
    confidence: float | None
    class_probabilities: dict
    model_version: str | None
    inference_mode: str | None
    is_development_model: bool
    duration_ms: int | None
    error_message: str | None
    created_at: datetime


class RiskAssessmentRead(ORMModel):
    id: uuid.UUID
    session_id: uuid.UUID
    risk_level: str
    priority: str
    reason: str
    recommended_action: str
    requires_clinician_review: bool
    rule_id: str | None
    created_at: datetime


class ReferralRead(ORMModel):
    id: uuid.UUID
    session_id: uuid.UUID
    patient_id: uuid.UUID
    to_clinic_id: uuid.UUID | None
    assigned_doctor_id: uuid.UUID | None
    priority: str
    status: str
    reason: str
    acknowledged_at: datetime | None
    created_at: datetime


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #
class ScreeningStartRequest(BaseModel):
    patient_id: uuid.UUID
    clinic_id: uuid.UUID | None = None
    local_id: str | None = Field(default=None, max_length=64)
    captured_offline: bool = False


class ScreeningSessionRead(ORMModel):
    id: uuid.UUID
    local_id: str | None
    patient_id: uuid.UUID
    clinic_id: uuid.UUID | None
    conducted_by_user_id: uuid.UUID | None
    state: str
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_reason: str | None
    sync_status: str
    captured_offline: bool
    created_at: datetime


class ScreeningSessionDetail(ScreeningSessionRead):
    state_label: str
    available_transitions: list[str]
    is_terminal: bool
    patient: PatientRead | None = None
    images: list[RetinalImageRead] = []
    quality: list[QualityAssessmentRead] = []
    results: list[InferenceResultRead] = []
    risk: RiskAssessmentRead | None = None
    referral: ReferralRead | None = None


class CaptureResponse(BaseModel):
    image: RetinalImageRead
    quality: QualityAssessmentRead
    retake_required: bool
    session_state: str
    state_label: str


class InferenceRunResponse(BaseModel):
    results: list[InferenceResultRead]
    worst: InferenceResultRead | None
    risk: RiskAssessmentRead | None
    quality_blocked: list[uuid.UUID]
    model_status: dict
    disclaimer: str


class CancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class RetakeRequest(BaseModel):
    eye_side: EyeSide


# --------------------------------------------------------------------------- #
# Review / follow-up
# --------------------------------------------------------------------------- #
class ClinicalReviewRead(ORMModel):
    id: uuid.UUID
    session_id: uuid.UUID
    patient_id: uuid.UUID
    referral_id: uuid.UUID | None
    reviewer_user_id: uuid.UUID | None
    status: str
    decision: str | None
    clinician_category: str | None
    agrees_with_ai: bool | None
    notes: str | None
    reviewed_at: datetime | None
    created_at: datetime


class ReviewCompleteRequest(BaseModel):
    decision: ReviewDecision
    clinician_category: ScreeningCategory | None = None
    notes: str | None = Field(default=None, max_length=4000)
    agrees_with_ai: bool | None = None
    follow_up_due: date | None = None
    follow_up_instructions: str | None = Field(default=None, max_length=2000)


class RiskQueueItem(BaseModel):
    review: ClinicalReviewRead
    session: ScreeningSessionRead
    patient: PatientRead
    risk: RiskAssessmentRead | None
    worst_result: InferenceResultRead | None
    quality_acceptable: bool


class FollowUpRead(ORMModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    session_id: uuid.UUID | None
    review_id: uuid.UUID | None
    due_date: date
    status: str
    instructions: str | None
    completed_at: datetime | None
    created_at: datetime


class FollowUpCreate(BaseModel):
    session_id: uuid.UUID
    due_date: date
    instructions: str | None = Field(default=None, max_length=2000)

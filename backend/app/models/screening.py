"""Screening pipeline: sessions, retinal images, quality assessments,
inference results, explanations, risk assessments, referrals, clinical reviews
and follow-ups.

This mirrors the product workflow:
    capture -> quality gate -> inference -> explanation -> risk -> referral
    -> clinician review -> follow-up
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.domain.enums import ReferralStatus, ReviewStatus, ScreeningState, SyncStatus


class ScreeningSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "screening_sessions"

    # Client-generated id from the offline device; enables idempotent sync.
    local_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)

    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clinics.id", ondelete="SET NULL"), nullable=True, index=True
    )
    conducted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    state: Mapped[str] = mapped_column(
        String(32), default=ScreeningState.IDLE.value, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    sync_status: Mapped[str] = mapped_column(
        String(16), default=SyncStatus.SYNCED.value, index=True
    )
    captured_offline: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    images: Mapped[list["RetinalImage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    inference_results: Mapped[list["InferenceResult"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    risk_assessments: Mapped[list["RiskAssessment"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    referrals: Mapped[list["Referral"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    reviews: Mapped[list["ClinicalReview"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class RetinalImage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Image *metadata* only — bytes live in private object storage."""

    __tablename__ = "retinal_images"
    __table_args__ = (UniqueConstraint("session_id", "eye_side", "capture_index"),)

    local_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("screening_sessions.id", ondelete="CASCADE"), index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )
    eye_side: Mapped[str] = mapped_column(String(8), index=True)
    capture_index: Mapped[int] = mapped_column(Integer, default=0)

    storage_key: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(64), default="image/jpeg")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    session: Mapped["ScreeningSession"] = relationship(back_populates="images")
    quality_assessment: Mapped["QualityAssessment | None"] = relationship(
        back_populates="image", cascade="all, delete-orphan", uselist=False
    )


class QualityAssessment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "quality_assessments"

    image_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("retinal_images.id", ondelete="CASCADE"), unique=True, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("screening_sessions.id", ondelete="CASCADE"), index=True
    )

    is_acceptable: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    result: Mapped[str] = mapped_column(String(24), index=True)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    blur_score: Mapped[float] = mapped_column(Float, default=0.0)
    lighting_score: Mapped[float] = mapped_column(Float, default=0.0)
    framing_score: Mapped[float] = mapped_column(Float, default=0.0)
    retinal_visibility_score: Mapped[float] = mapped_column(Float, default=0.0)
    issues: Mapped[list] = mapped_column(JSON, default=list)
    recommendations: Mapped[list] = mapped_column(JSON, default=list)
    # Snapshot of the thresholds used, so historic results stay interpretable
    # after configuration changes.
    thresholds_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    assessed_on_device: Mapped[bool] = mapped_column(Boolean, default=False)

    image: Mapped["RetinalImage"] = relationship(back_populates="quality_assessment")


class ModelMetadata(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Registry entry for a screening model. Clinical validation status is
    explicit and defaults to NOT validated — never inferred."""

    __tablename__ = "model_metadata"
    __table_args__ = (UniqueConstraint("name", "version"),)

    name: Mapped[str] = mapped_column(String(128), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    framework: Mapped[str] = mapped_column(String(32))
    deployment_target: Mapped[str] = mapped_column(String(32))
    architecture: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_width: Mapped[int] = mapped_column(Integer, default=224)
    input_height: Mapped[int] = mapped_column(Integer, default=224)
    classes: Mapped[list] = mapped_column(JSON, default=list)
    model_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    validation_status: Mapped[str] = mapped_column(String(24), index=True)
    # Populated ONLY from a real validation run. Empty means "no metrics" —
    # the UI must not display or invent performance numbers.
    validation_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    registered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class InferenceResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "inference_results"

    local_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("screening_sessions.id", ondelete="CASCADE"), index=True
    )
    image_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("retinal_images.id", ondelete="CASCADE"), nullable=True, index=True
    )
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("model_metadata.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(16), index=True)
    eye_side: Mapped[str | None] = mapped_column(String(8), nullable=True)
    category: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    class_probabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    inference_mode: Mapped[str | None] = mapped_column(String(24), nullable=True)
    is_development_model: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)

    session: Mapped["ScreeningSession"] = relationship(back_populates="inference_results")
    explanation: Mapped["Explanation | None"] = relationship(
        back_populates="inference_result", cascade="all, delete-orphan", uselist=False
    )


class Explanation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Grad-CAM (or equivalent) saliency output. Not a validated lesion detector."""

    __tablename__ = "explanations"

    inference_result_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inference_results.id", ondelete="CASCADE"), unique=True, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("screening_sessions.id", ondelete="CASCADE"), index=True
    )
    method: Mapped[str] = mapped_column(String(32), default="grad_cam")
    heatmap_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    overlay_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    affected_regions: Mapped[list] = mapped_column(JSON, default=list)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_development_model: Mapped[bool] = mapped_column(Boolean, default=True)

    inference_result: Mapped["InferenceResult"] = relationship(back_populates="explanation")


class RiskAssessment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "risk_assessments"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("screening_sessions.id", ondelete="CASCADE"), index=True
    )
    inference_result_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inference_results.id", ondelete="SET NULL"), nullable=True
    )

    risk_level: Mapped[str] = mapped_column(String(16), index=True)
    priority: Mapped[str] = mapped_column(String(16), index=True)
    reason: Mapped[str] = mapped_column(String(512), default="")
    recommended_action: Mapped[str] = mapped_column(String(255), default="")
    requires_clinician_review: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # Which configured rule produced this outcome (traceability/auditability).
    rule_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rules_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)

    session: Mapped["ScreeningSession"] = relationship(back_populates="risk_assessments")


class Referral(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "referrals"

    local_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("screening_sessions.id", ondelete="CASCADE"), index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )
    risk_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("risk_assessments.id", ondelete="SET NULL"), nullable=True
    )
    to_clinic_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clinics.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_doctor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True, index=True
    )

    priority: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(
        String(16), default=ReferralStatus.CREATED.value, index=True
    )
    reason: Mapped[str] = mapped_column(String(512), default="")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped["ScreeningSession"] = relationship(back_populates="referrals")


class ClinicalReview(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """The clinician-in-the-loop record. AI output is never final without this."""

    __tablename__ = "clinical_reviews"

    local_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("screening_sessions.id", ondelete="CASCADE"), index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )
    referral_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("referrals.id", ondelete="SET NULL"), nullable=True
    )
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(
        String(16), default=ReviewStatus.PENDING.value, index=True
    )
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    clinician_category: Mapped[str | None] = mapped_column(String(24), nullable=True)
    agrees_with_ai: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped["ScreeningSession"] = relationship(back_populates="reviews")


class FollowUp(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "follow_ups"

    local_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("screening_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    review_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clinical_reviews.id", ondelete="SET NULL"), nullable=True
    )

    due_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

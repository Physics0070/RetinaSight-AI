"""Image quality gate service.

Runs the quality assessment against the **configured** thresholds and persists
the outcome, including a snapshot of the thresholds used so a historic result
stays interpretable after configuration changes.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.domain.config_defaults import KEY_QUALITY_NORMALISATION, KEY_QUALITY_THRESHOLDS
from app.domain.enums import AuditAction, QualityGateResult
from app.ml.quality import assess_quality
from app.models.identity import User
from app.models.screening import QualityAssessment, RetinalImage
from app.repositories.base import BaseRepository
from app.services.audit_service import AuditService
from app.services.config_service import ConfigService
from app.storage import get_storage_provider

logger = get_logger(__name__)


class QualityAssessmentRepository(BaseRepository[QualityAssessment]):
    model = QualityAssessment


class QualityService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = QualityAssessmentRepository(db)
        self.config = ConfigService(db)
        self.audit = AuditService(db)
        self.storage = get_storage_provider()

    def assess_image(
        self,
        image: RetinalImage,
        *,
        actor: User | None = None,
        assessed_on_device: bool = False,
    ) -> QualityAssessment:
        thresholds = self.config.get(KEY_QUALITY_THRESHOLDS)
        normalisation = self.config.get(KEY_QUALITY_NORMALISATION)

        data = self.storage.download(image.storage_key)
        result = assess_quality(data, thresholds=thresholds, normalisation=normalisation)

        existing = self.repo.get_by(image_id=image.id)
        payload = result.as_dict()

        if existing is None:
            assessment = QualityAssessment(
                image_id=image.id,
                session_id=image.session_id,
                result=(
                    QualityGateResult.ACCEPTABLE.value
                    if result.is_acceptable
                    else QualityGateResult.RETAKE_REQUIRED.value
                ),
                thresholds_snapshot={
                    "thresholds": thresholds,
                    "normalisation": normalisation,
                    "measurements": result.measurements,
                },
                assessed_on_device=assessed_on_device,
                **payload,
            )
            self.db.add(assessment)
        else:
            assessment = existing
            for key, value in payload.items():
                setattr(assessment, key, value)
            assessment.result = (
                QualityGateResult.ACCEPTABLE.value
                if result.is_acceptable
                else QualityGateResult.RETAKE_REQUIRED.value
            )
            assessment.thresholds_snapshot = {
                "thresholds": thresholds,
                "normalisation": normalisation,
                "measurements": result.measurements,
            }
            assessment.assessed_on_device = assessed_on_device

        self.db.flush()

        self.audit.record(
            action=AuditAction.QUALITY_ASSESSED,
            actor=actor,
            resource_type="retinal_image",
            resource_id=image.id,
            context={
                "acceptable": result.is_acceptable,
                "overall_score": result.scores.overall,
                "issues": result.issues,
            },
        )
        self.db.commit()
        return assessment

    def get_for_image(self, image_id: uuid.UUID) -> QualityAssessment:
        assessment = self.repo.get_by(image_id=image_id)
        if assessment is None:
            raise NotFoundError("This image has not been assessed yet.")
        return assessment

    def for_session(self, session_id: uuid.UUID) -> list[QualityAssessment]:
        return list(self.repo.list(session_id=session_id))

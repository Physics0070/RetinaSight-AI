"""AI screening inference and explanation.

Orchestrates: preprocess -> predict -> Grad-CAM -> persist. Results are per
image (per eye); the session-level outcome is the most severe eye, which is then
handed to the risk engine.

Inference is idempotent per image: re-running returns the stored result unless
explicitly forced, so a retried sync or a double-tap cannot create duplicate
clinical records.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, WorkflowError
from app.core.logging import get_logger
from app.domain.enums import (
    AuditAction,
    InferenceMode,
    InferenceStatus,
    ScreeningCategory,
)
from app.ml.explainability import generate_explanation
from app.ml.preprocessing import preprocess
from app.ml.providers.base import ModelNotAvailableError
from app.ml.registry import ModelRegistry
from app.models.identity import User
from app.models.screening import (
    Explanation,
    InferenceResult,
    ModelMetadata,
    QualityAssessment,
    RetinalImage,
)
from app.repositories.screening_repository import (
    RetinalImageRepository,
    ScreeningSessionRepository,
)
from app.services.audit_service import AuditService
from app.storage import get_storage_provider
from app.storage.base import build_derived_key

logger = get_logger(__name__)

# Clinical ordering of the grading scale — used to pick the worse eye.
SEVERITY_ORDER: list[str] = [
    ScreeningCategory.NO_DR.value,
    ScreeningCategory.MILD.value,
    ScreeningCategory.MODERATE.value,
    ScreeningCategory.SEVERE.value,
    ScreeningCategory.PROLIFERATIVE.value,
]


def severity_rank(category: str | None) -> int:
    try:
        return SEVERITY_ORDER.index(str(category))
    except ValueError:
        return -1


@dataclass
class SessionInference:
    results: list[InferenceResult]
    worst: InferenceResult | None
    quality_blocked: list[uuid.UUID]


class InferenceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.images = RetinalImageRepository(db)
        self.sessions = ScreeningSessionRepository(db)
        self.audit = AuditService(db)
        self.registry = ModelRegistry(db)
        self.storage = get_storage_provider()

    # ------------------------------------------------------------------ #
    def provider_status(self) -> dict:
        return self.registry.status()

    # ------------------------------------------------------------------ #
    def run_for_image(
        self,
        image: RetinalImage,
        *,
        actor: User | None = None,
        force: bool = False,
        with_explanation: bool = True,
    ) -> InferenceResult:
        existing = self.db.execute(
            select(InferenceResult)
            .where(
                InferenceResult.image_id == image.id,
                InferenceResult.status == InferenceStatus.COMPLETED.value,
            )
            .order_by(InferenceResult.created_at.desc())
        ).scalars().first()
        if existing is not None and not force:
            return existing

        # The quality gate is a hard precondition — a rejected image never
        # reaches the model.
        assessment = self.db.execute(
            select(QualityAssessment).where(QualityAssessment.image_id == image.id)
        ).scalars().first()
        if assessment is None:
            raise WorkflowError("This image has not passed the quality gate yet.")
        if not assessment.is_acceptable:
            raise WorkflowError(
                "This image did not pass the quality gate and cannot be screened. "
                "Please retake it."
            )

        provider = self.registry.resolve()
        record = InferenceResult(
            session_id=image.session_id,
            image_id=image.id,
            eye_side=image.eye_side,
            status=InferenceStatus.RUNNING.value,
            model_version=provider.model_version,
            inference_mode=self._mode_for(provider),
            is_development_model=provider.is_development_model,
            model_id=self._metadata_id(),
        )
        self.db.add(record)
        self.db.flush()

        try:
            data = self.storage.download(image.storage_key)
            prepared = preprocess(data, input_size=provider.input_size)
            prediction = provider.predict(prepared.tensor)
        except ModelNotAvailableError as exc:
            record.status = InferenceStatus.FAILED.value
            record.error_message = exc.message
            self.db.commit()
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Inference failed for image=%s", image.id)
            record.status = InferenceStatus.FAILED.value
            record.error_message = "Inference could not be completed."
            self.db.commit()
            raise

        record.status = InferenceStatus.COMPLETED.value
        record.category = prediction.category.value
        record.confidence = prediction.confidence
        record.class_probabilities = prediction.probabilities
        record.model_version = prediction.model_version
        record.is_development_model = prediction.is_development_model
        record.duration_ms = prediction.duration_ms
        self.db.flush()

        if with_explanation:
            self._store_explanation(
                record=record,
                image=image,
                provider=provider,
                prediction=prediction,
                rgb=prepared.rgb,
                tensor=prepared.tensor,
            )

        self.audit.record(
            action=AuditAction.INFERENCE_COMPLETED,
            actor=actor,
            resource_type="inference_result",
            resource_id=record.id,
            context={
                "session_id": str(image.session_id),
                "eye_side": image.eye_side,
                "category": record.category,
                "confidence": round(record.confidence or 0.0, 4),
                "model_version": record.model_version,
                "development_model": record.is_development_model,
            },
        )
        self.db.commit()
        return record

    # ------------------------------------------------------------------ #
    def run_for_session(
        self, session_id: uuid.UUID, *, actor: User | None = None, force: bool = False
    ) -> SessionInference:
        session = self.sessions.get(session_id)
        if session is None:
            raise NotFoundError("Screening session not found.")

        images = self.images.for_session(session_id, active_only=True)
        if not images:
            raise WorkflowError("No captured images are available for screening.")

        results: list[InferenceResult] = []
        blocked: list[uuid.UUID] = []
        for image in images:
            try:
                results.append(
                    self.run_for_image(image, actor=actor, force=force)
                )
            except WorkflowError:
                # Quality-blocked images are reported, not silently skipped.
                blocked.append(image.id)

        if not results:
            raise WorkflowError(
                "None of the captured images passed the quality gate. Please retake."
            )

        worst = max(results, key=lambda r: severity_rank(r.category))
        return SessionInference(results=results, worst=worst, quality_blocked=blocked)

    # ------------------------------------------------------------------ #
    def _store_explanation(
        self, *, record: InferenceResult, image: RetinalImage, provider, prediction, rgb, tensor
    ) -> Explanation | None:
        try:
            explanation = generate_explanation(
                provider=provider, prediction=prediction, rgb=rgb, tensor=tensor
            )
        except Exception:  # noqa: BLE001
            # An explanation is valuable but must never block a screening result.
            logger.exception("Explanation generation failed for image=%s", image.id)
            return None

        heatmap_key = build_derived_key(image.storage_key, kind="gradcam")
        overlay_key = build_derived_key(image.storage_key, kind="overlay")
        self.storage.upload(
            key=heatmap_key, data=explanation.heatmap_png, content_type="image/png"
        )
        self.storage.upload(
            key=overlay_key, data=explanation.overlay_png, content_type="image/png"
        )

        row = Explanation(
            inference_result_id=record.id,
            session_id=record.session_id,
            method=explanation.method,
            heatmap_storage_key=heatmap_key,
            overlay_storage_key=overlay_key,
            affected_regions=explanation.affected_regions,
            model_version=explanation.model_version,
            is_development_model=explanation.is_development_model,
        )
        self.db.add(row)
        self.db.flush()

        self.audit.record(
            action=AuditAction.EXPLANATION_GENERATED,
            resource_type="explanation",
            resource_id=row.id,
            context={"method": explanation.method, "inference_result_id": str(record.id)},
        )
        return row

    # ------------------------------------------------------------------ #
    def _metadata_id(self) -> uuid.UUID | None:
        metadata = self.registry.active_metadata()
        return metadata.id if metadata else None

    @staticmethod
    def _mode_for(provider) -> str:
        if provider.is_development_model:
            return InferenceMode.DEVELOPMENT.value
        return InferenceMode.CLOUD_SYNC.value

    # ------------------------------------------------------------------ #
    def explanation_for(self, inference_result_id: uuid.UUID) -> Explanation | None:
        return self.db.execute(
            select(Explanation).where(
                Explanation.inference_result_id == inference_result_id
            )
        ).scalars().first()

    def results_for_session(self, session_id: uuid.UUID) -> list[InferenceResult]:
        return list(
            self.db.execute(
                select(InferenceResult)
                .where(InferenceResult.session_id == session_id)
                .order_by(InferenceResult.created_at)
            ).scalars().all()
        )

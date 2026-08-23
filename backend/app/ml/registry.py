"""Model registry: resolves which provider serves inference.

Selection order:
1. The ``model_metadata`` row marked ACTIVE in the database, if any.
2. Otherwise the provider named by ``RS_MODEL_PROVIDER``.

If a real model is configured but cannot be loaded, an
:class:`UnavailableModelProvider` is returned — the system reports
"MODEL NOT AVAILABLE" instead of silently degrading to placeholder output.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ModelProvider as ConfiguredProvider
from app.core.config import settings
from app.core.logging import get_logger
from app.domain.enums import ModelFramework, ModelStatus
from app.ml.providers.base import ModelProvider
from app.ml.providers.development import DevelopmentModelProvider, UnavailableModelProvider
from app.models.screening import ModelMetadata

logger = get_logger(__name__)


class ModelRegistry:
    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    def active_metadata(self) -> ModelMetadata | None:
        if self.db is None:
            return None
        stmt = (
            select(ModelMetadata)
            .where(ModelMetadata.status == ModelStatus.ACTIVE.value)
            .order_by(ModelMetadata.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    # ------------------------------------------------------------------ #
    def resolve(self) -> ModelProvider:
        metadata = self.active_metadata()
        if metadata is not None:
            return self._from_metadata(metadata)
        return self._from_settings()

    def _from_metadata(self, metadata: ModelMetadata) -> ModelProvider:
        input_size = (metadata.input_width, metadata.input_height)
        classes = tuple(metadata.classes) if metadata.classes else None
        version = metadata.version
        framework = metadata.framework

        if framework == ModelFramework.DEVELOPMENT.value:
            return DevelopmentModelProvider(version=version, input_size=input_size)

        if not metadata.model_path:
            return UnavailableModelProvider(
                reason=f"model '{metadata.name}:{version}' has no artefact path",
                version=version,
            )

        path = self._resolve_path(metadata.model_path)

        if framework == ModelFramework.ONNX.value:
            from app.ml.providers.onnx_provider import OnnxModelProvider

            return OnnxModelProvider(
                model_path=str(path), version=version, input_size=input_size, classes=classes
            )

        if framework == ModelFramework.PYTORCH.value:
            from app.ml.providers.torch_provider import TorchModelProvider

            return TorchModelProvider(
                model_path=str(path),
                version=version,
                architecture=metadata.architecture or "efficientnet_b0",
                input_size=input_size,
                classes=classes,
            )

        return UnavailableModelProvider(
            reason=f"framework '{framework}' is not supported by this service",
            version=version,
        )

    def _from_settings(self) -> ModelProvider:
        version = settings.active_model_version

        if settings.model_provider == ConfiguredProvider.development:
            return DevelopmentModelProvider(version=version)

        directory = settings.model_dir_path
        if settings.model_provider == ConfiguredProvider.onnx:
            from app.ml.providers.onnx_provider import OnnxModelProvider

            return OnnxModelProvider(
                model_path=str(directory / f"{version}.onnx"), version=version
            )

        if settings.model_provider == ConfiguredProvider.torch:
            from app.ml.providers.torch_provider import TorchModelProvider

            return TorchModelProvider(
                model_path=str(directory / f"{version}.pt"), version=version
            )

        return UnavailableModelProvider(
            reason=f"unknown provider '{settings.model_provider}'", version=version
        )

    @staticmethod
    def _resolve_path(model_path: str) -> Path:
        path = Path(model_path)
        return path if path.is_absolute() else settings.model_dir_path / path.name

    # ------------------------------------------------------------------ #
    def status(self) -> dict[str, object]:
        """Honest status report for the admin model page.

        Validation status comes from stored metadata only — it is never
        inferred, and no performance metrics are invented.
        """
        provider = self.resolve()
        metadata = self.active_metadata()
        return {
            **provider.describe(),
            "source": "database" if metadata else "environment",
            "validation_status": (
                metadata.validation_status if metadata else "not_validated"
            ),
            "validation_metrics": (metadata.validation_metrics if metadata else {}) or {},
            "clinically_validated": bool(
                metadata and metadata.validation_status == "validated"
            ),
        }

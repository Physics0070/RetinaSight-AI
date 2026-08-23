"""Model provider contract.

Inference is deliberately decoupled from any single framework: the service
layer depends on this interface, and PyTorch / ONNX / the development stub are
interchangeable behind it.

Every output carries ``is_development_model``. When that flag is true the result
is **not** a screening opinion and must be surfaced to the user as such.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np

from app.core.errors import AppError
from app.domain.enums import ScreeningCategory


class ModelNotAvailableError(AppError):
    status_code = 503
    code = "model_not_available"
    message = "The screening model is not available. Screening cannot run right now."


@dataclass(frozen=True)
class PredictionOutput:
    category: ScreeningCategory
    confidence: float
    probabilities: dict[str, float]
    model_version: str
    framework: str
    is_development_model: bool
    duration_ms: int
    # Populated by providers that expose intermediate activations (Grad-CAM).
    activations: np.ndarray | None = field(default=None, repr=False)
    warnings: list[str] = field(default_factory=list)


class ModelProvider(ABC):
    """A loadable screening model."""

    #: Class order the model outputs. The five-class DR scale.
    classes: tuple[str, ...] = tuple(c.value for c in ScreeningCategory)

    @property
    @abstractmethod
    def model_version(self) -> str: ...

    @property
    @abstractmethod
    def framework(self) -> str: ...

    @property
    @abstractmethod
    def is_development_model(self) -> bool:
        """True when this backend does not produce clinically meaningful output."""

    @property
    @abstractmethod
    def input_size(self) -> tuple[int, int]: ...

    @abstractmethod
    def is_available(self) -> bool:
        """Whether the model can actually serve a request right now."""

    @abstractmethod
    def predict(self, tensor: np.ndarray) -> PredictionOutput: ...

    def supports_gradcam(self) -> bool:
        return False

    def describe(self) -> dict[str, object]:
        return {
            "model_version": self.model_version,
            "framework": self.framework,
            "is_development_model": self.is_development_model,
            "input_size": list(self.input_size),
            "classes": list(self.classes),
            "available": self.is_available(),
            "supports_gradcam": self.supports_gradcam(),
        }


def softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits)
    exponentiated = np.exp(shifted)
    return exponentiated / np.sum(exponentiated)

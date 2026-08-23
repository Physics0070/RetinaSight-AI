"""PyTorch provider — the training-side backend, and the only one that can
produce true Grad-CAM attributions (it exposes intermediate activations and
gradients).

Supports the candidate architectures from the product proposal — EfficientNet,
MobileNet and ResNet — selected from model metadata rather than hardcoded.

Requires ``torch``/``torchvision`` (requirements-ml.txt) plus a checkpoint. If
either is missing the provider reports itself unavailable; it never substitutes
placeholder output.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from app.core.logging import get_logger
from app.domain.enums import ScreeningCategory
from app.ml.providers.base import (
    ModelNotAvailableError,
    ModelProvider,
    PredictionOutput,
    softmax,
)

logger = get_logger(__name__)

# Architecture name -> (torchvision factory, attribute path of the final conv
# block used as the Grad-CAM target layer).
SUPPORTED_ARCHITECTURES = {
    "efficientnet_b0": ("efficientnet_b0", "features"),
    "efficientnet_b3": ("efficientnet_b3", "features"),
    "mobilenet_v3_large": ("mobilenet_v3_large", "features"),
    "mobilenet_v2": ("mobilenet_v2", "features"),
    "resnet18": ("resnet18", "layer4"),
    "resnet50": ("resnet50", "layer4"),
}


class TorchModelProvider(ModelProvider):
    def __init__(
        self,
        *,
        model_path: str,
        version: str,
        architecture: str = "efficientnet_b0",
        input_size: tuple[int, int] = (224, 224),
        classes: tuple[str, ...] | None = None,
    ) -> None:
        self._path = Path(model_path)
        self._version = version
        self._architecture = architecture
        self._input_size = input_size
        self._model = None
        if classes:
            self.classes = classes

    @property
    def model_version(self) -> str:
        return self._version

    @property
    def framework(self) -> str:
        return "pytorch"

    @property
    def is_development_model(self) -> bool:
        return False

    @property
    def input_size(self) -> tuple[int, int]:
        return self._input_size

    @property
    def architecture(self) -> str:
        return self._architecture

    def supports_gradcam(self) -> bool:
        return self.is_available()

    def _ensure_model(self):  # noqa: ANN202
        if self._model is not None:
            return self._model
        if not self._path.is_file():
            raise ModelNotAvailableError(
                f"MODEL NOT AVAILABLE — checkpoint not found at {self._path}"
            )
        try:
            import torch
            import torchvision
        except ImportError as exc:
            raise ModelNotAvailableError(
                "MODEL NOT AVAILABLE — torch/torchvision are not installed"
            ) from exc

        if self._architecture not in SUPPORTED_ARCHITECTURES:
            raise ModelNotAvailableError(
                f"MODEL NOT AVAILABLE — unsupported architecture '{self._architecture}'"
            )

        factory_name, _ = SUPPORTED_ARCHITECTURES[self._architecture]
        model = getattr(torchvision.models, factory_name)(weights=None)
        _replace_classifier(model, len(self.classes))

        checkpoint = torch.load(self._path, map_location="cpu")
        state = checkpoint.get("state_dict", checkpoint) if isinstance(checkpoint, dict) else checkpoint
        model.load_state_dict(state)
        model.eval()

        self._model = model
        return model

    def is_available(self) -> bool:
        try:
            self._ensure_model()
            return True
        except ModelNotAvailableError:
            return False

    def target_layer(self):  # noqa: ANN201
        """The layer Grad-CAM hooks (final convolutional block)."""
        model = self._ensure_model()
        _, attribute = SUPPORTED_ARCHITECTURES[self._architecture]
        return getattr(model, attribute)

    def predict(self, tensor: np.ndarray) -> PredictionOutput:
        import torch

        model = self._ensure_model()
        started = time.perf_counter()

        with torch.no_grad():
            logits = model(torch.from_numpy(tensor.astype(np.float32)))
        values = logits.detach().cpu().numpy().reshape(-1)
        probabilities = softmax(values)
        index = int(np.argmax(probabilities))

        return PredictionOutput(
            category=ScreeningCategory(self.classes[index]),
            confidence=float(probabilities[index]),
            probabilities={
                name: float(value) for name, value in zip(self.classes, probabilities)
            },
            model_version=self.model_version,
            framework=self.framework,
            is_development_model=False,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )


def _replace_classifier(model, num_classes: int) -> None:
    """Resize the final layer to the DR grading scale."""
    import torch.nn as nn

    if hasattr(model, "classifier"):
        classifier = model.classifier
        if isinstance(classifier, nn.Sequential):
            for index in range(len(classifier) - 1, -1, -1):
                if isinstance(classifier[index], nn.Linear):
                    classifier[index] = nn.Linear(classifier[index].in_features, num_classes)
                    return
        elif isinstance(classifier, nn.Linear):
            model.classifier = nn.Linear(classifier.in_features, num_classes)
            return
    if hasattr(model, "fc") and isinstance(model.fc, nn.Linear):
        model.fc = nn.Linear(model.fc.in_features, num_classes)

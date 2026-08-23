"""ONNX Runtime provider (edge-parity and cloud inference).

ONNX is the interchange format shared with the mobile edge deployment, so the
cloud and on-device paths run the same exported graph.

Requires ``onnxruntime`` (see requirements-ml.txt) and an exported ``.onnx``
model. If either is missing the provider reports itself unavailable rather than
producing substitute output.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from app.ml.providers.base import (
    ModelNotAvailableError,
    ModelProvider,
    PredictionOutput,
    softmax,
)
from app.domain.enums import ScreeningCategory


class OnnxModelProvider(ModelProvider):
    def __init__(
        self,
        *,
        model_path: str,
        version: str,
        input_size: tuple[int, int] = (224, 224),
        classes: tuple[str, ...] | None = None,
    ) -> None:
        self._path = Path(model_path)
        self._version = version
        self._input_size = input_size
        self._session = None
        self._load_error: str | None = None
        if classes:
            self.classes = classes

    @property
    def model_version(self) -> str:
        return self._version

    @property
    def framework(self) -> str:
        return "onnx"

    @property
    def is_development_model(self) -> bool:
        return False

    @property
    def input_size(self) -> tuple[int, int]:
        return self._input_size

    def _ensure_session(self):  # noqa: ANN202
        if self._session is not None:
            return self._session
        if not self._path.is_file():
            self._load_error = f"model file not found at {self._path}"
            raise ModelNotAvailableError(f"MODEL NOT AVAILABLE — {self._load_error}")
        try:
            import onnxruntime as ort
        except ImportError as exc:
            self._load_error = "onnxruntime is not installed"
            raise ModelNotAvailableError(
                f"MODEL NOT AVAILABLE — {self._load_error}"
            ) from exc

        self._session = ort.InferenceSession(
            str(self._path), providers=["CPUExecutionProvider"]
        )
        return self._session

    def is_available(self) -> bool:
        try:
            self._ensure_session()
            return True
        except ModelNotAvailableError:
            return False

    def supports_gradcam(self) -> bool:
        """True when the exported graph also emits class-activation maps."""
        try:
            session = self._ensure_session()
        except ModelNotAvailableError:
            return False
        return len(session.get_outputs()) > 1

    def predict(self, tensor: np.ndarray) -> PredictionOutput:
        session = self._ensure_session()
        started = time.perf_counter()

        input_name = session.get_inputs()[0].name
        outputs = session.run(None, {input_name: tensor.astype(np.float32)})
        logits = np.asarray(outputs[0]).reshape(-1)

        probabilities = logits if _looks_like_probabilities(logits) else softmax(logits)
        index = int(np.argmax(probabilities))

        # Models exported with the CAM wrapper carry a second output of shape
        # (batch, classes, H, W). Without it ONNX serving could not explain a
        # prediction at all, since the runtime has no gradients.
        activations = None
        if len(outputs) > 1:
            cam = np.asarray(outputs[1])
            if cam.ndim == 4 and cam.shape[1] > index:
                activations = cam[0, index].astype(np.float32)

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
            activations=activations,
        )


def _looks_like_probabilities(values: np.ndarray) -> bool:
    """True if the graph already applies softmax."""
    return bool(np.all(values >= 0) and abs(float(values.sum()) - 1.0) < 1e-3)

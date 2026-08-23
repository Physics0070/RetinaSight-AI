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
        # Loading the session refines this from the graph. Preprocessing reads
        # this property, so it has to reflect the graph before the first call —
        # not after it has already resized an image to the wrong resolution.
        try:
            self._ensure_session()
        except ModelNotAvailableError:
            pass
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

        # The graph is the authority on its own input size. Registry metadata
        # and the environment fallback both carry a size, and a stale or absent
        # one would preprocess at the wrong resolution — which for a fixed-shape
        # graph is a runtime error, and for a dynamic one is silent degradation.
        graph_size = _spatial_input_size(self._session)
        if graph_size is not None and graph_size != self._input_size:
            self._input_size = graph_size

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

        # Which grade the model reports is the model's decision, not this
        # provider's. Graphs exported with a decision head emit it as a third
        # output; models trained with the ordinal objective decide by rounding
        # the expected grade, which disagrees with argmax on a real fraction of
        # cases. Older two-output graphs were evaluated under argmax, so that
        # remains the fallback.
        index = _decided_index(outputs, len(probabilities))
        if index is None:
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


def _decided_index(outputs: list, num_classes: int) -> int | None:
    """The grade a decision-head graph reports, or None if it has no such head.

    Guards the index rather than trusting it: an out-of-range value would index
    the class list wrongly and mislabel a screening.
    """
    if len(outputs) < 3:
        return None
    decided = np.asarray(outputs[2]).reshape(-1)
    if decided.size == 0 or not np.issubdtype(decided.dtype, np.integer):
        return None
    index = int(decided[0])
    return index if 0 <= index < num_classes else None


def _spatial_input_size(session) -> tuple[int, int] | None:  # noqa: ANN001
    """(width, height) if the graph fixes them, else None for a dynamic graph."""
    shape = session.get_inputs()[0].shape
    if len(shape) != 4:
        return None
    height, width = shape[2], shape[3]
    if isinstance(height, int) and isinstance(width, int):
        return (width, height)
    return None

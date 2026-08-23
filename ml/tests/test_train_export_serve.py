"""Integration: a trained checkpoint must actually serve through the backend.

This is the seam where a model pipeline usually breaks silently — the export
succeeds, the service loads *something*, and the predictions are quietly wrong.
The test walks the whole path:

    build → checkpoint → ONNX export → backend OnnxModelProvider → prediction

and asserts the served logits match the trained model's.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ML_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ML_ROOT.parent / "backend"
for path in (str(ML_ROOT), str(BACKEND_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

torch = pytest.importorskip("torch", reason="training extras not installed")
pytest.importorskip("onnx", reason="onnx not installed")
pytest.importorskip("onnxruntime", reason="onnxruntime not installed")

from datasets.retinal_dataset import CLASS_NAMES  # noqa: E402
from export.to_onnx import export  # noqa: E402
from training.model_factory import build_model  # noqa: E402


@pytest.fixture(scope="module")
def exported_model(tmp_path_factory) -> tuple[Path, torch.nn.Module, int]:
    """Train-free checkpoint + its ONNX export.

    Weights are random — this test is about the plumbing, not accuracy, and
    random weights exercise the same code path far faster.
    """
    tmp = tmp_path_factory.mktemp("export")
    image_size = 224

    # mobilenet_v2 is the smallest supported backbone; keeps the test quick.
    model = build_model("mobilenet_v2", num_classes=len(CLASS_NAMES), pretrained=False)
    model.eval()

    checkpoint_path = tmp / "best.pt"
    torch.save(
        {
            "state_dict": model.state_dict(),
            "arch": "mobilenet_v2",
            "num_classes": len(CLASS_NAMES),
            "classes": list(CLASS_NAMES),
            "image_size": image_size,
        },
        checkpoint_path,
    )

    onnx_path = tmp / "model.onnx"
    export(checkpoint_path, onnx_path)
    return onnx_path, model, image_size


def test_export_writes_artefact_and_metadata(exported_model) -> None:
    onnx_path, _, _ = exported_model

    assert onnx_path.is_file()
    assert onnx_path.stat().st_size > 0

    metadata_path = onnx_path.with_suffix(".json")
    assert metadata_path.is_file()

    import json

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["architecture"] == "mobilenet_v2"
    assert metadata["classes"] == list(CLASS_NAMES)
    # A freshly exported model has never been validated.
    assert metadata["clinically_validated"] is False


def test_export_refuses_a_diverging_artefact(tmp_path) -> None:
    """Parity is enforced, not merely reported.

    A silently diverging export would produce wrong screening results with no
    error anywhere, so the exporter raises rather than writing a bad artefact.
    """
    from export import to_onnx

    model = build_model("mobilenet_v2", num_classes=len(CLASS_NAMES), pretrained=False)
    model.eval()
    checkpoint = tmp_path / "c.pt"
    torch.save(
        {
            "state_dict": model.state_dict(),
            "arch": "mobilenet_v2",
            "num_classes": len(CLASS_NAMES),
            "image_size": 224,
        },
        checkpoint,
    )

    # Force any difference to look unacceptable.
    original_tolerance = to_onnx.PROBABILITY_TOLERANCE
    to_onnx.PROBABILITY_TOLERANCE = -1.0
    try:
        with pytest.raises(RuntimeError, match="diverge from PyTorch"):
            to_onnx.export(checkpoint, tmp_path / "bad.onnx")
    finally:
        to_onnx.PROBABILITY_TOLERANCE = original_tolerance


def test_backend_provider_loads_the_exported_model(exported_model) -> None:
    onnx_path, _, _ = exported_model
    from app.ml.providers.onnx_provider import OnnxModelProvider

    provider = OnnxModelProvider(model_path=str(onnx_path), version="test-v1")

    assert provider.is_available() is True
    assert provider.framework == "onnx"
    # Crucially: a real exported model must NOT be flagged as the placeholder.
    assert provider.is_development_model is False


def test_served_prediction_matches_the_trained_model(exported_model) -> None:
    """The whole point: the service must reproduce the trained model's output."""
    onnx_path, model, image_size = exported_model
    from app.ml.providers.onnx_provider import OnnxModelProvider

    rng = np.random.default_rng(7)
    tensor = rng.standard_normal((1, 3, image_size, image_size)).astype(np.float32)

    with torch.no_grad():
        expected_logits = model(torch.from_numpy(tensor)).numpy().reshape(-1)
    expected_index = int(np.argmax(expected_logits))

    output = OnnxModelProvider(model_path=str(onnx_path), version="test-v1").predict(tensor)

    assert output.category.value == CLASS_NAMES[expected_index]
    assert set(output.probabilities) == set(CLASS_NAMES)
    assert sum(output.probabilities.values()) == pytest.approx(1.0, abs=1e-5)
    assert 0.0 <= output.confidence <= 1.0


def test_served_model_supports_explanation(exported_model) -> None:
    onnx_path, _, image_size = exported_model
    from app.ml.explainability import generate_explanation
    from app.ml.providers.onnx_provider import OnnxModelProvider

    provider = OnnxModelProvider(model_path=str(onnx_path), version="test-v1")
    rng = np.random.default_rng(3)
    tensor = rng.standard_normal((1, 3, image_size, image_size)).astype(np.float32)
    rgb = rng.integers(0, 255, (image_size, image_size, 3), dtype=np.uint8)

    prediction = provider.predict(tensor)
    explanation = generate_explanation(
        provider=provider, prediction=prediction, rgb=rgb, tensor=tensor
    )

    assert explanation.heatmap_png.startswith(b"\x89PNG")
    assert explanation.overlay_png.startswith(b"\x89PNG")
    assert explanation.is_development_model is False


def test_missing_artefact_reports_unavailable_rather_than_guessing(tmp_path) -> None:
    """The safety property: a missing model must never degrade to placeholder
    output that a clinician might act on."""
    from app.ml.providers.base import ModelNotAvailableError
    from app.ml.providers.onnx_provider import OnnxModelProvider

    provider = OnnxModelProvider(
        model_path=str(tmp_path / "absent.onnx"), version="missing"
    )

    assert provider.is_available() is False
    with pytest.raises(ModelNotAvailableError, match="MODEL NOT AVAILABLE"):
        provider.predict(np.zeros((1, 3, 224, 224), dtype=np.float32))

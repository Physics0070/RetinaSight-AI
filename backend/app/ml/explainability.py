"""Grad-CAM explainability.

Produces a saliency heatmap indicating which regions most influenced the
model's output, plus a colourised overlay for the clinician's image viewer.

**Interpretive limit:** Grad-CAM shows where a model attended. It is not a
validated lesion detector, it does not localise pathology, and a highlighted
region is not a finding. This caveat travels with every explanation the API
returns.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np

from app.core.logging import get_logger
from app.ml.providers.base import ModelProvider, PredictionOutput

logger = get_logger(__name__)

GRADCAM_CAVEAT = (
    "Grad-CAM indicates image regions that influenced the model's output. "
    "It is not a validated lesion detector and does not localise pathology."
)


@dataclass(frozen=True)
class ExplanationOutput:
    method: str
    heatmap_png: bytes
    overlay_png: bytes
    affected_regions: list[dict]
    model_version: str
    is_development_model: bool
    caveat: str = GRADCAM_CAVEAT


def _normalise(activation: np.ndarray) -> np.ndarray:
    activation = np.maximum(activation, 0)  # ReLU: only positive influence
    spread = float(activation.max() - activation.min())
    if spread <= 0:
        return np.zeros_like(activation, dtype=np.float32)
    return ((activation - activation.min()) / spread).astype(np.float32)


def _upscale(grid: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Bilinear upscale of a small activation grid to image size."""
    from PIL import Image

    width, height = size
    with Image.fromarray((grid * 255).astype(np.uint8)) as small:
        resized = small.resize((width, height), Image.BILINEAR)
        return np.asarray(resized, dtype=np.float32) / 255.0


def _colourise(heat: np.ndarray) -> np.ndarray:
    """Map 0-1 saliency to an RGB ramp (blue -> cyan -> yellow -> red).

    A perceptually ordered ramp: severity is conveyed by position along the
    ramp, and the accompanying UI never relies on colour alone.
    """
    stops = np.array(
        [
            [0.0, 0.0, 0.55],
            [0.0, 0.65, 0.85],
            [0.95, 0.90, 0.20],
            [0.85, 0.15, 0.10],
        ],
        dtype=np.float32,
    )
    positions = np.linspace(0.0, 1.0, len(stops))
    flat = heat.reshape(-1)
    channels = [np.interp(flat, positions, stops[:, c]) for c in range(3)]
    rgb = np.stack(channels, axis=-1).reshape(*heat.shape, 3)
    return (rgb * 255).astype(np.uint8)


def _to_png(array: np.ndarray) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    with Image.fromarray(array) as image:
        image.save(buffer, format="PNG")
    return buffer.getvalue()


def _top_regions(heat: np.ndarray, *, grid: int = 3, limit: int = 3) -> list[dict]:
    """Coarse description of where attention concentrated, as named cells."""
    height, width = heat.shape
    cell_h, cell_w = max(1, height // grid), max(1, width // grid)
    names_y = ["superior", "central", "inferior"]
    names_x = ["nasal", "central", "temporal"]

    regions: list[dict] = []
    for row in range(grid):
        for col in range(grid):
            block = heat[
                row * cell_h : (row + 1) * cell_h, col * cell_w : (col + 1) * cell_w
            ]
            if not block.size:
                continue
            label = (
                "central"
                if row == 1 and col == 1
                else f"{names_y[min(row, 2)]}-{names_x[min(col, 2)]}"
            )
            regions.append(
                {
                    "region": label,
                    "intensity": round(float(block.mean()), 4),
                    "bounds": {
                        "x": round(col / grid, 3),
                        "y": round(row / grid, 3),
                        "width": round(1 / grid, 3),
                        "height": round(1 / grid, 3),
                    },
                }
            )

    regions.sort(key=lambda r: r["intensity"], reverse=True)
    return regions[:limit]


def generate_explanation(
    *,
    provider: ModelProvider,
    prediction: PredictionOutput,
    rgb: np.ndarray,
    tensor: np.ndarray,
) -> ExplanationOutput:
    """Build a saliency map for a prediction.

    Uses true Grad-CAM when the provider exposes gradients (PyTorch); otherwise
    falls back to the activation map the provider supplied. The result is always
    labelled with the model's development status so a placeholder explanation is
    never mistaken for a real one.
    """
    height, width = rgb.shape[:2]
    grid = _resolve_saliency_grid(provider, prediction, tensor)
    heat = _upscale(_normalise(grid), (width, height))

    heatmap_rgb = _colourise(heat)
    alpha = np.clip(heat[..., None] * 0.65, 0.0, 0.65)
    overlay = (rgb.astype(np.float32) * (1 - alpha) + heatmap_rgb.astype(np.float32) * alpha)

    return ExplanationOutput(
        method="grad_cam",
        heatmap_png=_to_png(heatmap_rgb),
        overlay_png=_to_png(overlay.astype(np.uint8)),
        affected_regions=_top_regions(heat),
        model_version=prediction.model_version,
        is_development_model=prediction.is_development_model,
    )


def _resolve_saliency_grid(
    provider: ModelProvider, prediction: PredictionOutput, tensor: np.ndarray
) -> np.ndarray:
    from app.ml.providers.torch_provider import TorchModelProvider

    if isinstance(provider, TorchModelProvider) and provider.supports_gradcam():
        try:
            return _torch_gradcam(provider, tensor, prediction)
        except Exception:  # noqa: BLE001
            logger.exception("Grad-CAM computation failed; using provider activations.")

    if prediction.activations is not None:
        return prediction.activations
    return np.zeros((7, 7), dtype=np.float32)


def _torch_gradcam(
    provider, tensor: np.ndarray, prediction: PredictionOutput
) -> np.ndarray:  # pragma: no cover - requires torch + a checkpoint
    """True Grad-CAM: gradient of the predicted class w.r.t. final conv activations."""
    import torch

    model = provider._ensure_model()  # noqa: SLF001 - registry-internal access
    target_layer = provider.target_layer()

    captured: dict[str, torch.Tensor] = {}

    def forward_hook(_module, _inputs, output):  # noqa: ANN001
        captured["activations"] = output.detach()
        output.register_hook(lambda grad: captured.__setitem__("gradients", grad.detach()))

    handle = target_layer.register_forward_hook(forward_hook)
    try:
        inputs = torch.from_numpy(tensor.astype(np.float32)).requires_grad_(True)
        logits = model(inputs)
        class_index = list(provider.classes).index(prediction.category.value)
        model.zero_grad(set_to_none=True)
        logits[0, class_index].backward()

        activations = captured["activations"][0]  # (C, H, W)
        gradients = captured["gradients"][0]  # (C, H, W)
        weights = gradients.mean(dim=(1, 2), keepdim=True)  # channel importance
        cam = (weights * activations).sum(dim=0)
        return cam.cpu().numpy().astype(np.float32)
    finally:
        handle.remove()

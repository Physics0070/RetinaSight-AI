"""Retinal image preprocessing.

Pipeline: decode -> crop to the retinal disc -> resize -> normalise.

Uses NumPy + Pillow by default so the service runs anywhere. If OpenCV is
installed (``requirements-ml.txt``) it is used for the resize step, which is
faster and matches the interpolation used during training.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np

try:  # pragma: no cover - exercised only when the optional dep is installed
    import cv2

    _HAS_OPENCV = True
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]
    _HAS_OPENCV = False


# ImageNet statistics — the standard normalisation for EfficientNet/ResNet/
# MobileNet backbones pretrained on ImageNet. These are properties of the
# pretrained weights, not tunable business configuration.
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


@dataclass(frozen=True)
class PreprocessedImage:
    """A model-ready tensor plus the intermediate RGB array."""

    tensor: np.ndarray  # (1, 3, H, W) float32, normalised — NCHW
    rgb: np.ndarray  # (H, W, 3) uint8 — cropped/resized, for overlays
    original_size: tuple[int, int]
    crop_box: tuple[int, int, int, int]


def decode_image(data: bytes) -> np.ndarray:
    """Decode bytes to an RGB uint8 array."""
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def to_grayscale(rgb: np.ndarray) -> np.ndarray:
    """Luminance (ITU-R BT.601), as float32 in 0-255."""
    return (
        0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    ).astype(np.float32)


def retinal_mask(rgb: np.ndarray, *, threshold: int = 18) -> np.ndarray:
    """Boolean mask of the illuminated retinal disc.

    Fundus photographs sit on a black surround, so a low luminance threshold
    separates the disc from the background reliably.
    """
    return to_grayscale(rgb) > threshold


def find_crop_box(rgb: np.ndarray, *, padding: float = 0.02) -> tuple[int, int, int, int]:
    """Bounding box of the retinal disc as ``(left, top, right, bottom)``."""
    height, width = rgb.shape[:2]
    mask = retinal_mask(rgb)
    if not mask.any():
        return 0, 0, width, height

    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    top, bottom = int(rows[0]), int(rows[-1]) + 1
    left, right = int(cols[0]), int(cols[-1]) + 1

    pad_y = int((bottom - top) * padding)
    pad_x = int((right - left) * padding)
    return (
        max(0, left - pad_x),
        max(0, top - pad_y),
        min(width, right + pad_x),
        min(height, bottom + pad_y),
    )


def crop_to_retina(rgb: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    left, top, right, bottom = find_crop_box(rgb)
    if right - left < 2 or bottom - top < 2:
        return rgb, (0, 0, rgb.shape[1], rgb.shape[0])
    return rgb[top:bottom, left:right], (left, top, right, bottom)


def resize(rgb: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Resize to ``(width, height)``."""
    width, height = size
    if _HAS_OPENCV:  # pragma: no cover - optional path
        return cv2.resize(rgb, (width, height), interpolation=cv2.INTER_AREA)

    from PIL import Image

    with Image.fromarray(rgb) as image:
        return np.asarray(image.resize((width, height), Image.BILINEAR), dtype=np.uint8)


def normalize(rgb: np.ndarray) -> np.ndarray:
    """Scale to 0-1, apply ImageNet normalisation, return NCHW float32."""
    scaled = rgb.astype(np.float32) / 255.0
    normalised = (scaled - IMAGENET_MEAN) / IMAGENET_STD
    return np.expand_dims(np.transpose(normalised, (2, 0, 1)), axis=0)


def preprocess(data: bytes, *, input_size: tuple[int, int] = (224, 224)) -> PreprocessedImage:
    """Full pipeline from raw bytes to a model-ready tensor."""
    rgb = decode_image(data)
    original_size = (rgb.shape[1], rgb.shape[0])
    cropped, crop_box = crop_to_retina(rgb)
    resized = resize(cropped, input_size)
    return PreprocessedImage(
        tensor=normalize(resized),
        rgb=resized,
        original_size=original_size,
        crop_box=crop_box,
    )


def opencv_available() -> bool:
    """Whether the optional OpenCV acceleration path is active."""
    return _HAS_OPENCV

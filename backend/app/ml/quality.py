"""Image quality gate.

Four measurements are taken from the pixels themselves:

* **blur**       — variance of the Laplacian (focus measure)
* **lighting**   — mean luminance vs target, plus clipped-pixel fraction
* **framing**    — how centred the retinal disc is, and how much frame it fills
* **visibility** — how much of the frame is actually retina, and its colour
                   consistency with fundus imagery

Each raw measurement is mapped to a 0-1 score using configurable reference
values, then compared with configurable minimums. Nothing here is a clinical
assessment — it is a capture-quality pre-check that decides whether an image is
worth sending to the model at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.domain.enums import QualityIssue
from app.ml.preprocessing import decode_image, resize, retinal_mask, to_grayscale

# 3x3 discrete Laplacian — a standard focus operator, not a tunable rule.
_LAPLACIAN_KERNEL = np.array(
    [[0.0, 1.0, 0.0], [1.0, -4.0, 1.0], [0.0, 1.0, 0.0]], dtype=np.float32
)


@dataclass
class QualityScores:
    overall: float
    blur: float
    lighting: float
    framing: float
    retinal_visibility: float


@dataclass
class QualityResult:
    is_acceptable: bool
    scores: QualityScores
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    measurements: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "is_acceptable": self.is_acceptable,
            "overall_score": self.scores.overall,
            "blur_score": self.scores.blur,
            "lighting_score": self.scores.lighting,
            "framing_score": self.scores.framing,
            "retinal_visibility_score": self.scores.retinal_visibility,
            "issues": self.issues,
            "recommendations": self.recommendations,
        }


# Actionable guidance shown to the person holding the camera.
_RECOMMENDATIONS: dict[str, str] = {
    QualityIssue.BLUR.value: "Hold the phone steady and let the camera focus before capturing.",
    QualityIssue.LOW_LIGHT.value: "Increase illumination slightly, or move to a darker room to widen the pupil.",
    QualityIssue.OVEREXPOSED.value: "Reduce the light intensity or move the lens slightly further away.",
    QualityIssue.POOR_FRAMING.value: "Centre the retina in the frame and move slightly closer.",
    QualityIssue.RETINA_NOT_VISIBLE.value: "Align the lens with the pupil until the retina fills the circle.",
    QualityIssue.LOW_RESOLUTION.value: "Use a higher capture resolution.",
}


def _laplacian_variance(gray: np.ndarray) -> float:
    """Focus measure: sharp images have high edge-response variance."""
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    windows = np.lib.stride_tricks.sliding_window_view(gray, (3, 3))
    response = np.einsum("ijkl,kl->ij", windows, _LAPLACIAN_KERNEL)
    return float(response.var())


def _clamp(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def _to_analysis_scale(rgb: np.ndarray, target_long_edge: int) -> np.ndarray:
    """Resize so measurements do not depend on the camera's resolution.

    Variance of the Laplacian is *scale-dependent*: the same photograph measured
    at 2000px and at 224px yields very different values. Without normalising the
    analysis scale, the gate's verdict would vary with the phone model rather
    than with image quality — unacceptable for a product whose whole premise is
    heterogeneous smartphone cameras.
    """
    height, width = rgb.shape[:2]
    long_edge = max(height, width)
    if long_edge <= target_long_edge:
        return rgb

    scale = target_long_edge / long_edge
    return resize(rgb, (max(1, int(width * scale)), max(1, int(height * scale))))


def assess_quality(
    data: bytes,
    *,
    thresholds: dict[str, Any],
    normalisation: dict[str, Any],
) -> QualityResult:
    """Score one captured image against the configured quality policy."""
    original = decode_image(data)
    # Resolution is judged on the original; everything else on a fixed scale.
    height, width = original.shape[:2]

    rgb = _to_analysis_scale(
        original, int(normalisation.get("analysis_long_edge", 512))
    )
    gray = to_grayscale(rgb)
    mask = retinal_mask(rgb)

    issues: list[str] = []
    measurements: dict[str, float] = {}

    # -- resolution -------------------------------------------------------
    min_width = int(thresholds.get("min_width", 224))
    min_height = int(thresholds.get("min_height", 224))
    if width < min_width or height < min_height:
        issues.append(QualityIssue.LOW_RESOLUTION.value)

    # -- blur -------------------------------------------------------------
    sharpness = _laplacian_variance(gray)
    sharpness_reference = float(normalisation.get("sharpness_reference", 220.0)) or 1.0
    blur_score = _clamp(sharpness / sharpness_reference)
    measurements["laplacian_variance"] = round(sharpness, 3)

    # -- lighting ---------------------------------------------------------
    retina_pixels = gray[mask] if mask.any() else gray
    mean_luminance = float(retina_pixels.mean()) if retina_pixels.size else 0.0
    target = float(normalisation.get("target_luminance", 118.0))
    tolerance = float(normalisation.get("luminance_tolerance", 62.0)) or 1.0
    luminance_score = _clamp(1.0 - abs(mean_luminance - target) / tolerance)

    clipped_dark = float((gray <= 2).mean())
    clipped_bright = float((gray >= 253).mean())
    max_clipped = float(normalisation.get("max_clipped_fraction", 0.12)) or 1.0
    clipping_score = _clamp(1.0 - (clipped_bright / max_clipped))
    lighting_score = _clamp(min(luminance_score, clipping_score))

    measurements["mean_luminance"] = round(mean_luminance, 3)
    measurements["clipped_bright_fraction"] = round(clipped_bright, 4)
    measurements["clipped_dark_fraction"] = round(clipped_dark, 4)

    # -- framing ----------------------------------------------------------
    coverage = float(mask.mean())
    target_coverage = float(normalisation.get("target_coverage", 0.42))
    coverage_tolerance = float(normalisation.get("coverage_tolerance", 0.30)) or 1.0
    coverage_score = _clamp(1.0 - abs(coverage - target_coverage) / coverage_tolerance)

    if mask.any():
        rows, cols = np.nonzero(mask)
        analysis_height, analysis_width = gray.shape
        centre_y, centre_x = float(rows.mean()), float(cols.mean())
        offset = float(
            np.hypot(centre_x - analysis_width / 2.0, centre_y - analysis_height / 2.0)
            / max(1.0, np.hypot(analysis_width, analysis_height) / 2.0)
        )
    else:
        offset = 1.0
    max_offset = float(normalisation.get("max_centre_offset", 0.28)) or 1.0
    centring_score = _clamp(1.0 - offset / max_offset)
    framing_score = _clamp(min(coverage_score, centring_score))

    measurements["retina_coverage"] = round(coverage, 4)
    measurements["centre_offset"] = round(offset, 4)

    # -- retinal visibility ----------------------------------------------
    # Fundus imagery is red-dominant; a frame with no red-dominant disc is
    # very unlikely to be a retina.
    if mask.any():
        masked = rgb[mask].astype(np.float32)
        channel_means = masked.mean(axis=0)
        total = float(channel_means.sum()) or 1.0
        red_ratio = float(channel_means[0] / total)
    else:
        red_ratio = 0.0
    # 1/3 is neutral; real fundus images sit around 0.42-0.68. Both the floor
    # and the span are configuration, not constants baked into the algorithm.
    redness_floor = float(normalisation.get("red_ratio_floor", 0.36))
    redness_span = float(normalisation.get("red_ratio_span", 0.14)) or 1.0
    redness_score = _clamp((red_ratio - redness_floor) / redness_span)
    visibility_score = _clamp(min(coverage_score, redness_score))

    measurements["red_channel_ratio"] = round(red_ratio, 4)

    # -- overall ----------------------------------------------------------
    scores = QualityScores(
        overall=round(
            float(np.mean([blur_score, lighting_score, framing_score, visibility_score])), 4
        ),
        blur=round(blur_score, 4),
        lighting=round(lighting_score, 4),
        framing=round(framing_score, 4),
        retinal_visibility=round(visibility_score, 4),
    )

    # -- policy -----------------------------------------------------------
    if scores.blur < float(thresholds.get("blur_min", 0.45)):
        issues.append(QualityIssue.BLUR.value)
    if scores.lighting < float(thresholds.get("lighting_min", 0.40)):
        issues.append(
            QualityIssue.OVEREXPOSED.value
            if mean_luminance > target
            else QualityIssue.LOW_LIGHT.value
        )
    if scores.framing < float(thresholds.get("framing_min", 0.40)):
        issues.append(QualityIssue.POOR_FRAMING.value)
    if scores.retinal_visibility < float(thresholds.get("retinal_visibility_min", 0.50)):
        issues.append(QualityIssue.RETINA_NOT_VISIBLE.value)

    is_acceptable = (
        not issues and scores.overall >= float(thresholds.get("overall_min", 0.55))
    )
    if not issues and not is_acceptable:
        # Every dimension passed but the blend fell short — say so plainly.
        issues.append(QualityIssue.BLUR.value)

    return QualityResult(
        is_acceptable=is_acceptable,
        scores=scores,
        issues=issues,
        recommendations=[_RECOMMENDATIONS[i] for i in issues if i in _RECOMMENDATIONS],
        measurements=measurements,
    )

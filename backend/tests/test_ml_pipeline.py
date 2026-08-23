"""ML pipeline: preprocessing, quality gate, providers, explainability."""

from __future__ import annotations

import io

import numpy as np
import pytest

from app.domain.config_defaults import (
    DEFAULT_CONFIGURATION,
    KEY_QUALITY_NORMALISATION,
    KEY_QUALITY_THRESHOLDS,
)
from app.domain.enums import QualityIssue, ScreeningCategory
from app.ml.explainability import GRADCAM_CAVEAT, generate_explanation
from app.ml.preprocessing import decode_image, find_crop_box, normalize, preprocess
from app.ml.providers.base import ModelNotAvailableError
from app.ml.providers.development import (
    DEVELOPMENT_WARNING,
    DevelopmentModelProvider,
    UnavailableModelProvider,
)
from app.ml.quality import assess_quality

THRESHOLDS = DEFAULT_CONFIGURATION[KEY_QUALITY_THRESHOLDS]["value"]
NORMALISATION = DEFAULT_CONFIGURATION[KEY_QUALITY_NORMALISATION]["value"]


# --------------------------------------------------------------------------- #
# Synthetic fixtures
# --------------------------------------------------------------------------- #
def synthetic_fundus(
    size: int = 320,
    *,
    blur: bool = False,
    brightness: float = 1.0,
    coverage: float = 0.42,
    offset: tuple[int, int] = (0, 0),
) -> bytes:
    """A crude fundus-like image: a red-dominant disc on a black surround."""
    from PIL import Image, ImageFilter

    canvas = np.zeros((size, size, 3), dtype=np.float32)
    radius = np.sqrt(coverage / np.pi) * size
    yy, xx = np.mgrid[0:size, 0:size]
    centre = size / 2
    mask = (
        (xx - centre - offset[0]) ** 2 + (yy - centre - offset[1]) ** 2
    ) <= radius**2

    # Red-dominant, with vessel-like texture so the focus measure has signal.
    canvas[..., 0] = mask * 165.0
    canvas[..., 1] = mask * 70.0
    canvas[..., 2] = mask * 55.0
    texture = (np.sin(xx / 3.0) * np.cos(yy / 4.0) * 26.0) * mask
    canvas += texture[..., None]
    canvas = np.clip(canvas * brightness, 0, 255).astype(np.uint8)

    image = Image.fromarray(canvas)
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(radius=6))

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# Preprocessing
# --------------------------------------------------------------------------- #
def test_preprocess_produces_model_ready_tensor() -> None:
    result = preprocess(synthetic_fundus(), input_size=(224, 224))

    assert result.tensor.shape == (1, 3, 224, 224)
    assert result.tensor.dtype == np.float32
    assert result.rgb.shape == (224, 224, 3)


def test_crop_isolates_the_retinal_disc() -> None:
    rgb = decode_image(synthetic_fundus(size=300, coverage=0.2))
    left, top, right, bottom = find_crop_box(rgb)

    # The disc occupies well under the full frame, so cropping must shrink it.
    assert (right - left) < 300
    assert (bottom - top) < 300


def test_normalisation_centres_values_around_zero() -> None:
    rgb = np.full((8, 8, 3), 118, dtype=np.uint8)
    tensor = normalize(rgb)

    assert tensor.shape == (1, 3, 8, 8)
    assert abs(float(tensor.mean())) < 1.5


def test_preprocess_handles_a_blank_frame() -> None:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (256, 256), color=(0, 0, 0)).save(buffer, format="PNG")

    result = preprocess(buffer.getvalue(), input_size=(224, 224))

    assert result.tensor.shape == (1, 3, 224, 224)


# --------------------------------------------------------------------------- #
# Quality gate
# --------------------------------------------------------------------------- #
def test_reasonable_capture_passes_the_gate() -> None:
    result = assess_quality(
        synthetic_fundus(), thresholds=THRESHOLDS, normalisation=NORMALISATION
    )

    assert result.is_acceptable is True
    assert result.issues == []
    assert 0.0 <= result.scores.overall <= 1.0


def test_blurred_capture_is_rejected_with_guidance() -> None:
    result = assess_quality(
        synthetic_fundus(blur=True), thresholds=THRESHOLDS, normalisation=NORMALISATION
    )

    assert result.is_acceptable is False
    assert QualityIssue.BLUR.value in result.issues
    assert result.recommendations, "A rejected image must tell the user what to do"


def test_dark_capture_is_rejected() -> None:
    result = assess_quality(
        synthetic_fundus(brightness=0.12),
        thresholds=THRESHOLDS,
        normalisation=NORMALISATION,
    )

    assert result.is_acceptable is False
    assert QualityIssue.LOW_LIGHT.value in result.issues


def test_frame_without_a_retina_is_rejected() -> None:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (320, 320), color=(20, 90, 30)).save(buffer, format="JPEG")

    result = assess_quality(
        buffer.getvalue(), thresholds=THRESHOLDS, normalisation=NORMALISATION
    )

    assert result.is_acceptable is False
    assert QualityIssue.RETINA_NOT_VISIBLE.value in result.issues


def test_badly_framed_capture_is_rejected() -> None:
    result = assess_quality(
        synthetic_fundus(coverage=0.05, offset=(90, 90)),
        thresholds=THRESHOLDS,
        normalisation=NORMALISATION,
    )

    assert result.is_acceptable is False
    assert QualityIssue.POOR_FRAMING.value in result.issues


def test_low_resolution_capture_is_flagged() -> None:
    result = assess_quality(
        synthetic_fundus(size=64), thresholds=THRESHOLDS, normalisation=NORMALISATION
    )

    assert QualityIssue.LOW_RESOLUTION.value in result.issues
    assert result.is_acceptable is False


def test_thresholds_are_configuration_driven() -> None:
    """Raising the bar must change the verdict — nothing is hardcoded."""
    image = synthetic_fundus(blur=True)
    permissive = dict(THRESHOLDS)
    permissive.update({"blur_min": 0.0, "overall_min": 0.0, "lighting_min": 0.0,
                       "framing_min": 0.0, "retinal_visibility_min": 0.0})

    strict = assess_quality(image, thresholds=THRESHOLDS, normalisation=NORMALISATION)
    relaxed = assess_quality(image, thresholds=permissive, normalisation=NORMALISATION)

    assert strict.is_acceptable is False
    assert relaxed.is_acceptable is True


def test_scores_stay_within_bounds_for_extreme_inputs() -> None:
    for brightness in (0.02, 1.0, 3.0):
        result = assess_quality(
            synthetic_fundus(brightness=brightness),
            thresholds=THRESHOLDS,
            normalisation=NORMALISATION,
        )
        for score in (
            result.scores.overall,
            result.scores.blur,
            result.scores.lighting,
            result.scores.framing,
            result.scores.retinal_visibility,
        ):
            assert 0.0 <= score <= 1.0


# --------------------------------------------------------------------------- #
# Model providers — honesty guarantees
# --------------------------------------------------------------------------- #
def test_development_provider_is_labelled_and_warns() -> None:
    provider = DevelopmentModelProvider()
    output = provider.predict(preprocess(synthetic_fundus()).tensor)

    assert provider.is_development_model is True
    assert output.is_development_model is True
    assert DEVELOPMENT_WARNING in output.warnings
    assert "NOT FOR CLINICAL USE" in DEVELOPMENT_WARNING


def test_development_provider_is_deterministic() -> None:
    tensor = preprocess(synthetic_fundus()).tensor
    provider = DevelopmentModelProvider()

    first = provider.predict(tensor)
    second = provider.predict(tensor)

    assert first.category == second.category
    assert first.confidence == pytest.approx(second.confidence)


def test_predictions_use_the_five_class_scale_and_sum_to_one() -> None:
    output = DevelopmentModelProvider().predict(preprocess(synthetic_fundus()).tensor)

    assert set(output.probabilities) == {c.value for c in ScreeningCategory}
    assert sum(output.probabilities.values()) == pytest.approx(1.0, abs=1e-5)
    assert 0.0 <= output.confidence <= 1.0
    assert output.category.value in output.probabilities


def test_unavailable_provider_refuses_rather_than_inventing_output() -> None:
    provider = UnavailableModelProvider(reason="no checkpoint present")

    assert provider.is_available() is False
    with pytest.raises(ModelNotAvailableError) as exc:
        provider.predict(np.zeros((1, 3, 224, 224), dtype=np.float32))
    assert "MODEL NOT AVAILABLE" in str(exc.value)


def test_provider_description_reports_no_invented_metrics() -> None:
    described = DevelopmentModelProvider().describe()

    for forbidden in ("accuracy", "sensitivity", "specificity", "auc", "f1"):
        assert forbidden not in {k.lower() for k in described}


# --------------------------------------------------------------------------- #
# Explainability
# --------------------------------------------------------------------------- #
def test_explanation_produces_heatmap_and_overlay() -> None:
    prepared = preprocess(synthetic_fundus())
    provider = DevelopmentModelProvider()
    prediction = provider.predict(prepared.tensor)

    explanation = generate_explanation(
        provider=provider, prediction=prediction, rgb=prepared.rgb, tensor=prepared.tensor
    )

    assert explanation.method == "grad_cam"
    assert explanation.heatmap_png.startswith(b"\x89PNG")
    assert explanation.overlay_png.startswith(b"\x89PNG")
    assert explanation.affected_regions
    assert explanation.caveat == GRADCAM_CAVEAT


def test_explanation_carries_the_interpretive_caveat() -> None:
    assert "not a validated lesion detector" in GRADCAM_CAVEAT.lower()


def test_explanation_inherits_development_status() -> None:
    prepared = preprocess(synthetic_fundus())
    provider = DevelopmentModelProvider()
    prediction = provider.predict(prepared.tensor)

    explanation = generate_explanation(
        provider=provider, prediction=prediction, rgb=prepared.rgb, tensor=prepared.tensor
    )

    assert explanation.is_development_model is True


def test_overlay_matches_the_source_image_dimensions() -> None:
    from PIL import Image

    prepared = preprocess(synthetic_fundus(), input_size=(224, 224))
    provider = DevelopmentModelProvider()
    prediction = provider.predict(prepared.tensor)

    explanation = generate_explanation(
        provider=provider, prediction=prediction, rgb=prepared.rgb, tensor=prepared.tensor
    )

    with Image.open(io.BytesIO(explanation.overlay_png)) as overlay:
        assert overlay.size == (224, 224)

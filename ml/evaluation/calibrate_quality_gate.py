"""Calibrate the image quality gate against real fundus photographs.

Why this exists
---------------
The gate's normalisation references were originally set against synthetically
generated fundus-like images. Real photographs behave differently — the retinal
disc fills far more of the frame, and genuine retinal tissue is much smoother
than drawn texture — so the original references rejected essentially every real
image. A gate that rejects everything is worse than no gate: it blocks the
workflow entirely.

This script measures the real distributions and proposes references derived from
them, then checks that the proposed settings still *discriminate*: deliberately
degraded copies of the same images must still be rejected. Calibration that
accepts everything is just as broken as one that accepts nothing.

Usage:
    python -m evaluation.calibrate_quality_gate --data-dir data/aptos/train_images
"""

from __future__ import annotations

import argparse
import io
import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

ML_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ML_ROOT.parent / "backend"
for path in (str(ML_ROOT), str(BACKEND_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.ml.quality import _laplacian_variance, assess_quality  # noqa: E402
from app.ml.preprocessing import decode_image, retinal_mask, to_grayscale  # noqa: E402


def measure(data: bytes) -> dict[str, float]:
    """Raw, un-normalised measurements for one image."""
    rgb = decode_image(data)
    height, width = rgb.shape[:2]
    gray = to_grayscale(rgb)
    mask = retinal_mask(rgb)

    retina = gray[mask] if mask.any() else gray
    coverage = float(mask.mean())

    if mask.any():
        rows, cols = np.nonzero(mask)
        offset = float(
            np.hypot(cols.mean() - width / 2.0, rows.mean() - height / 2.0)
            / max(1.0, np.hypot(width, height) / 2.0)
        )
        channels = rgb[mask].astype(np.float32).mean(axis=0)
        red_ratio = float(channels[0] / max(channels.sum(), 1e-6))
    else:
        offset, red_ratio = 1.0, 0.0

    return {
        "laplacian_variance": _laplacian_variance(gray),
        "mean_luminance": float(retina.mean()) if retina.size else 0.0,
        "clipped_bright": float((gray >= 253).mean()),
        "coverage": coverage,
        "centre_offset": offset,
        "red_ratio": red_ratio,
    }


def degrade(data: bytes, kind: str) -> bytes:
    """Produce a genuinely unusable version of a real image."""
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB")
        if kind == "blur":
            image = image.filter(ImageFilter.GaussianBlur(radius=max(image.width // 80, 6)))
        elif kind == "dark":
            image = ImageEnhance.Brightness(image).enhance(0.15)
        elif kind == "washed":
            image = ImageEnhance.Brightness(image).enhance(2.6)
        elif kind == "offcentre":
            # Crop a corner: the disc ends up small and far off centre.
            w, h = image.size
            image = image.crop((0, 0, w // 2, h // 2)).resize((w, h))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=92)
        return buffer.getvalue()


def percentile(values: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=np.float64), q)) if values else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate the quality gate.")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--sample", type=int, default=250)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    root = Path(args.data_dir)
    files = sorted(p for p in root.rglob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg"})
    if not files:
        raise SystemExit(f"No images under {root}")

    chosen = random.Random(args.seed).sample(files, min(args.sample, len(files)))
    print(f"Measuring {len(chosen)} real fundus images from {root}\n")

    measurements: dict[str, list[float]] = {
        k: [] for k in ("laplacian_variance", "mean_luminance", "clipped_bright",
                        "coverage", "centre_offset", "red_ratio")
    }
    for path in chosen:
        for key, value in measure(path.read_bytes()).items():
            measurements[key].append(value)

    print(f"{'measure':<22}{'p5':>10}{'p25':>10}{'median':>10}{'p75':>10}{'p95':>10}")
    print("-" * 72)
    for key, values in measurements.items():
        print(
            f"{key:<22}{percentile(values, 5):>10.3f}{percentile(values, 25):>10.3f}"
            f"{percentile(values, 50):>10.3f}{percentile(values, 75):>10.3f}"
            f"{percentile(values, 95):>10.3f}"
        )

    # Derive references so a typical real image scores well, while leaving room
    # for genuinely poor captures to fall below the thresholds.
    sharpness = measurements["laplacian_variance"]
    luminance = measurements["mean_luminance"]
    coverage = measurements["coverage"]
    offsets = measurements["centre_offset"]
    redness = measurements["red_ratio"]

    proposed_normalisation = {
        # The 60th percentile of real sharpness counts as "fully sharp"; below
        # roughly the 10th percentile the score decays toward zero.
        "sharpness_reference": round(percentile(sharpness, 60), 2),
        "target_luminance": round(percentile(luminance, 50), 1),
        # Wide enough to cover the real p5-p95 spread.
        "luminance_tolerance": round(
            max(percentile(luminance, 95) - percentile(luminance, 50),
                percentile(luminance, 50) - percentile(luminance, 5)) * 1.35, 1
        ),
        "max_clipped_fraction": round(max(percentile(measurements["clipped_bright"], 95) * 3, 0.02), 4),
        "target_coverage": round(percentile(coverage, 50), 3),
        "coverage_tolerance": round(
            max(percentile(coverage, 50) - percentile(coverage, 5), 0.12) * 2.2, 3
        ),
        "max_centre_offset": round(max(percentile(offsets, 95) * 2.5, 0.10), 3),
        "red_ratio_floor": round(max(percentile(redness, 5) - 0.06, 0.30), 3),
    }

    print("\nProposed normalisation:")
    print(json.dumps(proposed_normalisation, indent=2))

    # --- verify: real images pass, degraded ones still fail -----------------
    thresholds = {
        "overall_min": 0.55, "blur_min": 0.45, "lighting_min": 0.40,
        "framing_min": 0.40, "retinal_visibility_min": 0.50,
        "min_width": 224, "min_height": 224,
    }

    check = chosen[:60]
    accepted = sum(
        assess_quality(p.read_bytes(), thresholds=thresholds,
                       normalisation=proposed_normalisation).is_acceptable
        for p in check
    )
    print(f"\nReal images accepted: {accepted}/{len(check)} ({accepted / len(check):.0%})")

    print("\nDegraded images (these must still be rejected):")
    for kind in ("blur", "dark", "washed", "offcentre"):
        rejected = sum(
            not assess_quality(degrade(p.read_bytes(), kind), thresholds=thresholds,
                               normalisation=proposed_normalisation).is_acceptable
            for p in check[:25]
        )
        print(f"  {kind:<12} rejected {rejected}/25")

    print(
        "\nA gate that accepts everything is as broken as one that accepts nothing.\n"
        "Only adopt these references if the degraded rejection rates above are high."
    )


if __name__ == "__main__":
    main()

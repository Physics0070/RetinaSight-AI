"""Generate a synthetic fundus dataset for **pipeline verification only**.

Purpose
-------
Prove that the training pipeline runs end to end — dataset discovery, stratified
splitting, augmentation, training loop, metrics, checkpointing, ONNX export —
before anyone spends hours on a real dataset or discovers a bug at epoch 40.

What this is NOT
----------------
This is **not** retinal data and a model trained on it is **not** a screening
model. The "lesions" are drawn geometric artefacts, not pathology. Grade
separability here is synthetic and says nothing whatsoever about performance on
real fundus photographs.

Any run using this data is labelled `pipeline-smoke-test` and must never be
registered as an active model.

Usage:
    python -m datasets.make_synthetic --output data/synthetic --per-class 60
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image

CLASS_NAMES = ("no_dr", "mild", "moderate", "severe", "proliferative")

# Drawn-artefact counts per grade. These encode a deliberately learnable
# gradient so the pipeline can be exercised — they are not clinical criteria.
LESION_PROFILE = {
    0: {"microaneurysms": (0, 1), "haemorrhages": (0, 0), "exudates": (0, 0), "neovessels": 0},
    1: {"microaneurysms": (3, 8), "haemorrhages": (0, 1), "exudates": (0, 1), "neovessels": 0},
    2: {"microaneurysms": (8, 18), "haemorrhages": (2, 5), "exudates": (2, 5), "neovessels": 0},
    3: {"microaneurysms": (18, 32), "haemorrhages": (6, 12), "exudates": (6, 12), "neovessels": 0},
    4: {"microaneurysms": (25, 40), "haemorrhages": (10, 18), "exudates": (8, 16), "neovessels": 6},
}


def _draw_disc(size: int, rng: random.Random) -> np.ndarray:
    """Fundus base: red-dominant illuminated disc on a dark surround."""
    image = np.zeros((size, size, 3), dtype=np.float32)
    centre = size / 2
    radius = size * rng.uniform(0.36, 0.42)

    yy, xx = np.mgrid[0:size, 0:size]
    distance = np.sqrt((xx - centre) ** 2 + (yy - centre) ** 2)
    mask = distance <= radius

    # Radial falloff, brighter toward the centre.
    falloff = np.clip(1.0 - (distance / max(radius, 1)) ** 2 * 0.45, 0, 1)
    base = rng.uniform(0.85, 1.15)

    image[..., 0] = mask * falloff * 170 * base
    image[..., 1] = mask * falloff * 72 * base
    image[..., 2] = mask * falloff * 56 * base

    return image


def _draw_vessels(image: np.ndarray, rng: random.Random) -> None:
    """Vessel arcades radiating from an optic-disc position."""
    size = image.shape[0]
    centre = size / 2
    disc_x = centre + size * rng.uniform(0.14, 0.22) * rng.choice([-1, 1])
    disc_y = centre + size * rng.uniform(-0.06, 0.06)

    # Optic disc: brighter, yellow-ish.
    _blend_circle(image, disc_x, disc_y, size * 0.055, (245, 200, 130), 0.9)

    for _ in range(rng.randint(6, 10)):
        angle = rng.uniform(0, 2 * math.pi)
        x, y = disc_x, disc_y
        length = size * rng.uniform(0.22, 0.40)
        steps = int(length)
        thickness = rng.uniform(1.2, 2.6)

        for step in range(steps):
            angle += rng.uniform(-0.12, 0.12)  # gentle meander
            x += math.cos(angle)
            y += math.sin(angle)
            if not (0 <= x < size and 0 <= y < size):
                break
            taper = thickness * (1 - step / max(steps, 1) * 0.6)
            _blend_circle(image, x, y, taper, (110, 30, 25), 0.7)


def _blend_circle(
    image: np.ndarray, cx: float, cy: float, radius: float, colour, alpha: float
) -> None:
    size = image.shape[0]
    radius = max(radius, 0.6)
    x0, x1 = max(0, int(cx - radius) - 1), min(size, int(cx + radius) + 2)
    y0, y1 = max(0, int(cy - radius) - 1), min(size, int(cy + radius) + 2)
    if x0 >= x1 or y0 >= y1:
        return

    yy, xx = np.mgrid[y0:y1, x0:x1]
    distance = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    weight = np.clip(1.0 - distance / radius, 0, 1)[..., None] * alpha

    patch = image[y0:y1, x0:x1]
    # Only draw inside the illuminated disc.
    inside = (patch.sum(axis=-1, keepdims=True) > 12).astype(np.float32)
    image[y0:y1, x0:x1] = patch * (1 - weight * inside) + np.array(
        colour, dtype=np.float32
    ) * weight * inside


def _draw_lesions(image: np.ndarray, grade: int, rng: random.Random) -> None:
    size = image.shape[0]
    centre = size / 2
    radius = size * 0.36
    profile = LESION_PROFILE[grade]

    def random_point() -> tuple[float, float]:
        angle = rng.uniform(0, 2 * math.pi)
        distance = radius * math.sqrt(rng.uniform(0, 1)) * 0.92
        return centre + math.cos(angle) * distance, centre + math.sin(angle) * distance

    low, high = profile["microaneurysms"]
    for _ in range(rng.randint(low, high)):
        x, y = random_point()
        _blend_circle(image, x, y, rng.uniform(1.0, 2.0), (120, 20, 20), 0.85)

    low, high = profile["haemorrhages"]
    for _ in range(rng.randint(low, high)):
        x, y = random_point()
        _blend_circle(image, x, y, rng.uniform(3.0, 7.0), (95, 15, 15), 0.8)

    low, high = profile["exudates"]
    for _ in range(rng.randint(low, high)):
        x, y = random_point()
        _blend_circle(image, x, y, rng.uniform(2.0, 5.0), (250, 235, 170), 0.85)

    # Proliferative: tangled neovascular fronds.
    for _ in range(profile["neovessels"]):
        x, y = random_point()
        angle = rng.uniform(0, 2 * math.pi)
        for _ in range(rng.randint(12, 22)):
            angle += rng.uniform(-0.7, 0.7)
            x += math.cos(angle) * 1.6
            y += math.sin(angle) * 1.6
            _blend_circle(image, x, y, 1.1, (150, 35, 30), 0.75)


def generate_image(grade: int, size: int, rng: random.Random) -> Image.Image:
    image = _draw_disc(size, rng)
    _draw_vessels(image, rng)
    _draw_lesions(image, grade, rng)

    # Sensor noise so the model cannot latch onto perfectly clean edges.
    noise = np.random.default_rng(rng.randint(0, 2**31)).normal(0, 3.5, image.shape)
    return Image.fromarray(np.clip(image + noise, 0, 255).astype(np.uint8))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a synthetic fundus dataset for pipeline verification."
    )
    parser.add_argument("--output", default="data/synthetic")
    parser.add_argument("--per-class", type=int, default=60)
    parser.add_argument("--size", type=int, default=384)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    total = 0
    for grade, name in enumerate(CLASS_NAMES):
        directory = root / name
        directory.mkdir(parents=True, exist_ok=True)
        for index in range(args.per_class):
            image = generate_image(grade, args.size, rng)
            image.save(directory / f"{name}_{index:04d}.png")
            total += 1
        print(f"  {name:<16} {args.per_class} images")

    # A machine-readable marker so nothing downstream mistakes this for real data.
    (root / "SYNTHETIC_DATA.json").write_text(
        json.dumps(
            {
                "synthetic": True,
                "clinical_value": "none",
                "purpose": "training-pipeline verification only",
                "warning": (
                    "SYNTHETIC DEVELOPMENT DATA — NOT REAL PATIENT DATA. "
                    "Lesions are drawn geometric artefacts, not pathology. A model "
                    "trained on this data has no diagnostic meaning and must never "
                    "be activated for screening."
                ),
                "images": total,
                "classes": list(CLASS_NAMES),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\n{total} images written to {root.resolve()}")
    print(
        "\nSYNTHETIC DEVELOPMENT DATA — NOT REAL PATIENT DATA.\n"
        "Use only to verify the pipeline runs. A model trained on this has no\n"
        "diagnostic meaning whatsoever."
    )


if __name__ == "__main__":
    main()

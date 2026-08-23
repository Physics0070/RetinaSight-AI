"""Retinal dataset adapters.

Handles the two layouts the public DR datasets actually arrive in:

  1. CSV manifest  (APTOS, EyePACS)  -> id column + grade column
  2. folder-per-class                -> no_dr/ mild/ moderate/ severe/ proliferative/

Preprocessing is imported from the *serving* code rather than reimplemented, so
a model cannot be trained on a different pixel distribution from the one it will
see in production.
"""

from __future__ import annotations

import csv
import random
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image
from torch.utils.data import Dataset

# Share the exact preprocessing used at inference time.
_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.ml.preprocessing import (  # noqa: E402
    IMAGENET_MEAN,
    IMAGENET_STD,
    crop_to_retina,
    resize,
)

# The five-class DR scale, in clinical order. Index == label.
CLASS_NAMES: tuple[str, ...] = ("no_dr", "mild", "moderate", "severe", "proliferative")

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}

# Column names used by the common public datasets.
ID_COLUMNS = ("id_code", "image", "image_id", "id", "filename", "name")
LABEL_COLUMNS = ("diagnosis", "level", "label", "grade", "retinopathy_grade", "class")


@dataclass(frozen=True)
class Sample:
    path: Path
    label: int


class DatasetError(RuntimeError):
    """Raised when a dataset directory cannot be interpreted."""


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def discover_samples(data_dir: str | Path) -> list[Sample]:
    """Read a dataset directory in either supported layout."""
    root = Path(data_dir).expanduser().resolve()
    if not root.is_dir():
        raise DatasetError(f"Dataset directory not found: {root}")

    manifest = _find_manifest(root)
    samples = _from_manifest(root, manifest) if manifest else _from_folders(root)

    if not samples:
        raise DatasetError(
            f"No labelled images found under {root}.\n"
            "Expected either a CSV manifest (id + grade columns) or "
            "one folder per class: " + ", ".join(CLASS_NAMES)
        )
    return samples


def _find_manifest(root: Path) -> Path | None:
    for name in ("train.csv", "labels.csv", "trainLabels.csv", "manifest.csv"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    csvs = sorted(root.glob("*.csv"))
    return csvs[0] if csvs else None


def _from_manifest(root: Path, manifest: Path) -> list[Sample]:
    image_dirs = [
        d for d in (root / "train_images", root / "images", root / "train", root)
        if d.is_dir()
    ]

    with manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise DatasetError(f"{manifest} is empty.")

    fieldnames = [f.lower() for f in (rows[0].keys() or [])]
    id_column = _match_column(fieldnames, ID_COLUMNS)
    label_column = _match_column(fieldnames, LABEL_COLUMNS)
    if id_column is None or label_column is None:
        raise DatasetError(
            f"{manifest} needs an id column {ID_COLUMNS} and a grade column "
            f"{LABEL_COLUMNS}; found {fieldnames}."
        )

    samples: list[Sample] = []
    missing = 0
    for row in rows:
        normalised = {k.lower(): v for k, v in row.items()}
        identifier = (normalised.get(id_column) or "").strip()
        raw_label = (normalised.get(label_column) or "").strip()
        if not identifier or raw_label == "":
            continue

        label = _parse_label(raw_label)
        if label is None:
            continue

        path = _resolve_image(image_dirs, identifier)
        if path is None:
            missing += 1
            continue
        samples.append(Sample(path=path, label=label))

    if missing:
        print(f"  note: {missing} manifest rows had no matching image file")
    return samples


def _from_folders(root: Path) -> list[Sample]:
    samples: list[Sample] = []
    for label, name in enumerate(CLASS_NAMES):
        for directory in (root / name, root / str(label)):
            if not directory.is_dir():
                continue
            for path in sorted(directory.iterdir()):
                if path.suffix.lower() in IMAGE_SUFFIXES:
                    samples.append(Sample(path=path, label=label))
    return samples


def _match_column(fieldnames: Sequence[str], candidates: Sequence[str]) -> str | None:
    return next((c for c in candidates if c in fieldnames), None)


def _parse_label(raw: str) -> int | None:
    """Accept either a numeric grade (0-4) or a class name."""
    try:
        value = int(float(raw))
        return value if 0 <= value < len(CLASS_NAMES) else None
    except ValueError:
        pass
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    return CLASS_NAMES.index(key) if key in CLASS_NAMES else None


def _resolve_image(directories: Sequence[Path], identifier: str) -> Path | None:
    candidate = Path(identifier)
    if candidate.suffix:
        for directory in directories:
            path = directory / candidate.name
            if path.is_file():
                return path
    for directory in directories:
        for suffix in (".png", ".jpg", ".jpeg", ".tif", ".tiff"):
            path = directory / f"{identifier}{suffix}"
            if path.is_file():
                return path
    return None


# --------------------------------------------------------------------------- #
# Splitting
# --------------------------------------------------------------------------- #
def stratified_split(
    samples: list[Sample], *, val_fraction: float = 0.15, seed: int = 42
) -> tuple[list[Sample], list[Sample]]:
    """Split preserving class balance.

    DR datasets are heavily skewed toward grade 0; a random split can leave a
    validation set with almost no severe cases, making the metrics meaningless.
    """
    by_class: dict[int, list[Sample]] = {}
    for sample in samples:
        by_class.setdefault(sample.label, []).append(sample)

    rng = random.Random(seed)
    train: list[Sample] = []
    val: list[Sample] = []

    for label, group in sorted(by_class.items()):
        shuffled = group[:]
        rng.shuffle(shuffled)
        cut = max(1, int(len(shuffled) * val_fraction)) if len(shuffled) > 1 else 0
        val.extend(shuffled[:cut])
        train.extend(shuffled[cut:])

    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def class_distribution(samples: Sequence[Sample]) -> dict[str, int]:
    counts = Counter(s.label for s in samples)
    return {CLASS_NAMES[label]: counts.get(label, 0) for label in range(len(CLASS_NAMES))}


def class_weights(samples: Sequence[Sample]) -> list[float]:
    """Inverse-frequency weights, normalised to mean 1.

    Without this a model trained on a real DR dataset collapses to predicting
    'no DR' for everything and still scores ~74% accuracy.
    """
    counts = Counter(s.label for s in samples)
    total = len(samples)
    weights = [
        total / (len(CLASS_NAMES) * counts[label]) if counts.get(label) else 0.0
        for label in range(len(CLASS_NAMES))
    ]
    present = [w for w in weights if w > 0]
    mean = sum(present) / len(present) if present else 1.0
    return [w / mean if w > 0 else 0.0 for w in weights]


# --------------------------------------------------------------------------- #
# Dataset
# --------------------------------------------------------------------------- #
class RetinalDataset(Dataset):
    """Applies the *serving* preprocessing, plus training-time augmentation."""

    def __init__(
        self,
        samples: Sequence[Sample],
        *,
        image_size: int = 224,
        augment: bool = False,
        seed: int = 0,
    ) -> None:
        self.samples = list(samples)
        self.image_size = image_size
        self.augment = augment
        self._rng = random.Random(seed)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int):
        sample = self.samples[index]

        with Image.open(sample.path) as handle:
            rgb = np.asarray(handle.convert("RGB"), dtype=np.uint8)

        # Identical to inference: crop the retinal disc, then resize.
        cropped, _ = crop_to_retina(rgb)
        resized = resize(cropped, (self.image_size, self.image_size))

        if self.augment:
            resized = self._augment(resized)

        scaled = resized.astype(np.float32) / 255.0
        normalised = (scaled - IMAGENET_MEAN) / IMAGENET_STD
        tensor = np.transpose(normalised, (2, 0, 1)).copy()

        import torch

        return torch.from_numpy(tensor), sample.label

    def _augment(self, rgb: np.ndarray) -> np.ndarray:
        """Augmentations that are physically plausible for fundus photography.

        Flips and rotations are safe (either eye, any camera orientation);
        brightness and contrast jitter mirrors real illumination variance.
        Colour-channel shuffling is deliberately excluded — red dominance is a
        genuine signal, not noise.
        """
        if self._rng.random() < 0.5:
            rgb = np.ascontiguousarray(rgb[:, ::-1])
        if self._rng.random() < 0.2:
            rgb = np.ascontiguousarray(rgb[::-1, :])
        if self._rng.random() < 0.5:
            rgb = np.ascontiguousarray(np.rot90(rgb, k=self._rng.randint(1, 3)))

        if self._rng.random() < 0.6:
            brightness = self._rng.uniform(0.85, 1.15)
            contrast = self._rng.uniform(0.85, 1.15)
            mean = rgb.mean()
            adjusted = (rgb.astype(np.float32) - mean) * contrast + mean * brightness
            rgb = np.clip(adjusted, 0, 255).astype(np.uint8)

        return rgb

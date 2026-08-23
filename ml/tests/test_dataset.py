"""Dataset discovery, splitting and class weighting.

Requires torch (RetinalDataset subclasses torch.utils.data.Dataset); the
discovery and splitting tests are skipped cleanly without it.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

torch = pytest.importorskip("torch", reason="training extras not installed")

from datasets.retinal_dataset import (  # noqa: E402
    CLASS_NAMES,
    DatasetError,
    RetinalDataset,
    class_distribution,
    class_weights,
    discover_samples,
    stratified_split,
)


def _write_image(path: Path, size: int = 64) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (size, size), color=(160, 70, 55)).save(path)


@pytest.fixture
def folder_dataset(tmp_path: Path) -> Path:
    root = tmp_path / "folders"
    for index, name in enumerate(CLASS_NAMES):
        for image in range(index + 2):  # deliberately imbalanced
            _write_image(root / name / f"{name}_{image}.png")
    return root


@pytest.fixture
def manifest_dataset(tmp_path: Path) -> Path:
    root = tmp_path / "manifest"
    images = root / "train_images"
    rows = [("img_0", 0), ("img_1", 2), ("img_2", 4), ("img_3", 1)]
    for identifier, _ in rows:
        _write_image(images / f"{identifier}.png")

    with (root / "train.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id_code", "diagnosis"])
        writer.writerows(rows)
    return root


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def test_reads_folder_per_class_layout(folder_dataset: Path) -> None:
    samples = discover_samples(folder_dataset)

    assert len(samples) == sum(range(2, 2 + len(CLASS_NAMES)))
    assert {s.label for s in samples} == set(range(len(CLASS_NAMES)))


def test_reads_csv_manifest_layout(manifest_dataset: Path) -> None:
    """APTOS/EyePACS ship a CSV of id + grade rather than folders."""
    samples = discover_samples(manifest_dataset)

    assert len(samples) == 4
    assert sorted(s.label for s in samples) == [0, 1, 2, 4]


def test_manifest_rows_without_images_are_skipped_not_fatal(
    manifest_dataset: Path,
) -> None:
    with (manifest_dataset / "train.csv").open("a", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(["missing_image", 3])

    samples = discover_samples(manifest_dataset)

    assert len(samples) == 4  # the ghost row is ignored


def test_missing_directory_reports_clearly(tmp_path: Path) -> None:
    with pytest.raises(DatasetError, match="not found"):
        discover_samples(tmp_path / "does-not-exist")


def test_empty_directory_explains_the_expected_layout(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()

    with pytest.raises(DatasetError, match="CSV manifest|one folder per class"):
        discover_samples(tmp_path / "empty")


# --------------------------------------------------------------------------- #
# Splitting
# --------------------------------------------------------------------------- #
def test_split_preserves_every_class_in_validation(folder_dataset: Path) -> None:
    """A random split can leave validation with no severe cases at all, which
    makes the metrics meaningless. Stratification prevents that."""
    samples = discover_samples(folder_dataset)

    train, val = stratified_split(samples, val_fraction=0.3, seed=1)

    assert len(train) + len(val) == len(samples)
    assert set(class_distribution(val)) == set(class_distribution(train))
    for count in class_distribution(val).values():
        assert count > 0


def test_split_is_deterministic_for_a_given_seed(folder_dataset: Path) -> None:
    """Evaluation must be able to reconstruct the exact held-out set."""
    samples = discover_samples(folder_dataset)

    first, _ = stratified_split(samples, seed=7)
    second, _ = stratified_split(samples, seed=7)

    assert [s.path for s in first] == [s.path for s in second]


def test_train_and_validation_do_not_overlap(folder_dataset: Path) -> None:
    samples = discover_samples(folder_dataset)

    train, val = stratified_split(samples, val_fraction=0.3, seed=3)

    assert not ({s.path for s in train} & {s.path for s in val})


# --------------------------------------------------------------------------- #
# Class weighting
# --------------------------------------------------------------------------- #
def test_rare_classes_receive_larger_weights(folder_dataset: Path) -> None:
    """Without this the model predicts 'no DR' for everything."""
    samples = discover_samples(folder_dataset)  # class 0 has 2, class 4 has 6

    weights = class_weights(samples)

    assert weights[0] > weights[4], "the rarest class must be weighted highest"
    assert all(w > 0 for w in weights)


def test_absent_classes_receive_zero_weight(tmp_path: Path) -> None:
    root = tmp_path / "partial"
    _write_image(root / "no_dr" / "a.png")
    _write_image(root / "severe" / "b.png")

    weights = class_weights(discover_samples(root))

    assert weights[CLASS_NAMES.index("mild")] == 0.0
    assert weights[CLASS_NAMES.index("no_dr")] > 0


# --------------------------------------------------------------------------- #
# Tensor output
# --------------------------------------------------------------------------- #
def test_produces_model_ready_tensors(folder_dataset: Path) -> None:
    samples = discover_samples(folder_dataset)
    dataset = RetinalDataset(samples, image_size=224)

    tensor, label = dataset[0]

    assert tensor.shape == (3, 224, 224)
    assert tensor.dtype == torch.float32
    assert isinstance(label, int)


def test_preprocessing_matches_inference(folder_dataset: Path) -> None:
    """Train/serve skew would silently degrade a deployed model, so the
    training pipeline imports the serving preprocessing rather than copying it."""
    from datasets import retinal_dataset

    backend_preprocessing = sys.modules["app.ml.preprocessing"]

    assert retinal_dataset.crop_to_retina is backend_preprocessing.crop_to_retina
    assert retinal_dataset.resize is backend_preprocessing.resize
    assert retinal_dataset.IMAGENET_MEAN is backend_preprocessing.IMAGENET_MEAN


def test_augmentation_changes_the_image_but_not_the_label(folder_dataset: Path) -> None:
    samples = discover_samples(folder_dataset)
    plain = RetinalDataset(samples, image_size=64, augment=False)
    augmented = RetinalDataset(samples, image_size=64, augment=True, seed=5)

    plain_tensor, plain_label = plain[0]
    augmented_tensor, augmented_label = augmented[0]

    assert plain_label == augmented_label
    assert plain_tensor.shape == augmented_tensor.shape

"""Unpack and validate an APTOS download before training touches it.

Catches the failures that otherwise surface forty minutes into a training run:
a truncated archive, a manifest whose images are missing, or a grade column
outside the expected 0-4 scale.

Usage:
    python -m datasets.prepare_aptos --data-dir data/aptos
"""

from __future__ import annotations

import argparse
import csv
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datasets.retinal_dataset import CLASS_NAMES  # noqa: E402

EXPECTED_TRAIN_IMAGES = 3662  # APTOS 2019 training set size


def unpack(data_dir: Path) -> None:
    archives = sorted(data_dir.glob("*.zip"))
    if not archives:
        print("  no archive found (already unpacked?)")
        return

    for archive in archives:
        # A partial download is a truncated zip; fail loudly rather than
        # training on whatever fraction extracted.
        if not zipfile.is_zipfile(archive):
            raise SystemExit(
                f"{archive.name} is not a valid zip — the download is incomplete. "
                "Re-run the download before continuing."
            )

        print(f"  extracting {archive.name} ({archive.stat().st_size / 1e9:.2f} GB)…")
        with zipfile.ZipFile(archive) as handle:
            broken = handle.testzip()
            if broken is not None:
                raise SystemExit(f"{archive.name} is corrupt at {broken}.")
            handle.extractall(data_dir)
        print("  extracted")


def validate(data_dir: Path) -> dict[str, int]:
    manifest = data_dir / "train.csv"
    images = data_dir / "train_images"

    if not manifest.is_file():
        raise SystemExit(f"Expected {manifest} — is this an APTOS download?")
    if not images.is_dir():
        raise SystemExit(f"Expected {images} — is this an APTOS download?")

    with manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    counts: Counter[int] = Counter()
    missing: list[str] = []
    invalid: list[str] = []

    on_disk = {p.stem for p in images.iterdir() if p.suffix.lower() == ".png"}

    for row in rows:
        identifier = (row.get("id_code") or "").strip()
        raw_grade = (row.get("diagnosis") or "").strip()
        if not identifier:
            continue
        try:
            grade = int(raw_grade)
        except ValueError:
            invalid.append(identifier)
            continue
        if not 0 <= grade < len(CLASS_NAMES):
            invalid.append(identifier)
            continue
        counts[grade] += 1
        if identifier not in on_disk:
            missing.append(identifier)

    print(f"\n  manifest rows : {len(rows)}")
    print(f"  images on disk: {len(on_disk)}")

    if invalid:
        raise SystemExit(f"{len(invalid)} rows have a grade outside 0-4, e.g. {invalid[:5]}")
    if missing:
        raise SystemExit(
            f"{len(missing)} manifest rows have no image file, e.g. {missing[:5]}. "
            "The extraction is incomplete."
        )
    if len(rows) < EXPECTED_TRAIN_IMAGES * 0.95:
        print(
            f"  WARNING: expected about {EXPECTED_TRAIN_IMAGES} training rows, "
            f"found {len(rows)}."
        )

    print("\n  class distribution:")
    total = sum(counts.values()) or 1
    for grade, name in enumerate(CLASS_NAMES):
        count = counts.get(grade, 0)
        bar = "#" * int(count / total * 40)
        print(f"    {name:<16}{count:>6}  ({count / total:>5.1%}) {bar}")

    rarest = min(counts.values()) if counts else 0
    commonest = max(counts.values()) if counts else 0
    if rarest and commonest / rarest > 5:
        print(
            f"\n  Note: the commonest grade is {commonest / rarest:.1f}x the rarest. "
            "Class-weighted loss is on by default — keep it on, or the model will "
            "collapse to predicting the majority grade."
        )

    return {CLASS_NAMES[g]: c for g, c in sorted(counts.items())}


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare an APTOS dataset directory.")
    parser.add_argument("--data-dir", default="data/aptos")
    parser.add_argument("--keep-archive", action="store_true", help="Do not delete the zip.")
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    print(f"Preparing {data_dir}")

    unpack(data_dir)
    distribution = validate(data_dir)

    if not args.keep_archive:
        for archive in data_dir.glob("*.zip"):
            size = archive.stat().st_size / 1e9
            archive.unlink()
            print(f"\n  removed {archive.name} ({size:.2f} GB reclaimed)")
        for leftover in data_dir.glob("*.kaggle-partial"):
            leftover.unlink()

    print("\nReady to train:")
    print(f"  python -m training.train --data-dir {args.data_dir} --epochs 25")
    print(f"\n  {sum(distribution.values())} labelled training images")


if __name__ == "__main__":
    main()

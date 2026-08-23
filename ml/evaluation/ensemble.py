"""Measure test-time augmentation and checkpoint ensembling, separately.

Usage:
    python -m evaluation.ensemble --checkpoints models/a/best.pt models/b/best.pt \
        --data-dir data/aptos_456

Why this reports a grid rather than one number
----------------------------------------------
TTA and ensembling are usually applied together and reported as a single
improvement, which makes it impossible to tell which one paid for it — or
whether one of them is doing nothing. Every member is measured alone, then with
TTA, then combined, so each contribution is attributable.

Both decision rules are reported for every configuration. Models trained with
the ordinal objective decide by rounding the expected grade, which deliberately
trades exact-match accuracy for smaller-distance errors; argmax does the
reverse. Reporting one rule alone invites quoting whichever happens to flatter
the metric being discussed.

Guard against a split mismatch
------------------------------
Members must share a held-out set. `train.py` once derived the split from the
run seed, so checkpoints that differ in seed also differed in validation data —
averaging those is leakage, because each model trained on images in the others'
validation splits. Every member's config.json is checked for an identical
split_seed and val_fraction, and the run aborts if they disagree.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datasets.retinal_dataset import (  # noqa: E402
    CLASS_NAMES,
    RetinalDataset,
    class_distribution,
    discover_samples,
    stratified_split,
)
from evaluation.evaluate import load_checkpoint  # noqa: E402
from evaluation.metrics import evaluate_predictions  # noqa: E402

#: Dihedral views the training augmentation makes the model invariant to
#: (horizontal flip p=0.5, vertical flip p=0.2, rot90 p=0.5). Applying a view
#: the model was never trained to expect would add noise, not signal.
TTA_VIEWS: dict[str, list[str]] = {
    "none": ["identity"],
    "flips": ["identity", "hflip", "vflip"],
    "dihedral": [
        "identity", "hflip", "vflip", "rot180",
        "rot90", "rot270", "rot90_hflip", "rot270_hflip",
    ],
}


def apply_view(batch: torch.Tensor, view: str) -> torch.Tensor:
    """Spatial transform on a normalised NCHW batch."""
    if view == "identity":
        return batch
    if view == "hflip":
        return torch.flip(batch, dims=[3])
    if view == "vflip":
        return torch.flip(batch, dims=[2])
    if view == "rot180":
        return torch.flip(batch, dims=[2, 3])
    if view == "rot90":
        return torch.rot90(batch, 1, dims=[2, 3])
    if view == "rot270":
        return torch.rot90(batch, 3, dims=[2, 3])
    if view == "rot90_hflip":
        return torch.flip(torch.rot90(batch, 1, dims=[2, 3]), dims=[3])
    if view == "rot270_hflip":
        return torch.flip(torch.rot90(batch, 3, dims=[2, 3]), dims=[3])
    raise ValueError(f"Unknown TTA view: {view}")


@dataclass
class Member:
    path: Path
    model: torch.nn.Module
    image_size: int
    expected_grade_decision: bool
    config: dict


@torch.no_grad()
def member_probabilities(
    model: torch.nn.Module, loader: DataLoader, device: torch.device, views: list[str]
) -> tuple[np.ndarray, np.ndarray]:
    """Mean softmax over the requested views. Returns (probabilities, targets)."""
    all_probabilities: list[np.ndarray] = []
    all_targets: list[np.ndarray] = []

    for images, labels in loader:
        images = images.to(device, non_blocking=True)
        # Accumulate in float64: averaging many softmax vectors in float16/32
        # loses precision exactly where the classes are close, which is where
        # the decision rules disagree.
        summed = torch.zeros(
            (images.shape[0], len(CLASS_NAMES)), dtype=torch.float64, device=device
        )
        for view in views:
            logits = model(apply_view(images, view)).double()
            summed += torch.softmax(logits, dim=1)
        all_probabilities.append((summed / len(views)).cpu().numpy())
        all_targets.append(labels.numpy())

    return np.concatenate(all_probabilities), np.concatenate(all_targets)


def decide(probabilities: np.ndarray, rule: str) -> np.ndarray:
    """Turn probabilities into grades under the named rule."""
    if rule == "argmax":
        return probabilities.argmax(axis=1)
    if rule == "expected_grade":
        grades = np.arange(probabilities.shape[1], dtype=np.float64)
        expected = (probabilities * grades).sum(axis=1)
        # np.round is half-to-even, matching torch.round and the ONNX Round
        # operator, so this agrees with the exported graph on ties.
        return np.clip(np.round(expected), 0, probabilities.shape[1] - 1).astype(int)
    raise ValueError(f"Unknown decision rule: {rule}")


def summarise(probabilities: np.ndarray, targets: np.ndarray) -> dict[str, dict]:
    """Metrics under both decision rules."""
    out: dict[str, dict] = {}
    for rule in ("expected_grade", "argmax"):
        metrics = evaluate_predictions(targets, decide(probabilities, rule))
        out[rule] = {
            "accuracy": metrics["accuracy"],
            "macro_f1": metrics["macro_f1"],
            "quadratic_kappa": metrics["quadratic_kappa"],
            "referable_sensitivity": metrics["referable_dr"].get("sensitivity", 0.0),
            "referable_specificity": metrics["referable_dr"].get("specificity", 0.0),
        }
    return out


def load_members(paths: list[str], device: torch.device) -> list[Member]:
    members: list[Member] = []
    for raw in paths:
        path = Path(raw)
        model, checkpoint = load_checkpoint(path, device)
        config_path = path.parent / "config.json"
        config = (
            json.loads(config_path.read_text(encoding="utf-8"))
            if config_path.is_file()
            else {}
        )
        members.append(
            Member(
                path=path,
                model=model,
                image_size=checkpoint.get("image_size", 224),
                expected_grade_decision=bool(
                    checkpoint.get("expected_grade_decision", False)
                ),
                config=config,
            )
        )
    return members


def verify_comparable(members: list[Member]) -> tuple[int, float]:
    """All members must share an input size and a held-out split.

    Returns the agreed (split_seed, val_fraction).
    """
    sizes = {m.image_size for m in members}
    if len(sizes) > 1:
        raise SystemExit(f"Members disagree on input size: {sizes}")

    missing = [str(m.path) for m in members if not m.config]
    if missing:
        raise SystemExit(
            "Cannot verify these members share a validation split — no config.json "
            "beside the checkpoint:\n  " + "\n  ".join(missing)
        )

    def split_of(member: Member) -> tuple[int | None, float | None]:
        config = member.config
        if config.get("split_seed") is not None:
            return config["split_seed"], config.get("val_fraction")
        # Runs predating the split_seed fix derived the partition from the run
        # seed, so for those the run seed IS the split seed. Reading it lets a
        # single pre-fix checkpoint still be evaluated on its own held-out set;
        # it does NOT make two such runs ensemblable, which the equality check
        # below is what prevents.
        print(
            f"  note: {member.path.parent.name} predates split_seed; "
            f"using its run seed ({config.get('seed')}) as the split seed"
        )
        return config.get("seed"), config.get("val_fraction")

    splits = {split_of(member) for member in members}
    if len(splits) > 1:
        detail = "\n  ".join(
            f"{m.path.parent.name}: split={split_of(m)[0]}" for m in members
        )
        raise SystemExit(
            "Members were validated on DIFFERENT splits, so averaging them would "
            "score against data they partly trained on:\n  " + detail
        )

    split_seed, val_fraction = splits.pop()
    if split_seed is None:
        raise SystemExit(f"Cannot determine the validation split for {members[0].path}.")
    return int(split_seed), float(val_fraction if val_fraction is not None else 0.15)


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure TTA and ensembling separately.")
    parser.add_argument("--checkpoints", nargs="+", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--tta", choices=sorted(TTA_VIEWS), default="dihedral")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    members = load_members(args.checkpoints, device)
    split_seed, val_fraction = verify_comparable(members)
    image_size = members[0].image_size
    print(
        f"{len(members)} member(s), input {image_size}px, "
        f"split_seed={split_seed}, val_fraction={val_fraction}"
    )

    samples = discover_samples(args.data_dir)
    _, val_samples = stratified_split(
        samples, val_fraction=val_fraction, seed=split_seed
    )
    print(f"Held-out: {len(val_samples)} images  {class_distribution(val_samples)}\n")

    loader = DataLoader(
        RetinalDataset(val_samples, image_size=image_size, augment=False),
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=device.type == "cuda",
    )

    views = TTA_VIEWS[args.tta]
    results: dict[str, dict] = {}
    plain_probabilities: list[np.ndarray] = []
    tta_probabilities: list[np.ndarray] = []
    targets = np.array([])

    for index, member in enumerate(members, start=1):
        label = f"member{index} ({member.path.parent.name})"

        probabilities, targets = member_probabilities(
            member.model, loader, device, ["identity"]
        )
        plain_probabilities.append(probabilities)
        results[f"{label} | no TTA"] = summarise(probabilities, targets)

        if len(views) > 1:
            probabilities, targets = member_probabilities(
                member.model, loader, device, views
            )
            tta_probabilities.append(probabilities)
            results[f"{label} | TTA {args.tta}"] = summarise(probabilities, targets)

    if len(members) > 1:
        results["ENSEMBLE | no TTA"] = summarise(
            np.mean(plain_probabilities, axis=0), targets
        )
        if tta_probabilities:
            results[f"ENSEMBLE | TTA {args.tta}"] = summarise(
                np.mean(tta_probabilities, axis=0), targets
            )

    header = (
        f"{'configuration':<44}{'rule':<16}{'acc':>8}{'kappa':>8}"
        f"{'f1':>8}{'ref.sens':>10}"
    )
    print(header)
    print("-" * len(header))
    for name, by_rule in results.items():
        for rule, metrics in by_rule.items():
            print(
                f"{name:<44}{rule:<16}"
                f"{metrics['accuracy']:>8.4f}{metrics['quadratic_kappa']:>8.4f}"
                f"{metrics['macro_f1']:>8.4f}{metrics['referable_sensitivity']:>10.4f}"
            )

    payload = {
        "measured_on": f"held-out split of {args.data_dir}",
        "split_seed": split_seed,
        "val_fraction": val_fraction,
        "val_size": len(val_samples),
        "image_size": image_size,
        "tta": args.tta,
        "tta_views": views,
        "members": [str(m.path) for m in members],
        "clinically_validated": False,
        "note": (
            "Development metrics on a held-out split. NOT clinical validation. "
            "Accuracy is 5-class exact match; referable sensitivity is the "
            "binary moderate-or-worse decision. They are different metrics and "
            "must not be substituted for one another."
        ),
        "results": results,
    }
    output = Path(args.output) if args.output else Path("models") / "ensemble-report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWritten to {output}")


if __name__ == "__main__":
    main()

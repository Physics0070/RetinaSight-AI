"""Evaluate a trained checkpoint and write the metrics that may be reported.

Usage:
    python -m evaluation.evaluate --checkpoint models/<run>/best.pt --data-dir data/aptos

The numbers this writes to metrics.json are the only figures fit to enter the
model registry. Anything not measured here must not be claimed anywhere.
"""

from __future__ import annotations

import argparse
import json
import sys
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
from evaluation.metrics import evaluate_predictions, format_report  # noqa: E402
from training.losses import expected_grade_predictions  # noqa: E402
from training.model_factory import build_model  # noqa: E402


def load_checkpoint(path: Path, device: torch.device):
    checkpoint = torch.load(path, map_location=device, weights_only=False)
    arch = checkpoint.get("arch", "efficientnet_b0")
    num_classes = checkpoint.get("num_classes", len(CLASS_NAMES))

    # Pretrained weights are unnecessary here — the checkpoint supplies them.
    model = build_model(arch, num_classes=num_classes, pretrained=False)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval().to(device)
    return model, checkpoint


@torch.no_grad()
def predict(model, loader, device, *, expected_grade_decision: bool) -> tuple[np.ndarray, np.ndarray]:
    """Predictions under the checkpoint's own decision rule.

    This used to hardcode argmax, which silently misreported every model
    trained with the ordinal objective: those decide by rounding the expected
    grade, so the figures here disagreed with the run's own metrics.json for
    the very same weights.
    """
    predictions: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    for images, labels in loader:
        logits = model(images.to(device))
        decided = (
            expected_grade_predictions(logits)
            if expected_grade_decision
            else logits.argmax(dim=1)
        )
        predictions.append(decided.cpu().numpy())
        targets.append(labels.numpy())
    return (
        np.concatenate(targets) if targets else np.array([]),
        np.concatenate(predictions) if predictions else np.array([]),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a DR checkpoint.")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--split", choices=["val", "all"], default="val")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--val-fraction", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint_path = Path(args.checkpoint)
    model, checkpoint = load_checkpoint(checkpoint_path, device)
    image_size = checkpoint.get("image_size", 224)

    samples = discover_samples(args.data_dir)
    if args.split == "val":
        # Same seed and fraction as training, so this is genuinely held out.
        _, samples = stratified_split(
            samples, val_fraction=args.val_fraction, seed=args.seed
        )

    print(f"Evaluating {len(samples)} images ({args.split} split) on {device}")
    print(f"Distribution: {class_distribution(samples)}")

    loader = DataLoader(
        RetinalDataset(samples, image_size=image_size, augment=False),
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=2,
    )

    y_true, y_pred = predict(model, loader, device)
    metrics = evaluate_predictions(y_true, y_pred)

    print(format_report(metrics))

    payload = {
        "checkpoint": str(checkpoint_path),
        "architecture": checkpoint.get("arch"),
        "split": args.split,
        "measured_on": f"{args.split} split of {args.data_dir}",
        "clinically_validated": False,
        "note": (
            "Development metrics measured on a held-out split. These are NOT "
            "evidence of clinical performance and must not be presented as such."
        ),
        **metrics,
    }

    output = Path(args.output) if args.output else checkpoint_path.parent / "metrics.json"
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWritten to {output}")
    print(
        "\nReminder: register this model with validation_status='not_validated'.\n"
        "Held-out accuracy is a development signal, not clinical validation."
    )


if __name__ == "__main__":
    main()

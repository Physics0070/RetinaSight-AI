"""Train a diabetic-retinopathy screening model.

Usage:
    python -m training.train --data-dir data/aptos --epochs 20

Produces, under ml/models/<run-name>/:
    best.pt        checkpoint (best validation macro-F1)
    metrics.json   real measured metrics — the only numbers fit to report
    history.json   per-epoch curves

Nothing here fabricates a metric. If a number is not in metrics.json, it was not
measured, and it must not appear in the model registry.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datasets.retinal_dataset import (  # noqa: E402
    CLASS_NAMES,
    RetinalDataset,
    class_distribution,
    class_weights,
    discover_samples,
    stratified_split,
)
from evaluation.metrics import evaluate_predictions  # noqa: E402
from training.losses import OrdinalAwareLoss, expected_grade_predictions  # noqa: E402
from training.model_factory import build_model  # noqa: E402


@dataclass
class TrainingConfig:
    data_dir: str
    arch: str = "efficientnet_b0"
    epochs: int = 20
    batch_size: int = 16
    image_size: int = 224
    learning_rate: float = 3e-4
    weight_decay: float = 1e-4
    val_fraction: float = 0.15
    seed: int = 42
    balance: bool = True
    amp: bool = True
    num_workers: int = 4
    patience: int = 10
    selection_metric: str = "quadratic_kappa"
    # Ordinal term: penalises distant errors, which is what kappa measures.
    distance_weight: float = 0.5
    # Predict by rounding the expected grade rather than taking the argmax.
    expected_grade_decision: bool = True
    dropout: float = 0.4


def set_seed(seed: int) -> None:
    import random

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def resolve_device() -> torch.device:
    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        memory = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"Device: CUDA — {name} ({memory:.1f} GB)")
        return torch.device("cuda")
    print("Device: CPU (no CUDA available — training will be slow)")
    return torch.device("cpu")


def run_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    *,
    optimizer: torch.optim.Optimizer | None = None,
    scaler: torch.amp.GradScaler | None = None,
    expected_grade_decision: bool = False,
) -> tuple[float, np.ndarray, np.ndarray]:
    """One pass. Trains when an optimizer is supplied, else evaluates."""
    training = optimizer is not None
    model.train(training)

    total_loss = 0.0
    seen = 0
    all_predictions: list[np.ndarray] = []
    all_targets: list[np.ndarray] = []

    context = torch.enable_grad() if training else torch.no_grad()
    with context:
        for images, targets in loader:
            images = images.to(device, non_blocking=True)
            targets = targets.to(device, non_blocking=True)

            if training:
                optimizer.zero_grad(set_to_none=True)

            use_amp = scaler is not None and device.type == "cuda"
            with torch.amp.autocast("cuda", enabled=use_amp):
                logits = model(images)
                loss = criterion(logits, targets)

            if training:
                if use_amp:
                    scaler.scale(loss).backward()
                    scaler.step(optimizer)
                    scaler.update()
                else:
                    loss.backward()
                    optimizer.step()

            batch = targets.size(0)
            total_loss += loss.item() * batch
            seen += batch

            detached = logits.detach().float()
            predicted = (
                expected_grade_predictions(detached)
                if expected_grade_decision
                else detached.argmax(dim=1)
            )
            all_predictions.append(predicted.cpu().numpy())
            all_targets.append(targets.detach().cpu().numpy())

    return (
        total_loss / max(seen, 1),
        np.concatenate(all_predictions) if all_predictions else np.array([]),
        np.concatenate(all_targets) if all_targets else np.array([]),
    )


def train(config: TrainingConfig) -> Path:
    set_seed(config.seed)
    device = resolve_device()

    print(f"\nLoading dataset from {config.data_dir}")
    samples = discover_samples(config.data_dir)
    train_samples, val_samples = stratified_split(
        samples, val_fraction=config.val_fraction, seed=config.seed
    )

    print(f"  total {len(samples)}  train {len(train_samples)}  val {len(val_samples)}")
    print(f"  train distribution: {class_distribution(train_samples)}")
    print(f"  val   distribution: {class_distribution(val_samples)}")

    if len(val_samples) < len(CLASS_NAMES):
        print(
            "  WARNING: the validation split is smaller than the number of classes; "
            "metrics will not be meaningful."
        )

    train_loader = DataLoader(
        RetinalDataset(train_samples, image_size=config.image_size, augment=True, seed=config.seed),
        batch_size=config.batch_size,
        shuffle=True,
        num_workers=config.num_workers,
        pin_memory=device.type == "cuda",
        drop_last=len(train_samples) > config.batch_size,
    )
    val_loader = DataLoader(
        RetinalDataset(val_samples, image_size=config.image_size, augment=False),
        batch_size=config.batch_size,
        shuffle=False,
        num_workers=config.num_workers,
        pin_memory=device.type == "cuda",
    )

    model = build_model(config.arch, num_classes=len(CLASS_NAMES)).to(device)

    # Class weighting matters enormously here: without it the model predicts
    # "no DR" for everything and still looks accurate on a skewed dataset.
    if config.balance:
        weights = torch.tensor(class_weights(train_samples), dtype=torch.float32, device=device)
        print(f"  class weights: {[round(w, 3) for w in weights.tolist()]}")
    else:
        weights = None

    criterion = OrdinalAwareLoss(
        class_weights=weights,
        distance_weight=config.distance_weight,
        label_smoothing=0.05,
        num_classes=len(CLASS_NAMES),
    ).to(device)
    print(f"  ordinal distance weight: {config.distance_weight}")

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=config.epochs)
    scaler = torch.amp.GradScaler("cuda") if (config.amp and device.type == "cuda") else None

    run_name = f"{config.arch}-{datetime.now(tz=timezone.utc):%Y%m%d-%H%M%S}"
    output_dir = Path(__file__).resolve().parents[1] / "models" / run_name
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nRun: {run_name}\nOutput: {output_dir}\n")

    history: list[dict] = []
    best_score = -1.0
    epochs_without_improvement = 0
    started = time.time()

    for epoch in range(1, config.epochs + 1):
        epoch_started = time.time()

        train_loss, train_pred, train_true = run_epoch(
            model, train_loader, criterion, device, optimizer=optimizer, scaler=scaler,
            expected_grade_decision=config.expected_grade_decision,
        )
        val_loss, val_pred, val_true = run_epoch(
            model, val_loader, criterion, device,
            expected_grade_decision=config.expected_grade_decision,
        )
        scheduler.step()

        train_metrics = evaluate_predictions(train_true, train_pred)
        val_metrics = evaluate_predictions(val_true, val_pred)
        elapsed = time.time() - epoch_started

        print(
            f"epoch {epoch:>3}/{config.epochs}  "
            f"train loss {train_loss:.4f} f1 {train_metrics['macro_f1']:.4f}  |  "
            f"val loss {val_loss:.4f} acc {val_metrics['accuracy']:.4f} "
            f"f1 {val_metrics['macro_f1']:.4f} kappa {val_metrics['quadratic_kappa']:.4f}  "
            f"({elapsed:.1f}s)"
        )

        history.append(
            {
                "epoch": epoch,
                "train_loss": train_loss,
                "val_loss": val_loss,
                "train_macro_f1": train_metrics["macro_f1"],
                "val_accuracy": val_metrics["accuracy"],
                "val_macro_f1": val_metrics["macro_f1"],
                "val_quadratic_kappa": val_metrics["quadratic_kappa"],
                "learning_rate": scheduler.get_last_lr()[0],
            }
        )

        # Selection metric: quadratic kappa. It is the metric this task is
        # judged on, it cannot be gamed by ignoring the rare severe classes
        # (distance is penalised), and it is markedly more stable than macro-F1,
        # which swings on a 28-sample validation class.
        selection_score = val_metrics[config.selection_metric]
        if selection_score > best_score:
            best_score = selection_score
            epochs_without_improvement = 0
            torch.save(
                {
                    "state_dict": model.state_dict(),
                    "arch": config.arch,
                    "num_classes": len(CLASS_NAMES),
                    "classes": list(CLASS_NAMES),
                    "image_size": config.image_size,
                    "epoch": epoch,
                    "val_selection_score": best_score,
                    "selection_metric": config.selection_metric,
                    "expected_grade_decision": config.expected_grade_decision,
                },
                output_dir / "best.pt",
            )
            (output_dir / "metrics.json").write_text(
                json.dumps(
                    {
                        "measured_on": "held-out validation split",
                        "clinically_validated": False,
                        "note": (
                            "Development metrics from a held-out split. These are "
                            "NOT evidence of clinical performance."
                        ),
                        "epoch": epoch,
                        "dataset": {
                            "source": str(config.data_dir),
                            "train_size": len(train_samples),
                            "val_size": len(val_samples),
                            "val_distribution": class_distribution(val_samples),
                        },
                        **val_metrics,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= config.patience:
                print(f"\nEarly stop: no improvement for {config.patience} epochs.")
                break

    (output_dir / "history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
    (output_dir / "config.json").write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")

    total = time.time() - started
    print(f"\nFinished in {total / 60:.1f} min. Best validation {config.selection_metric}: {best_score:.4f}")
    print(f"Checkpoint: {output_dir / 'best.pt'}")
    print(
        "\nThese are development metrics on a held-out split.\n"
        "They are NOT clinical validation. Register the model as "
        "'not_validated' until real validation exists."
    )
    return output_dir


def parse_args() -> TrainingConfig:
    parser = argparse.ArgumentParser(description="Train a DR screening model.")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--arch", default="efficientnet_b0")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--val-fraction", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--selection-metric", default="quadratic_kappa",
                        choices=["quadratic_kappa", "macro_f1", "accuracy"])
    parser.add_argument("--no-balance", action="store_true")
    parser.add_argument("--no-amp", action="store_true")
    parser.add_argument("--distance-weight", type=float, default=0.5,
                        help="Ordinal penalty strength; 0 disables it.")
    parser.add_argument("--argmax-decision", action="store_true",
                        help="Predict by argmax instead of the rounded expected grade.")
    args = parser.parse_args()

    return TrainingConfig(
        data_dir=args.data_dir,
        arch=args.arch,
        epochs=args.epochs,
        batch_size=args.batch_size,
        image_size=args.image_size,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        val_fraction=args.val_fraction,
        seed=args.seed,
        num_workers=args.num_workers,
        patience=args.patience,
        selection_metric=args.selection_metric,
        balance=not args.no_balance,
        distance_weight=args.distance_weight,
        expected_grade_decision=not args.argmax_decision,
        amp=not args.no_amp,
    )


if __name__ == "__main__":
    train(parse_args())

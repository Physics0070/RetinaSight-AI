"""Compare training configurations across several seeds.

Why several seeds
-----------------
A single training run is not evidence on this dataset. The validation split
contains only ~28 severe cases, so metrics that weight rare classes swing
substantially between runs of the *same* configuration. Two identical
configurations here produced best macro-F1 of 0.720 and 0.669 — a gap larger
than most of the improvements one might hope to measure.

Reporting one run as "config A beats config B" is therefore unsound. This script
runs each configuration over several seeds and reports mean and spread, so a
claimed improvement can be checked against the noise floor.

Usage:
    python -m evaluation.compare_runs --data-dir data/aptos_456 --seeds 3
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]

REPORTED = ("quadratic_kappa", "macro_f1", "accuracy")


def run_once(*, data_dir: str, seed: int, image_size: int, batch_size: int,
             epochs: int, distance_weight: float, learning_rate: float) -> dict | None:
    """Train once and return the resulting metrics."""
    before = {p.parent for p in (ML_ROOT / "models").glob("*/metrics.json")}

    command = [
        sys.executable, "-u", "-m", "training.train",
        "--data-dir", data_dir,
        "--seed", str(seed),
        "--image-size", str(image_size),
        "--batch-size", str(batch_size),
        "--epochs", str(epochs),
        "--distance-weight", str(distance_weight),
        "--learning-rate", str(learning_rate),
        "--num-workers", "6",
    ]
    print(f"\n{'=' * 70}\nseed {seed}  |  distance_weight {distance_weight}  |  {image_size}px")
    print(f"{'=' * 70}")

    result = subprocess.run(command, cwd=str(ML_ROOT), text=True)
    if result.returncode != 0:
        print(f"  seed {seed} FAILED")
        return None

    after = {p.parent for p in (ML_ROOT / "models").glob("*/metrics.json")}
    new = sorted(after - before)
    if not new:
        print(f"  seed {seed} produced no metrics")
        return None

    return json.loads((new[-1] / "metrics.json").read_text(encoding="utf-8"))


def summarise(name: str, results: list[dict]) -> dict:
    print(f"\n{name}: {len(results)} run(s)")
    summary: dict[str, dict] = {}
    for metric in REPORTED:
        values = [r[metric] for r in results if metric in r]
        if not values:
            continue
        mean = statistics.mean(values)
        spread = statistics.stdev(values) if len(values) > 1 else 0.0
        summary[metric] = {
            "mean": round(mean, 4),
            "stdev": round(spread, 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "runs": values,
        }
        print(f"  {metric:<20} {mean:.4f} +/- {spread:.4f}   (min {min(values):.4f}, max {max(values):.4f})")

    sensitivities = [
        r["referable_dr"]["sensitivity"] for r in results if r.get("referable_dr")
    ]
    if sensitivities:
        mean = statistics.mean(sensitivities)
        spread = statistics.stdev(sensitivities) if len(sensitivities) > 1 else 0.0
        summary["referable_sensitivity"] = {
            "mean": round(mean, 4), "stdev": round(spread, 4), "runs": sensitivities
        }
        print(f"  {'referable_sensitivity':<20} {mean:.4f} +/- {spread:.4f}")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare configurations across seeds.")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--image-size", type=int, default=456)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--distance-weight", type=float, default=0.5)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--label", default="configuration")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    results: list[dict] = []
    for index in range(args.seeds):
        metrics = run_once(
            data_dir=args.data_dir,
            seed=42 + index * 101,
            image_size=args.image_size,
            batch_size=args.batch_size,
            epochs=args.epochs,
            distance_weight=args.distance_weight,
            learning_rate=args.learning_rate,
        )
        if metrics:
            results.append(metrics)

    if not results:
        raise SystemExit("No runs completed.")

    print(f"\n{'=' * 70}")
    summary = summarise(args.label, results)

    payload = {
        "label": args.label,
        "seeds": len(results),
        "image_size": args.image_size,
        "distance_weight": args.distance_weight,
        "summary": summary,
        "note": (
            "Mean and standard deviation across seeds. A difference smaller than "
            "the spread is not evidence of an improvement."
        ),
        "clinically_validated": False,
    }

    output = Path(args.output) if args.output else ML_ROOT / "models" / f"{args.label}-summary.json"
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWritten to {output}")
    print(
        "\nA difference smaller than the spread above is not evidence of an "
        "improvement — it is noise."
    )


if __name__ == "__main__":
    main()

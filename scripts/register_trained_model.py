"""Register the trained model directly in the database and activate it.

The API route (`ml/export/register_model.py`) is the normal path and is what an
administrator uses. This variant writes straight to the database so a demo or a
first-time setup can be seeded before the API is up.

It reads the measured numbers from metrics.json and registers the model as
`not_validated` — held-out metrics are a development signal, and the system
refuses to represent them as clinical validation.

Usage:
    python -m scripts.register_trained_model --metrics ml/models/<run>/metrics.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.db.session import SessionLocal  # noqa: E402
from app.domain.enums import (  # noqa: E402
    DeploymentTarget,
    ModelFramework,
    ModelStatus,
    ValidationStatus,
)
from app.models.screening import ModelMetadata  # noqa: E402

CLASSES = ["no_dr", "mild", "moderate", "severe", "proliferative"]


def latest_metrics() -> Path | None:
    runs = sorted((REPO_ROOT / "ml" / "models").glob("*/metrics.json"))
    return runs[-1] if runs else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Register a trained model.")
    parser.add_argument("--metrics", default=None)
    parser.add_argument("--artefact", default="dr-v2.onnx")
    parser.add_argument("--name", default="retinasight-dr")
    parser.add_argument("--version", default="v1")
    parser.add_argument("--architecture", default="efficientnet_b0")
    parser.add_argument(
        "--seed-summary",
        default=None,
        help=(
            "Optional multi-seed summary JSON. The shipped checkpoint is the "
            "best of several runs, so its own metrics are an optimistic draw; "
            "recording the across-seed mean and spread alongside them keeps the "
            "registry honest about expected performance."
        ),
    )
    args = parser.parse_args()

    metrics_path = Path(args.metrics) if args.metrics else latest_metrics()
    if metrics_path is None or not metrics_path.is_file():
        raise SystemExit(
            "No metrics.json found. Train and evaluate a model first:\n"
            "  cd ml && python -m training.train --data-dir data/aptos"
        )

    artefact = REPO_ROOT / "ml" / "models" / args.artefact
    if not artefact.is_file():
        raise SystemExit(
            f"No artefact at {artefact}. Export one first:\n"
            "  cd ml && python -m export.to_onnx --checkpoint <run>/best.pt "
            f"--output models/{args.artefact}"
        )

    # Input size and architecture describe the artefact, so they are read from
    # the sidecar the exporter wrote rather than assumed. Registering a 456px
    # graph as 224px would preprocess every image at the wrong resolution.
    sidecar = artefact.with_suffix(".json")
    if not sidecar.is_file():
        raise SystemExit(
            f"No export metadata at {sidecar}. Re-export the artefact so its "
            "input size and class order are recorded rather than guessed."
        )
    exported = json.loads(sidecar.read_text(encoding="utf-8"))
    input_size = exported.get("input_size")
    if not (isinstance(input_size, list) and len(input_size) == 2):
        raise SystemExit(f"{sidecar} does not record a usable input_size.")
    width, height = int(input_size[0]), int(input_size[1])
    architecture = exported.get("architecture") or args.architecture
    classes = exported.get("classes") or CLASSES

    raw = json.loads(metrics_path.read_text(encoding="utf-8"))
    reported = {k: raw[k] for k in ("accuracy", "macro_f1", "quadratic_kappa", "samples") if k in raw}
    if referable := raw.get("referable_dr"):
        reported["referable_sensitivity"] = referable.get("sensitivity")
        reported["referable_specificity"] = referable.get("specificity")
    reported["measured_on"] = raw.get("measured_on", "held-out validation split")
    reported["decision_rule"] = exported.get("decision_rule", "argmax")
    reported["clinically_validated"] = False

    # A single run's numbers are the best of several draws on a 546-image split
    # whose run-to-run spread exceeds most improvements worth claiming. Where a
    # multi-seed summary exists, the mean and spread are what should be read as
    # this model's expected performance.
    if args.seed_summary:
        summary_path = Path(args.seed_summary)
        if not summary_path.is_file():
            raise SystemExit(f"No seed summary at {summary_path}.")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        reported["across_seeds"] = {
            "seeds": summary.get("seeds"),
            **{
                metric: {"mean": values.get("mean"), "stdev": values.get("stdev")}
                for metric, values in (summary.get("summary") or {}).items()
            },
        }
        reported["note_on_selection"] = (
            "The shipped checkpoint is the best of "
            f"{summary.get('seeds')} seeds by quadratic kappa. Read "
            "'across_seeds' as expected performance; the top-level figures are "
            "this checkpoint's own and are an optimistic draw."
        )

    with SessionLocal() as db:
        existing = (
            db.query(ModelMetadata)
            .filter(ModelMetadata.name == args.name, ModelMetadata.version == args.version)
            .one_or_none()
        )
        if existing is not None:
            print(f"{args.name}:{args.version} is already registered.")
            return

        # Exactly one model serves at a time.
        for other in db.query(ModelMetadata).filter(
            ModelMetadata.status == ModelStatus.ACTIVE.value
        ):
            other.status = ModelStatus.DEPRECATED.value

        db.add(
            ModelMetadata(
                name=args.name,
                version=args.version,
                framework=ModelFramework.ONNX.value,
                deployment_target=DeploymentTarget.CLOUD.value,
                architecture=architecture,
                input_width=width,
                input_height=height,
                classes=classes,
                model_path=args.artefact,
                status=ModelStatus.ACTIVE.value,
                # Held-out metrics are NOT clinical validation.
                validation_status=ValidationStatus.NOT_VALIDATED.value,
                validation_metrics=reported,
                notes=f"Trained model. Metrics from {metrics_path.name}.",
            )
        )
        db.commit()

    print(f"Registered {args.name}:{args.version} -> {args.artefact} (ACTIVE)")
    print(f"  {json.dumps(reported, indent=2)}")
    print("\nvalidation_status = not_validated (correct: no clinical study exists)")


if __name__ == "__main__":
    main()

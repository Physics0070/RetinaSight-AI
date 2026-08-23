"""Register a trained model with a running RetinaSight AI backend.

Does exactly what the Admin -> Models screen does, for people who would rather
not click. It reads the measured numbers straight from ``metrics.json`` so the
registry can only ever contain figures that were actually produced by an
evaluation run.

It deliberately does **not** mark the model clinically validated. That status
requires prospective clinical evaluation, and the API rejects the claim without
evidence regardless of what is passed here.

Usage:
    python -m export.register_model \
        --api http://localhost:8000/api/v1 \
        --email admin@retinasight.ai \
        --artefact dr-v1.onnx \
        --metrics models/<run>/metrics.json \
        --activate
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

CLASSES = ["no_dr", "mild", "moderate", "severe", "proliferative"]


def call(
    api: str, path: str, *, method: str = "GET", body: dict | None = None, token: str | None = None
) -> dict:
    request = urllib.request.Request(f"{api}{path}", method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    payload = json.dumps(body).encode() if body is not None else None

    try:
        with urllib.request.urlopen(request, payload, timeout=30) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        try:
            message = json.loads(detail)["error"]["message"]
        except Exception:  # noqa: BLE001
            message = detail[:300]
        raise SystemExit(f"{method} {path} failed ({error.code}): {message}") from error
    except urllib.error.URLError as error:
        raise SystemExit(
            f"Could not reach the API at {api}. Is the backend running?\n  {error.reason}"
        ) from error


def main() -> None:
    parser = argparse.ArgumentParser(description="Register a trained model.")
    # No literal default: the API address comes from the environment or the
    # flag, the same rule the rest of the project follows.
    parser.add_argument(
        "--api",
        default=os.environ.get("RS_API_BASE_URL"),
        help="API root, e.g. https://host/api/v1. Defaults to $RS_API_BASE_URL.",
    )
    parser.add_argument("--email", required=True, help="Administrator email.")
    parser.add_argument("--artefact", required=True, help="Filename inside RS_MODEL_DIR.")
    parser.add_argument("--metrics", required=True, help="Path to metrics.json.")
    parser.add_argument("--name", default="retinasight-dr")
    parser.add_argument("--version", default="v1")
    parser.add_argument("--architecture", default="efficientnet_b0")
    parser.add_argument("--framework", default="onnx", choices=["onnx", "pytorch", "tflite"])
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument("--activate", action="store_true", help="Set status to ACTIVE.")
    args = parser.parse_args()

    if not args.api:
        raise SystemExit(
            "No API address. Pass --api https://host/api/v1 or set RS_API_BASE_URL."
        )

    metrics_path = Path(args.metrics)
    if not metrics_path.is_file():
        raise SystemExit(f"No metrics file at {metrics_path}. Run evaluation first.")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

    # Only headline, comparable figures go into the registry.
    reported = {
        key: metrics[key]
        for key in ("accuracy", "macro_f1", "quadratic_kappa", "samples")
        if key in metrics
    }
    if referable := metrics.get("referable_dr"):
        reported["referable_sensitivity"] = referable.get("sensitivity")
        reported["referable_specificity"] = referable.get("specificity")
    reported["measured_on"] = metrics.get("measured_on", "held-out validation split")
    reported["clinically_validated"] = False

    password = getpass.getpass(f"Password for {args.email}: ")
    token = call(
        args.api, "/auth/login", method="POST", body={"email": args.email, "password": password}
    )["tokens"]["access_token"]
    print("  authenticated")

    model = call(
        args.api,
        "/models",
        method="POST",
        token=token,
        body={
            "name": args.name,
            "version": args.version,
            "framework": args.framework,
            "deployment_target": "cloud",
            "architecture": args.architecture,
            "input_width": args.image_size,
            "input_height": args.image_size,
            "classes": CLASSES,
            "model_path": args.artefact,
            "notes": f"Trained on {metrics.get('dataset', {}).get('source', 'unknown dataset')}.",
        },
    )
    print(f"  registered {model['name']}:{model['version']}  (id {model['id']})")

    call(
        args.api,
        f"/models/{model['id']}/validation",
        method="POST",
        token=token,
        body={
            # Development metrics are NOT clinical validation.
            "validation_status": "not_validated",
            "validation_metrics": reported,
            "notes": "Held-out development metrics. Not clinically validated.",
        },
    )
    print("  metrics recorded (status: not_validated)")

    if args.activate:
        call(
            args.api,
            f"/models/{model['id']}/status",
            method="POST",
            token=token,
            body={"status": "active"},
        )
        print("  activated - now serving inference")

    status = call(args.api, "/models/status", token=token)
    print("\nServing model:")
    print(f"  version            : {status.get('model_version')}")
    print(f"  framework          : {status.get('framework')}")
    print(f"  available          : {status.get('available')}")
    print(f"  development model  : {status.get('is_development_model')}")
    print(f"  clinically validated: {status.get('clinically_validated')}")

    if status.get("is_development_model"):
        print(
            "\n  NOTE: the placeholder is still serving. Check that the artefact "
            "exists inside RS_MODEL_DIR and that the model status is ACTIVE."
        )


if __name__ == "__main__":
    sys.exit(main())

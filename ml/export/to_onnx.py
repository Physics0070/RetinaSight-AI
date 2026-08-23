"""Export a checkpoint to ONNX for serving.

ONNX is the interchange format shared between the cloud service and the mobile
edge deployment, so both run the same graph.

The export is verified before it is written: PyTorch and ONNX Runtime must agree
on the logits for the same input. A silently-diverging export would produce
wrong screening results with no error anywhere.

Usage:
    python -m export.to_onnx --checkpoint models/<run>/best.pt --output ../ml/models/dr-v1.onnx
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datasets.retinal_dataset import CLASS_NAMES  # noqa: E402
from export.cam_wrapper import CamWrapper, verify_wrapper_matches  # noqa: E402
from training.model_factory import build_model  # noqa: E402

# What parity actually has to guarantee is that the exported graph makes the
# same *decisions*, not that two different conv implementations produce
# bit-identical floats. Raw logits of a trained network are large (±10 or more),
# so an absolute logit tolerance is meaninglessly strict — PyTorch and ONNX
# Runtime legitimately differ at ~1e-3 there through kernel choice and fusion.
#
# So the contract is:
#   1. the predicted class must match on every probe  (hard requirement)
#   2. softmax probabilities must agree closely       (what the risk engine reads)
#   3. logit divergence is reported, not enforced     (diagnostic only)
PROBABILITY_TOLERANCE = 1e-3
PARITY_PROBES = 8


def export(checkpoint_path: Path, output_path: Path, *, opset: int = 17) -> dict:
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    arch = checkpoint.get("arch", "efficientnet_b0")
    num_classes = checkpoint.get("num_classes", len(CLASS_NAMES))
    image_size = checkpoint.get("image_size", 224)

    model = build_model(arch, num_classes=num_classes, pretrained=False)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()

    dummy = torch.randn(1, 3, image_size, image_size)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Export through the CAM wrapper so the served graph can produce
    # explanations. ONNX Runtime has no gradients, so without this the
    # deployed model would return a blank heatmap.
    wrapper = CamWrapper(model, arch)
    wrapper.eval()
    wrapper_drift = verify_wrapper_matches(model, wrapper, dummy)
    if wrapper_drift > 1e-5:
        raise RuntimeError(
            f"The CAM wrapper changes the model's logits by {wrapper_drift:.2e}. "
            "Refusing to export a graph that does not match the checkpoint."
        )

    torch.onnx.export(
        wrapper,
        dummy,
        str(output_path),
        input_names=["input"],
        output_names=["logits", "cam"],
        # Batch is dynamic so the server can batch requests later.
        dynamic_axes={
            "input": {0: "batch"},
            "logits": {0: "batch"},
            "cam": {0: "batch"},
        },
        opset_version=opset,
        do_constant_folding=True,
    )
    print(f"Exported to {output_path} ({output_path.stat().st_size / 1e6:.1f} MB)")

    try:
        parity = _verify_parity(wrapper, output_path, dummy)
    except RuntimeError:
        # Never leave an uncertified artefact where a deploy could pick it up.
        output_path.unlink(missing_ok=True)
        print(f"  removed {output_path.name} — it did not pass verification")
        raise

    metadata = {
        "architecture": arch,
        "classes": checkpoint.get("classes", list(CLASS_NAMES)),
        "input_size": [image_size, image_size],
        "opset": opset,
        "source_checkpoint": str(checkpoint_path),
        "parity_max_probability_difference": parity,
        "supports_cam": True,
        "exact_cam": wrapper.supports_exact_cam,
        "clinically_validated": False,
    }
    metadata_path = output_path.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Metadata written to {metadata_path}")
    return metadata


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - values.max(axis=-1, keepdims=True)
    exponentiated = np.exp(shifted)
    return exponentiated / exponentiated.sum(axis=-1, keepdims=True)


def _verify_parity(model, onnx_path: Path, dummy: torch.Tensor) -> float | None:
    """Confirm the exported graph makes the same decisions as the checkpoint.

    Probes several random inputs rather than one, so a divergence that only
    shows up for certain activations cannot slip through.
    """
    try:
        import onnxruntime as ort
    except ImportError:
        print(
            "  WARNING: onnxruntime is not installed, so the export could NOT be "
            "verified. Install it and re-run before serving this model."
        )
        return None

    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(0)

    worst_logit_difference = 0.0
    worst_probability_difference = 0.0
    disagreements = 0

    for probe in range(PARITY_PROBES):
        # Probe 0 is the caller's tensor; the rest are fresh random inputs.
        tensor = dummy if probe == 0 else torch.from_numpy(
            rng.standard_normal(tuple(dummy.shape)).astype(np.float32)
        )

        with torch.no_grad():
            expected = model(tensor)[0].numpy()
        actual = session.run(None, {"input": tensor.numpy()})[0]

        worst_logit_difference = max(
            worst_logit_difference, float(np.abs(expected - actual).max())
        )
        worst_probability_difference = max(
            worst_probability_difference,
            float(np.abs(_softmax(expected) - _softmax(actual)).max()),
        )
        if int(np.argmax(expected)) != int(np.argmax(actual)):
            disagreements += 1

    if disagreements:
        raise RuntimeError(
            f"ONNX export changes the predicted class on {disagreements}/"
            f"{PARITY_PROBES} probes. Refusing to certify this artefact."
        )
    if worst_probability_difference > PROBABILITY_TOLERANCE:
        raise RuntimeError(
            f"ONNX probabilities diverge from PyTorch by "
            f"{worst_probability_difference:.2e} (limit {PROBABILITY_TOLERANCE:.0e}). "
            "Refusing to certify this artefact."
        )

    print(
        f"  parity verified over {PARITY_PROBES} probes: "
        f"predicted class identical, max probability difference "
        f"{worst_probability_difference:.2e} "
        f"(logit difference {worst_logit_difference:.2e}, diagnostic only)"
    )
    return worst_probability_difference


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a DR checkpoint to ONNX.")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--opset", type=int, default=17)
    args = parser.parse_args()

    export(Path(args.checkpoint), Path(args.output), opset=args.opset)

    print(
        "\nNext: register the model in Admin -> Models with "
        "validation_status='not_validated', then activate it."
    )


if __name__ == "__main__":
    main()

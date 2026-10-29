"""Assemble the directory that gets pushed to a Hugging Face Space.

A Space is a separate git repository whose root must contain a Dockerfile and a
README.md with Space metadata. This repository's root cannot be that, so this
script copies exactly what the container needs into an output directory:

    <out>/Dockerfile
    <out>/README.md
    <out>/backend/...        (runtime code only -- no tests, caches or secrets)
    <out>/ml/models/dr-v2.onnx, dr-v2.json

Usage:
    python scripts/package_hf_space.py [--out build/hf-space] [--model dr-v2]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "deploy" / "free" / "huggingface"

# Never shipped: they are either dead weight in an image or unsafe to publish.
BACKEND_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "tests", ".pytest_cache", ".venv", "venv",
    ".env", ".env.*", "*.db", "*.sqlite", "*.sqlite3", "pytest.ini",
    "requirements-ml.txt",
)


def package(out: Path, model: str) -> list[str]:
    onnx = ROOT / "ml" / "models" / f"{model}.onnx"
    card = ROOT / "ml" / "models" / f"{model}.json"
    for required in (onnx, card, SRC / "Dockerfile", SRC / "README.md"):
        if not required.is_file():
            raise SystemExit(f"Missing required file: {required.relative_to(ROOT)}")

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    shutil.copy2(SRC / "Dockerfile", out / "Dockerfile")
    shutil.copy2(SRC / "README.md", out / "README.md")
    shutil.copytree(ROOT / "backend", out / "backend", ignore=BACKEND_IGNORE)

    models = out / "ml" / "models"
    models.mkdir(parents=True)
    shutil.copy2(onnx, models / onnx.name)
    shutil.copy2(card, models / card.name)

    return sorted(str(p.relative_to(out)).replace("\\", "/") for p in out.rglob("*") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="build/hf-space")
    parser.add_argument("--model", default="dr-v2", help="model filename stem under ml/models")
    args = parser.parse_args()

    out = (ROOT / args.out).resolve()
    files = package(out, args.model)
    print(f"Packaged {len(files)} files into {out}")
    print(f"  model: ml/models/{args.model}.onnx")
    print("Next: push this directory to your Space's git repository.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

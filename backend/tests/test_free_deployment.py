"""The free-tier bundle must stay deployable.

These guard the failure modes that only show up after pushing to a host:
a container missing the model, secrets copied into the image, or a Space card
that points traffic at the wrong port.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "deploy" / "free" / "huggingface"


def _packager():
    spec = importlib.util.spec_from_file_location(
        "package_hf_space", REPO_ROOT / "scripts" / "package_hf_space.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_space_card_and_dockerfile_agree_on_the_port() -> None:
    card = (SRC / "README.md").read_text(encoding="utf-8")
    dockerfile = (SRC / "Dockerfile").read_text(encoding="utf-8")

    port = re.search(r"^app_port:\s*(\d+)", card, re.MULTILINE)
    assert port, "Space README.md must declare app_port"
    assert "sdk: docker" in card
    assert f"--port {port.group(1)}" in dockerfile, "uvicorn must listen on the declared app_port"


def test_container_migrates_before_serving_and_does_not_run_as_root() -> None:
    dockerfile = (SRC / "Dockerfile").read_text(encoding="utf-8")
    assert "alembic upgrade head && uvicorn" in dockerfile
    assert "USER app" in dockerfile


def test_bundle_ships_the_model_and_no_secrets(tmp_path) -> None:
    files = set(_packager().package(tmp_path / "bundle", "dr-v2"))

    assert "ml/models/dr-v2.onnx" in files, "an image without the model would serve nothing"
    assert "ml/models/dr-v2.json" in files
    assert "Dockerfile" in files and "README.md" in files

    leaked = [
        f for f in files
        if Path(f).name.startswith(".env")
        or f.endswith((".db", ".sqlite", ".sqlite3", ".pem", ".key"))
        or "/tests/" in f
        or "__pycache__" in f
    ]
    assert not leaked, f"bundle contains files that must not ship: {leaked}"


def test_spa_fallback_exists_for_static_hosts() -> None:
    redirects = REPO_ROOT / "dashboard" / "public" / "_redirects"
    assert redirects.is_file(), "deep links 404 on Cloudflare Pages without this"
    assert "/index.html" in redirects.read_text(encoding="utf-8")

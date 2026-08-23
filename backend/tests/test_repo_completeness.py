"""The repository must actually contain the code it claims to.

A `.gitignore` rule written as a bare `name/` matches a directory called `name`
at *any* depth. A rule meant to exclude a dev object store — `storage/` —
therefore also excluded `backend/app/storage/`: the object-storage module,
imported by the image, quality, inference and screening services and by two
routers.

Nothing failed locally, because the files were present on disk. But the
published repository did not contain them, so a fresh clone could not import
the backend at all, and the whole test suite would fail to collect.

Local test runs cannot notice this by construction — they read the working
tree, not the index. This guard asks git directly.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Trees that hold hand-written source. Everything here must be committed.
SOURCE_TREES = ("backend/app", "backend/tests", "dashboard/src", "ml", "scripts", "mobile/lib")

SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".dart", ".css", ".sql"}

#: Directories that legitimately hold generated or vendored files.
GENERATED = (
    "node_modules/", ".venv/", "venv/", "__pycache__/", ".pytest_cache/",
    ".dart_tool/", "dist/", "build/", "ml/data/", "ml/models/",
)


def _git() -> str | None:
    """Git executable, or None when it is not available to this environment."""
    return shutil.which("git")


def _is_generated(path: str) -> bool:
    return any(marker in f"{path}/" for marker in GENERATED)


@pytest.fixture(scope="module")
def ignored_files() -> list[str]:
    git = _git()
    if git is None:
        pytest.skip("git is not on PATH; cannot inspect what the repository tracks")

    result = subprocess.run(
        [git, "ls-files", "--others", "--ignored", "--exclude-standard"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        pytest.skip(f"git ls-files failed: {result.stderr.strip()}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def test_no_source_file_is_excluded_from_the_repository(ignored_files) -> None:
    """The regression: source present on disk but absent from the repository."""
    excluded = [
        path
        for path in ignored_files
        if Path(path).suffix in SOURCE_SUFFIXES
        and any(path.startswith(f"{tree}/") for tree in SOURCE_TREES)
        and not _is_generated(path)
    ]

    assert not excluded, (
        "These source files exist on disk but .gitignore excludes them, so they "
        "are missing from the repository:\n  "
        + "\n  ".join(sorted(excluded))
        + "\n\nA bare 'name/' pattern matches at every depth — anchor it with a "
        "leading slash."
    )


def test_the_object_storage_module_is_tracked() -> None:
    """Named explicitly, because this is the module that actually went missing."""
    git = _git()
    if git is None:
        pytest.skip("git is not on PATH; cannot inspect what the repository tracks")

    result = subprocess.run(
        [git, "ls-files", "backend/app/storage/"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    tracked = {Path(line).name for line in result.stdout.splitlines() if line.strip()}

    for module in ("__init__.py", "base.py", "factory.py", "local.py", "s3.py"):
        assert module in tracked, (
            f"backend/app/storage/{module} is not tracked by git. The backend "
            "imports this package at startup; without it a clone cannot run."
        )


def test_every_package_the_backend_imports_at_startup_is_tracked() -> None:
    """Generalises the check to every app subpackage, not just storage."""
    git = _git()
    if git is None:
        pytest.skip("git is not on PATH; cannot inspect what the repository tracks")

    result = subprocess.run(
        [git, "ls-files", "backend/app/"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    tracked = {line.strip() for line in result.stdout.splitlines() if line.strip()}

    on_disk = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "backend" / "app").rglob("*.py")
        if "__pycache__" not in path.parts
    }

    missing = sorted(on_disk - tracked)
    assert not missing, f"Backend source files missing from the repository: {missing}"

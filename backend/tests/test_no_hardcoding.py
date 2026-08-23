"""Guards that keep the codebase free of hardcoded config, secrets and Firebase.

These run in CI with everything else, so a regression fails the build rather
than waiting to be noticed in review.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER = REPO_ROOT / "scripts" / "check_no_hardcoding.py"


def test_repository_has_no_hardcoded_configuration_or_secrets() -> None:
    """Runs the full scanner; the assertion message carries the findings."""
    result = subprocess.run(
        [sys.executable, str(SCANNER)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"Hardcoding scan failed:\n{result.stdout}"


def test_no_firebase_dependency_anywhere() -> None:
    """Firebase is explicitly excluded from this architecture.

    Scans code and dependency manifests only — prose files legitimately discuss
    the constraint itself.
    """
    forbidden = ("firebase", "firestore", "firebase-admin", "firebaseconfig")
    skip_dirs = {
        ".git", ".venv", "node_modules", "__pycache__", "dist", "build",
        ".pytest_cache", "var", ".dart_tool",
    }
    skip_files = {"package-lock.json", "check_no_hardcoding.py", "test_no_hardcoding.py"}

    offenders: list[str] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts) or path.name in skip_files:
            continue
        if path.suffix not in {".py", ".ts", ".tsx", ".js", ".json", ".dart", ".yaml", ".yml", ".txt"}:
            continue
        content = path.read_text(encoding="utf-8", errors="ignore").lower()
        if any(token in content for token in forbidden):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert not offenders, f"Firebase references found in: {offenders}"


def test_no_env_file_is_committed() -> None:
    """Only .env.example may exist in the repository."""
    committed = [
        str(p.relative_to(REPO_ROOT))
        for p in REPO_ROOT.rglob(".env*")
        if p.is_file()
        and p.name != ".env.example"
        and ".venv" not in p.parts
        and "node_modules" not in p.parts
    ]
    assert not committed, f"Real .env files must never be committed: {committed}"


def test_env_example_documents_every_setting() -> None:
    """Each RS_-prefixed setting must appear in .env.example."""
    from app.core.config import Settings

    example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    documented = {
        line.split("=", 1)[0].strip()
        for line in example.splitlines()
        if line.strip() and not line.strip().startswith("#") and "=" in line
    }

    missing = [
        f"RS_{name.upper()}"
        for name in Settings.model_fields
        if f"RS_{name.upper()}" not in documented
    ]
    assert not missing, f"Undocumented settings in .env.example: {missing}"


def _load_scanner():
    """Import the scanner module by path (scripts/ is not a package)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("rs_scanner", SCANNER)
    module = importlib.util.module_from_spec(spec)
    # @dataclass resolves annotations through sys.modules during exec.
    sys.modules["rs_scanner"] = module
    spec.loader.exec_module(module)
    return module


def test_every_exemption_is_narrow_not_wholesale() -> None:
    """No allowlist entry may excuse a file from every rule.

    A blanket exemption is a hole, not a policy: it would let an allowlisted
    file carry a private key or a Firebase import undetected.
    """
    scanner = _load_scanner()
    all_rules = {rule.name for rule in scanner.RULES}

    for path, (exempt, reason) in scanner.ALLOWLIST.items():
        assert exempt, f"{path} exempts nothing — remove the entry instead"
        assert exempt < all_rules, f"{path} is exempt from every rule"
        assert exempt <= all_rules, f"{path} names rules that do not exist: {exempt - all_rules}"
        assert reason.strip(), f"{path} has no stated reason"

    for marker, exempt in scanner.ALLOWLISTED_DIRECTORIES:
        assert exempt < all_rules, f"directory {marker} is exempt from every rule"


def test_exempted_paths_are_still_scanned_for_other_rules(tmp_path) -> None:
    """The narrowing must actually work end to end, not just in the table.

    Plants a credential inside an allowlisted directory and asserts the scan
    fails. Under the previous blanket allowlist this would have passed.
    """
    scanner = _load_scanner()

    # Assembled from fragments so this very file does not trip the scanner —
    # tests/ is deliberately NOT exempt from the cloud-credential rule.
    fake_key = "AKIA" + "IOSFODNN7EXAMPLE"
    planted = Path(__file__).parent / "_planted_secret_fixture.py"
    planted.write_text(f'KEY = "{fake_key}"\n', encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, str(SCANNER)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode != 0, (
            "A cloud credential inside tests/ was not detected — the directory "
            f"exemption is too broad.\n{result.stdout}"
        )
        assert "aws_key" in result.stdout
    finally:
        planted.unlink(missing_ok=True)

    # Guards the guard: confirm the failure above came from the plant and not
    # from some unrelated pre-existing violation.
    after = subprocess.run(
        [sys.executable, str(SCANNER)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert after.returncode == 0, f"Scan still failing after cleanup:\n{after.stdout}"


def test_env_files_are_scanned_at_all() -> None:
    """.env files carry no scannable suffix but are where secrets get pasted."""
    scanner = _load_scanner()
    scanned = {str(p.relative_to(REPO_ROOT)).replace("\\", "/") for p in scanner.iter_files()}
    assert ".env.example" in scanned


def test_no_secret_defaults_reach_production() -> None:
    """Insecure development defaults must be obvious, not subtle."""
    from app.core.config import Settings

    defaults = Settings()
    for field in ("jwt_secret", "jwt_refresh_secret", "storage_signing_secret"):
        value = getattr(defaults, field)
        assert "dev-only" in value or "change" in value.lower(), (
            f"{field} default must be clearly marked as insecure"
        )

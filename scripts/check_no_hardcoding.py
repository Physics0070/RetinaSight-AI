#!/usr/bin/env python3
"""Automated hardcoding / secret / Firebase scan.

Fails the build when application configuration, credentials, clinical
thresholds or Firebase dependencies are written into source files.

Allowed locations (documentation, examples, fixtures and the seeded default
policy) are declared in ALLOWLIST below, each with a reason.

Usage:
    python scripts/check_no_hardcoding.py [--verbose]
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCAN_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".dart", ".yaml", ".yml", ".json"}

# Generated dependency manifests: they legitimately contain registry URLs and
# integrity hashes, and are not application configuration.
SKIP_FILENAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "pubspec.lock",
    "poetry.lock",
}

SKIP_DIRECTORIES = {
    ".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "var", ".dart_tool",
    "migrations",  # generated schema DDL, reviewed at generation time
}

# Files permitted to contain otherwise-flagged strings, with justification.
ALLOWLIST: dict[str, str] = {
    ".env.example": "documents required variables using placeholder values",
    "dashboard/.env.example": "documents required frontend variables",
    "backend/app/domain/config_defaults.py": "seeded default policy; runtime reads the database",
    "backend/app/domain/rbac_matrix.py": "default security policy, deliberately version-controlled",
    "scripts/check_no_hardcoding.py": "this scanner contains the patterns it searches for",
    # Demo seeding uses known credentials by design so a reviewer can sign in.
    # The script refuses to run when RS_ENV=production.
    "scripts/seed_demo.py": "clearly-labelled synthetic demo data; refuses to run in production",
    # These two files ARE the configuration layer. Their localhost values are
    # development fallbacks that every deployment overrides via environment
    # variables (RS_* / VITE_*); no other module may contain such a literal.
    "backend/app/core/config.py": "configuration layer; localhost defaults are env-overridable",
    "dashboard/src/lib/config.ts": "configuration layer; localhost default is env-overridable",
    "mobile/lib/core/config.dart": "configuration layer; emulator-loopback default is --dart-define-overridable",
}

ALLOWLISTED_DIRECTORIES = ("tests/", "test/", "__tests__/", "docs/")


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    message: str


RULES: list[Rule] = [
    Rule(
        "firebase",
        re.compile(r"\bfirebase|firestore|firebase[-_]admin|firebaseConfig", re.I),
        "Firebase must not be used anywhere in this project.",
    ),
    Rule(
        "hardcoded_url",
        re.compile(r"""["'](https?://(?!localhost|127\.0\.0\.1|10\.0\.2\.2|fonts\.|www\.w3\.org|pytorch\.org)[^"']+)["']"""),
        "Hardcoded external URL — read it from configuration instead.",
    ),
    Rule(
        "localhost_url",
        re.compile(r"""["']https?://(localhost|127\.0\.0\.1|10\.0\.2\.2)[:/][^"']*["']"""),
        "Hardcoded localhost URL — belongs in .env / configuration defaults.",
    ),
    Rule(
        "api_key",
        re.compile(
            r"""(api[_-]?key|secret[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*["'][A-Za-z0-9_\-]{12,}["']""",
            re.I,
        ),
        "Possible hardcoded credential.",
    ),
    Rule(
        "password_literal",
        re.compile(r"""password\s*[:=]\s*["'](?!.*\{)[^"']{6,}["']""", re.I),
        "Possible hardcoded password.",
    ),
    Rule(
        "aws_key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "AWS access key ID committed to source.",
    ),
    Rule(
        "private_key",
        re.compile(r"-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
        "Private key committed to source.",
    ),
    Rule(
        "postgres_dsn",
        re.compile(r"postgres(ql)?(\+\w+)?://[^\s\"']*:[^\s\"']*@"),
        "Database connection string with credentials.",
    ),
    Rule(
        "clinical_threshold",
        re.compile(
            r"(confidence|risk[_-]?score|blur|quality|threshold)\s*[<>]=?\s*0?\.\d+",
            re.I,
        ),
        "Clinical threshold compared against a literal — read it from the config service.",
    ),
    Rule(
        "referral_literal",
        re.compile(r"""referral\s*=\s*["'](urgent|routine|consultation)["']""", re.I),
        "Referral rule hardcoded — the referral engine reads configuration.",
    ),
]


def is_allowlisted(relative: str) -> bool:
    normalised = relative.replace("\\", "/")
    if normalised in ALLOWLIST:
        return True
    return any(part in normalised for part in ALLOWLISTED_DIRECTORIES)


def iter_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        if any(part in SKIP_DIRECTORIES for part in path.parts):
            continue
        if path.name in SKIP_FILENAMES:
            continue
        yield path


def scan() -> list[tuple[str, int, str, str]]:
    findings: list[tuple[str, int, str, str]] = []
    for path in iter_files():
        relative = str(path.relative_to(ROOT)).replace("\\", "/")
        if is_allowlisted(relative):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue

        for number, line in enumerate(lines, start=1):
            stripped = line.strip()
            # Comments explain policy; they are not executable configuration.
            if stripped.startswith(("#", "//", "*", "/*")):
                continue
            for rule in RULES:
                if rule.pattern.search(line):
                    findings.append((relative, number, rule.name, stripped[:110]))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    findings = scan()
    scanned = sum(1 for _ in iter_files())

    if args.verbose:
        print(f"Scanned {scanned} files across {len(RULES)} rules.")
        print(f"Allowlisted paths: {len(ALLOWLIST)}")

    if not findings:
        print(f"PASS — no hardcoded configuration or secrets found ({scanned} files scanned).")
        return 0

    print(f"FAIL — {len(findings)} issue(s) found:\n")
    by_rule: dict[str, list] = {}
    for relative, number, rule, snippet in findings:
        by_rule.setdefault(rule, []).append((relative, number, snippet))

    messages = {rule.name: rule.message for rule in RULES}
    for rule_name, items in sorted(by_rule.items()):
        print(f"[{rule_name}] {messages[rule_name]}")
        for relative, number, snippet in items:
            print(f"    {relative}:{number}: {snippet}")
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main())

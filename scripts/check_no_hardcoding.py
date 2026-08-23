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

# Narrow exemptions: a path is excused from NAMED RULES ONLY, never wholesale.
#
# This used to be a map of path -> reason that suppressed every rule for that
# file. That is a hole rather than a policy: an allowlisted file could have
# carried an AWS key, a private key or a Firebase import and the scan would
# still have reported PASS. Each entry now names the specific rules it needs,
# so every other rule still applies to it.
#
# The list is short because the underlying literals were removed rather than
# excused — application configuration now lives in .env.example, which the
# backend and Vite read as a lowest-precedence development fallback, and the
# demo password is generated per run instead of committed.
ALLOWLIST: dict[str, tuple[frozenset[str], str]] = {
    "scripts/check_no_hardcoding.py": (
        frozenset({"firebase"}),
        "this scanner necessarily contains the patterns it searches for",
    ),
    ".env.example": (
        frozenset({"localhost_url"}),
        "the development defaults themselves; production never reads this file "
        "and refuses to start on any value published here",
    ),
    "dashboard/.env.example": (
        frozenset({"localhost_url"}),
        "same, for the Vite build",
    ),
    # Exempted per FILE rather than by adding these rules to the whole tests/
    # directory: a genuine Firebase import or a real DSN in any other test is
    # still a violation worth failing on.
    "backend/tests/test_no_hardcoding.py": (
        frozenset({"firebase"}),
        "the test asserting Firebase is absent must name it to search for it",
    ),
    "backend/tests/test_config_paths.py": (
        frozenset({"postgres_dsn"}),
        "fabricated DSN used to assert non-SQLite URLs pass through unchanged",
    ),
}

# Directories excused from named rules only, for the same reason as above.
# Test fixtures legitimately hold throwaway passwords, loopback URLs and
# threshold literals; nothing legitimately holds a cloud key or a private key,
# so those rules keep applying inside tests and docs.
ALLOWLISTED_DIRECTORIES: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "tests/",
        frozenset({"password_literal", "localhost_url", "hardcoded_url", "clinical_threshold"}),
    ),
    (
        "test/",
        frozenset({"password_literal", "localhost_url", "hardcoded_url", "clinical_threshold"}),
    ),
    (
        "__tests__/",
        frozenset({"password_literal", "localhost_url", "hardcoded_url", "clinical_threshold"}),
    ),
    (
        "docs/",
        frozenset(
            {"password_literal", "localhost_url", "hardcoded_url", "postgres_dsn", "firebase"}
        ),
    ),
)


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


def exempt_rules(relative: str) -> frozenset[str]:
    """Rule names this path is excused from. Everything else still applies."""
    normalised = relative.replace("\\", "/")
    exempt: set[str] = set()
    if normalised in ALLOWLIST:
        exempt |= ALLOWLIST[normalised][0]
    for marker, rules in ALLOWLISTED_DIRECTORIES:
        if marker in normalised:
            exempt |= rules
    return frozenset(exempt)


def iter_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        # Environment files carry no scannable suffix but are exactly where a
        # real secret gets pasted by accident, so include them by name.
        is_env_file = path.name.startswith(".env")
        if path.suffix not in SCAN_SUFFIXES and not is_env_file:
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
        exempt = exempt_rules(relative)
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
                if rule.name in exempt:
                    continue
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

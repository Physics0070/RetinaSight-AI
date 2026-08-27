"""Typed, environment-driven application configuration.

Everything environment- or deployment-specific is read from the environment
(prefixed ``RS_``) — never hardcoded. Business/clinical rules that must be
editable at runtime live in the database (``system_configuration``) and are
served by :mod:`app.services.config_service`, not here.

Render injects an unprefixed ``PORT``; the process entrypoint prefers it over
``RS_PORT`` so the service binds correctly without any hardcoded port.
"""

from __future__ import annotations

import os
import re
from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root: app/core/config.py -> core -> app -> backend -> repo.
# Relative filesystem paths in configuration resolve against this rather than
# the process working directory, so the service behaves identically whether it
# is started from the repo root, from backend/, or by a process manager.
REPO_ROOT = Path(__file__).resolve().parents[3]

# A file-backed SQLite URL: scheme + three slashes + a path. The negative
# lookahead excludes the four-slash form, which is already absolute.
_SQLITE_FILE_URL = re.compile(r"^(sqlite(?:\+\w+)?:///)(?!/)(.*)$")


def _anchor(configured: str) -> Path:
    """Resolve a configured filesystem path against the repository root."""
    path = Path(configured).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


class Environment(str, Enum):
    development = "development"
    staging = "staging"
    production = "production"


#: Substrings marking a value as a documented placeholder rather than a real
#: setting. Production refuses to start on any of them.
PLACEHOLDER_MARKERS = ("change-me", "changeme", "dev-only", "placeholder", "your-")

#: Settings that have no safe default and must be supplied per deployment.
REQUIRED_IN_PRODUCTION = (
    "database_url",
    "jwt_secret",
    "jwt_refresh_secret",
    "storage_signing_secret",
    "public_base_url",
    "cors_origins",
)


@lru_cache(maxsize=1)
def example_values() -> dict[str, str]:
    """The values published in ``.env.example``, keyed by variable name.

    Production rejects any required setting still equal to one of these.

    This is what makes the placeholder check order-independent. ``_env_files``
    decides whether to read the example file when the class is *defined*, which
    is correct when RS_ENV comes from the real environment but wrong if the
    variable is set later in-process. Comparing against the published values
    catches the leak regardless of how it happened, and it also catches
    placeholders that carry none of the PLACEHOLDER_MARKERS substrings — the
    localhost CORS origins, for instance, which look like ordinary settings.
    """
    path = REPO_ROOT / ".env.example"
    values: dict[str, str] = {}
    if not path.is_file():
        return values

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        # The file documents settings with trailing inline comments.
        value = value.split("#", 1)[0].strip()
        if value:
            values[key.strip().upper()] = value
    return values


def _env_files() -> tuple[Path, ...]:
    """Environment files, lowest precedence first.

    ``.env.example`` is read as the *lowest* precedence source outside
    production. That is what lets this module declare no environment values of
    its own: the development defaults that used to sit here as string literals
    (localhost URLs, dev secrets, the SQLite path) now live only in the example
    file, where they are documentation rather than code, and a fresh clone
    still runs with no setup step.

    It is deliberately NOT read in production. Silently falling back to a
    published placeholder secret is far worse than refusing to start, and
    :meth:`Settings.model_post_init` enforces that refusal.

    Paths are anchored to the repository root so the same files are found
    whether the process starts from the repo root or from backend/.
    """
    deployment = (REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env")
    if os.environ.get("RS_ENV", "").strip().lower() == Environment.production.value:
        return deployment
    return (REPO_ROOT / ".env.example", *deployment)


class StorageProvider(str, Enum):
    local = "local"
    s3 = "s3"


class ModelProvider(str, Enum):
    development = "development"
    onnx = "onnx"
    torch = "torch"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RS_",
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Every field below whose value is environment-specific declares an EMPTY
    # default. The real development values live in .env.example (see
    # _env_files); production must supply them explicitly. Fields that are
    # genuine protocol/format constants rather than deployment settings keep
    # their literal — an API prefix or a JWT algorithm is not a secret and does
    # not vary by environment.

    # ---- runtime ----
    env: Environment = Environment.development
    debug: bool = True
    log_level: str = "INFO"

    # ---- api server ----
    host: str = "0.0.0.0"
    port: int = 8000
    api_prefix: str = "/api/v1"
    cors_origins: str = ""

    # ---- database ----
    database_url: str = ""
    db_echo: bool = False

    # ---- auth / jwt ----
    jwt_secret: str = ""
    jwt_refresh_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    jwt_issuer: str = "retinasight-ai"

    # ---- security policy (configurable, not hardcoded in validators) ----
    password_min_length: int = 12
    login_rate_limit_per_minute: int = 10

    # ---- public base URL (used to build signed URLs for the local provider) ----
    public_base_url: str = ""

    # ---- object storage ----
    storage_provider: StorageProvider = StorageProvider.local
    storage_local_root: str = "./var/object-store"
    storage_signed_url_ttl_seconds: int = 300
    # Dedicated signing key for local signed URLs (kept separate from JWT keys
    # so rotating one never silently invalidates the other).
    storage_signing_secret: str = ""
    storage_max_image_bytes: int = 15_000_000
    storage_allowed_mime_types: str = "image/jpeg,image/png,image/webp"
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_use_path_style: bool = True

    # ---- ml / inference ----
    model_provider: ModelProvider = ModelProvider.development
    model_dir: str = "./ml/models"
    active_model_version: str = "dev-0.0.0"
    inference_mode: str = "sync"  # sync | worker

    # ---- seed (dev bootstrap only) ----
    # NOTE: RS_SEED_ADMIN_EMAIL must be a routable-looking address — reserved
    # TLDs (.local, .test, .example, .invalid) are rejected by email validation
    # and would create an administrator account that can never sign in.
    seed_admin_email: str = ""
    seed_admin_password: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def model_dir_path(self) -> Path:
        """Absolute directory holding model artefacts.

        A relative RS_MODEL_DIR resolves against the repository root, so the
        default (./ml/models) points at the same place the training pipeline
        writes to, regardless of where the process was started.
        """
        return _anchor(self.model_dir)

    @property
    def storage_local_root_path(self) -> Path:
        """Absolute root of the local object store.

        Anchored for the same reason as the model directory: a relative path
        resolved against the working directory would put images uploaded by a
        process started from backend/ somewhere a process started from the repo
        root cannot see them.
        """
        return _anchor(self.storage_local_root)

    @property
    def database_url_resolved(self) -> str:
        """Connection URL with any relative SQLite path made absolute.

        The path inside a SQLite URL resolves against the process working
        directory, so `uvicorn` started from backend/ and a script run from the
        repo root would quietly operate on two different databases — the model
        you registered would be missing from the one actually serving.

        Anchoring it to the repository root matches how RS_MODEL_DIR already
        behaves. Non-SQLite URLs (PostgreSQL in production) pass through
        untouched, as do absolute paths and :memory:.
        """
        # Render (like Heroku-style providers) issues `postgresql://...`, which
        # SQLAlchemy maps to psycopg2 -- not installed here. psycopg 3 is.
        if self.database_url.startswith(("postgres://", "postgresql://")):
            _, _, tail = self.database_url.partition("://")
            return f"postgresql+psycopg://{tail}"

        match = _SQLITE_FILE_URL.match(self.database_url)
        if match is None:
            return self.database_url

        scheme, tail = match.groups()
        if not tail or tail == ":memory:":
            return self.database_url

        path = Path(tail).expanduser()
        if path.is_absolute():
            return self.database_url
        return f"{scheme}{(REPO_ROOT / path).resolve().as_posix()}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def storage_allowed_mime_types_list(self) -> list[str]:
        return [m.strip().lower() for m in self.storage_allowed_mime_types.split(",") if m.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.env == Environment.production

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def model_post_init(self, _context: object) -> None:
        """Refuse to run production on defaults or documented placeholders.

        Reading .env.example outside production is what keeps environment
        values out of this source file, but it also means an unset variable
        degrades to a published placeholder instead of failing loudly. That is
        acceptable on a developer's machine and unacceptable in production —
        a service running on the JWT secret printed in a public example file
        is trivially forgeable. This is the check that makes the trade safe.
        """
        if not self.is_production:
            return

        published = example_values()
        problems: list[str] = []
        for name in REQUIRED_IN_PRODUCTION:
            value = str(getattr(self, name, "")).strip()
            variable = f"RS_{name.upper()}"
            if not value:
                problems.append(f"{variable} is not set.")
            elif value == published.get(variable):
                problems.append(
                    f"{variable} still holds the value published in .env.example."
                )
            elif any(marker in value.lower() for marker in PLACEHOLDER_MARKERS):
                problems.append(f"{variable} still holds a placeholder value.")

        # Reusing one secret for both token families means a stolen access
        # token can be replayed as a refresh token.
        if self.jwt_secret and self.jwt_secret == self.jwt_refresh_secret:
            problems.append("RS_JWT_SECRET and RS_JWT_REFRESH_SECRET must differ.")

        if problems:
            raise ValueError(
                "Refusing to start: insecure production configuration.\n  - "
                + "\n  - ".join(problems)
                + "\nSee .env.example for the full list of variables."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton (safe to import anywhere)."""
    return Settings()


settings = get_settings()

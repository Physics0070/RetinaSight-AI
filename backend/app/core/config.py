"""Typed, environment-driven application configuration.

Everything environment- or deployment-specific is read from the environment
(prefixed ``RS_``) — never hardcoded. Business/clinical rules that must be
editable at runtime live in the database (``system_configuration``) and are
served by :mod:`app.services.config_service`, not here.

Render injects an unprefixed ``PORT``; the process entrypoint prefers it over
``RS_PORT`` so the service binds correctly without any hardcoded port.
"""

from __future__ import annotations

import re
from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
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
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- runtime ----
    env: Environment = Environment.development
    debug: bool = True
    log_level: str = "INFO"

    # ---- api server ----
    host: str = "0.0.0.0"
    port: int = 8000
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---- database ----
    database_url: str = "sqlite+pysqlite:///./var/retinasight_dev.sqlite3"
    db_echo: bool = False

    # ---- auth / jwt ----
    jwt_secret: str = "dev-only-insecure-access-secret-change-me"
    jwt_refresh_secret: str = "dev-only-insecure-refresh-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    jwt_issuer: str = "retinasight-ai"

    # ---- security policy (configurable, not hardcoded in validators) ----
    password_min_length: int = 12
    login_rate_limit_per_minute: int = 10

    # ---- public base URL (used to build signed URLs for the local provider) ----
    public_base_url: str = "http://localhost:8000"

    # ---- object storage ----
    storage_provider: StorageProvider = StorageProvider.local
    storage_local_root: str = "./var/object-store"
    storage_signed_url_ttl_seconds: int = 300
    # Dedicated signing key for local signed URLs (kept separate from JWT keys
    # so rotating one never silently invalidates the other).
    storage_signing_secret: str = "dev-only-insecure-storage-signing-secret"
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
    # NOTE: must be a routable-looking address — reserved TLDs (.local, .test,
    # .example, .invalid) are rejected by email validation and would create an
    # administrator account that can never sign in.
    seed_admin_email: str = "admin@retinasight.ai"
    seed_admin_password: str = "ChangeMe_Admin123!"

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton (safe to import anywhere)."""
    return Settings()


settings = get_settings()

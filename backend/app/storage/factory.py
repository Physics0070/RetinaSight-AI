"""Storage provider selection — driven entirely by configuration."""

from __future__ import annotations

from app.core.config import StorageProvider, settings
from app.core.logging import get_logger
from app.storage.base import ObjectStorageProvider

logger = get_logger(__name__)

_provider: ObjectStorageProvider | None = None


def get_storage_provider() -> ObjectStorageProvider:
    """Return the configured provider (memoised)."""
    global _provider
    if _provider is not None:
        return _provider

    if settings.storage_provider == StorageProvider.s3:
        from app.storage.s3 import S3CompatibleStorage

        _provider = S3CompatibleStorage()
        logger.info("Object storage: S3-compatible bucket=%s", settings.s3_bucket)
    else:
        from app.storage.local import LocalFileSystemStorage

        if settings.is_production:
            # A container filesystem is ephemeral — images would be lost on
            # every deploy. Refuse to start rather than silently lose patient data.
            raise RuntimeError(
                "Local filesystem storage must not be used in production. "
                "Set RS_STORAGE_PROVIDER=s3 and configure the bucket."
            )
        _provider = LocalFileSystemStorage()
        logger.info("Object storage: local filesystem (development)")

    return _provider


def reset_storage_provider() -> None:
    """Clear the memoised provider (used by tests)."""
    global _provider
    _provider = None

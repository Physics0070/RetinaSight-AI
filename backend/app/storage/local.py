"""Local filesystem storage provider (development).

Objects live outside any statically-served directory and are reachable only
through the signed ``/images/blob`` endpoint, which verifies an HMAC signature
and expiry — mirroring the S3 presigned-URL model so application code behaves
identically in both environments.

NOTE: a container filesystem is ephemeral. This provider is for local
development only; production uses the S3-compatible provider.
"""

from __future__ import annotations

import hmac
import os
import time
import uuid
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlencode

from app.core.config import settings
from app.core.logging import get_logger
from app.storage.base import (
    ObjectNotFoundError,
    ObjectStorageProvider,
    StorageError,
    StoredObject,
    compute_checksum,
    validate_key,
)

logger = get_logger(__name__)


def sign_key(key: str, expires_at: int, *, secret: str | None = None) -> str:
    payload = f"{key}:{expires_at}".encode()
    return hmac.new(
        (secret or settings.storage_signing_secret).encode(), payload, sha256
    ).hexdigest()


def verify_signature(key: str, expires_at: int, signature: str) -> bool:
    """Constant-time signature check plus expiry enforcement."""
    if expires_at < int(time.time()):
        return False
    return hmac.compare_digest(sign_key(key, expires_at), signature or "")


class LocalFileSystemStorage(ObjectStorageProvider):
    def __init__(self, root: str | None = None) -> None:
        # An explicit root (tests) is taken as given; the configured default is
        # anchored to the repository root so the store does not move when the
        # process is started from a different directory.
        self.root = (
            Path(root).expanduser().resolve()
            if root is not None
            else settings.storage_local_root_path
        )
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        validate_key(key)
        path = (self.root / key).resolve()
        # Defence in depth: the resolved path must stay inside the root.
        if not path.is_relative_to(self.root):
            raise StorageError("Invalid storage key.", code="invalid_storage_key")
        return path

    def upload(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file then atomically replace, so a crash mid-write
        # never leaves a truncated image behind.
        tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, path)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            logger.exception("Local storage write failed for key=%s", key)
            raise StorageError() from exc

        return StoredObject(
            key=key,
            size=len(data),
            checksum=compute_checksum(data),
            content_type=content_type,
        )

    def download(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise ObjectNotFoundError()
        try:
            return path.read_bytes()
        except OSError as exc:
            logger.exception("Local storage read failed for key=%s", key)
            raise StorageError() from exc

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def generate_signed_url(
        self, key: str, *, ttl_seconds: int | None = None, download_name: str | None = None
    ) -> str:
        validate_key(key)
        ttl = ttl_seconds or settings.storage_signed_url_ttl_seconds
        expires_at = int(time.time()) + ttl
        params = {"key": key, "expires": expires_at, "signature": sign_key(key, expires_at)}
        if download_name:
            params["filename"] = download_name
        base = settings.public_base_url.rstrip("/")
        return f"{base}{settings.api_prefix}/images/blob?{urlencode(params)}"

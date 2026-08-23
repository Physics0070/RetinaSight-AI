"""Object-storage contract.

Retinal images are patient data: every backing store MUST be private, and read
access is granted only through short-lived signed URLs. No implementation may
expose a permanently public object URL.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.errors import AppError
from app.domain.enums import EyeSide


class StorageError(AppError):
    status_code = 503
    code = "storage_unavailable"
    message = "Image storage is temporarily unavailable. Please try again."


class ObjectNotFoundError(StorageError):
    status_code = 404
    code = "object_not_found"
    message = "The requested image could not be found."


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    checksum: str
    content_type: str


# Keys are system-generated; this guards against traversal and odd characters
# if a key ever arrives from an untrusted source.
_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.\-]{0,510}$")


def validate_key(key: str) -> str:
    if not _SAFE_KEY.match(key or "") or ".." in key or key.startswith("/"):
        raise StorageError("Invalid storage key.", code="invalid_storage_key")
    return key


def compute_checksum(data: bytes) -> str:
    """SHA-256 content hash — used for integrity and idempotent re-upload."""
    return hashlib.sha256(data).hexdigest()


def build_retinal_image_key(
    *,
    patient_id: uuid.UUID,
    session_id: uuid.UUID,
    eye_side: EyeSide | str,
    extension: str,
) -> str:
    """Opaque, non-enumerable key. Contains only UUIDs — never patient names."""
    suffix = extension.lstrip(".").lower() or "jpg"
    return posixpath.join(
        "retinal-images",
        str(patient_id),
        str(session_id),
        str(eye_side),
        f"{uuid.uuid4().hex}.{suffix}",
    )


def build_derived_key(source_key: str, *, kind: str, extension: str = "png") -> str:
    """Key for a derived artefact (e.g. Grad-CAM heatmap) beside its source."""
    validate_key(source_key)
    base = posixpath.dirname(source_key)
    stem = posixpath.splitext(posixpath.basename(source_key))[0]
    return posixpath.join(base, f"{stem}.{kind}.{extension.lstrip('.')}")


class ObjectStorageProvider(ABC):
    """Interface every storage backend implements."""

    @abstractmethod
    def upload(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject: ...

    @abstractmethod
    def download(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def generate_signed_url(
        self, key: str, *, ttl_seconds: int | None = None, download_name: str | None = None
    ) -> str:
        """A time-limited read URL. Must expire; must never be permanent."""

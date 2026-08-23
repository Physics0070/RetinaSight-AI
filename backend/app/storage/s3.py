"""S3-compatible object storage (production).

Works with any S3 API implementation — AWS S3, Cloudflare R2, MinIO, Backblaze
B2 — selected purely through environment variables. Objects are written
private; reads always go through a presigned, expiring URL.
"""

from __future__ import annotations

from functools import cached_property

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


class S3CompatibleStorage(ObjectStorageProvider):
    def __init__(self) -> None:
        if not settings.s3_bucket:
            raise StorageError(
                "Object storage is not configured.", code="storage_misconfigured"
            )
        self.bucket = settings.s3_bucket

    @cached_property
    def _client(self):  # noqa: ANN202
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise StorageError("Storage client unavailable.") from exc

        return boto3.client(
            "s3",
            region_name=settings.s3_region or None,
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key_id or None,
            aws_secret_access_key=settings.s3_secret_access_key or None,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if settings.s3_use_path_style else "auto"},
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    def upload(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        validate_key(key)
        try:
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                # Explicitly private — never public-read.
                ACL="private",
                Metadata={k: str(v) for k, v in (metadata or {}).items()},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("S3 upload failed for key=%s", key)
            raise StorageError() from exc

        return StoredObject(
            key=key,
            size=len(data),
            checksum=compute_checksum(data),
            content_type=content_type,
        )

    def download(self, key: str) -> bytes:
        validate_key(key)
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except Exception as exc:  # noqa: BLE001
            if _is_missing(exc):
                raise ObjectNotFoundError() from exc
            logger.exception("S3 download failed for key=%s", key)
            raise StorageError() from exc

    def delete(self, key: str) -> None:
        validate_key(key)
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:  # noqa: BLE001
            logger.exception("S3 delete failed for key=%s", key)
            raise StorageError() from exc

    def exists(self, key: str) -> bool:
        validate_key(key)
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:  # noqa: BLE001
            if _is_missing(exc):
                return False
            logger.exception("S3 head failed for key=%s", key)
            raise StorageError() from exc

    def generate_signed_url(
        self, key: str, *, ttl_seconds: int | None = None, download_name: str | None = None
    ) -> str:
        validate_key(key)
        params: dict[str, str] = {"Bucket": self.bucket, "Key": key}
        if download_name:
            params["ResponseContentDisposition"] = f'attachment; filename="{download_name}"'
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=ttl_seconds or settings.storage_signed_url_ttl_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("S3 presign failed for key=%s", key)
            raise StorageError() from exc


def _is_missing(exc: Exception) -> bool:
    code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
    return str(code) in {"404", "NoSuchKey", "NotFound"}

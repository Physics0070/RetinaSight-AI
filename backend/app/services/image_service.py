"""Retinal image intake.

Bytes go to private object storage; only metadata is persisted in the database.
Uploads are idempotent by content hash so an offline device retrying a sync can
never duplicate a clinical image record.
"""

from __future__ import annotations

import io
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.domain.enums import AuditAction, EyeSide
from app.models.identity import User
from app.models.screening import RetinalImage, ScreeningSession
from app.repositories.screening_repository import (
    RetinalImageRepository,
    ScreeningSessionRepository,
)
from app.services.audit_service import AuditService
from app.storage import get_storage_provider
from app.storage.base import build_retinal_image_key, compute_checksum

logger = get_logger(__name__)

# Pillow format name -> (mime type, file extension)
_FORMAT_MAP = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}


class ImageService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.images = RetinalImageRepository(db)
        self.sessions = ScreeningSessionRepository(db)
        self.audit = AuditService(db)
        self.storage = get_storage_provider()

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    def _inspect(self, data: bytes) -> tuple[str, str, int, int]:
        """Decode the bytes to confirm they really are an image.

        Returns ``(mime_type, extension, width, height)``. Trusting a
        client-supplied Content-Type would let arbitrary files be stored as
        "images", so the content itself is the authority.
        """
        if not data:
            raise ValidationError("The image file is empty.")
        if len(data) > settings.storage_max_image_bytes:
            limit_mb = settings.storage_max_image_bytes / 1_000_000
            raise ValidationError(f"Image exceeds the {limit_mb:.0f} MB limit.")

        try:
            from PIL import Image

            with Image.open(io.BytesIO(data)) as probe:
                probe.verify()  # structural check
            with Image.open(io.BytesIO(data)) as probe:
                image_format = (probe.format or "").upper()
                width, height = probe.size
        except Exception as exc:  # noqa: BLE001
            raise ValidationError("That file is not a readable image.") from exc

        if image_format not in _FORMAT_MAP:
            raise ValidationError("Unsupported image format. Use JPEG, PNG or WebP.")

        mime, extension = _FORMAT_MAP[image_format]
        if mime not in settings.storage_allowed_mime_types_list:
            raise ValidationError(f"Images of type {mime} are not accepted.")

        return mime, extension, width, height

    # ------------------------------------------------------------------ #
    # Store
    # ------------------------------------------------------------------ #
    def store_capture(
        self,
        *,
        session_id: uuid.UUID,
        eye_side: EyeSide,
        data: bytes,
        uploaded_by: User | None = None,
        local_id: str | None = None,
        captured_offline: bool = False,
    ) -> RetinalImage:
        session = self.sessions.get(session_id)
        if session is None:
            raise NotFoundError("Screening session not found.")

        # Idempotency 1: a device replaying the same local_id.
        if local_id:
            existing = self.images.get_by(local_id=local_id)
            if existing is not None:
                return existing

        mime, extension, width, height = self._inspect(data)
        checksum = compute_checksum(data)

        # Idempotency 2: identical bytes already stored for this session.
        duplicate = self.images.find_by_checksum(session_id, checksum)
        if duplicate is not None:
            logger.info(
                "Duplicate capture ignored session=%s checksum=%s", session_id, checksum[:12]
            )
            return duplicate

        key = build_retinal_image_key(
            patient_id=session.patient_id,
            session_id=session.id,
            eye_side=eye_side,
            extension=extension,
        )
        stored = self.storage.upload(
            key=key,
            data=data,
            content_type=mime,
            metadata={"session_id": str(session.id), "eye_side": str(eye_side)},
        )

        # A retake supersedes the previous capture of the same eye.
        capture_index = self.images.next_capture_index(session_id, str(eye_side))
        if capture_index:
            self.images.supersede_previous(session_id, str(eye_side))

        image = RetinalImage(
            local_id=local_id,
            session_id=session.id,
            patient_id=session.patient_id,
            eye_side=str(eye_side),
            capture_index=capture_index,
            storage_key=stored.key,
            mime_type=stored.content_type,
            file_size=stored.size,
            checksum=stored.checksum,
            width=width,
            height=height,
            is_active=True,
        )
        self.db.add(image)
        self.db.flush()

        self.audit.record(
            action=AuditAction.IMAGE_UPLOADED,
            actor=uploaded_by,
            resource_type="retinal_image",
            resource_id=image.id,
            context={
                "session_id": str(session.id),
                "eye_side": str(eye_side),
                "capture_index": capture_index,
                "captured_offline": captured_offline,
                # Deliberately no filename and no image content.
            },
        )
        self.db.commit()
        return image

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    def get(self, image_id: uuid.UUID) -> RetinalImage:
        image = self.images.get(image_id)
        if image is None:
            raise NotFoundError("Image not found.")
        return image

    def signed_url(self, image: RetinalImage, *, ttl_seconds: int | None = None) -> str:
        return self.storage.generate_signed_url(image.storage_key, ttl_seconds=ttl_seconds)

    def list_for_session(
        self, session_id: uuid.UUID, *, active_only: bool = False
    ) -> list[RetinalImage]:
        return list(self.images.for_session(session_id, active_only=active_only))

    def delete(self, image: RetinalImage) -> None:
        """Remove the stored object and its metadata row."""
        self.storage.delete(image.storage_key)
        self.db.delete(image)
        self.db.commit()

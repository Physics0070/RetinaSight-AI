"""Retinal image contracts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.domain.enums import EyeSide
from app.schemas.common import ORMModel


class RetinalImageRead(ORMModel):
    id: uuid.UUID
    session_id: uuid.UUID
    patient_id: uuid.UUID
    eye_side: str
    capture_index: int
    mime_type: str
    file_size: int
    checksum: str | None
    width: int | None
    height: int | None
    is_active: bool
    created_at: datetime
    # storage_key is deliberately NOT exposed — clients receive signed URLs only.


class RetinalImageWithUrl(RetinalImageRead):
    url: str
    url_expires_in: int


class ImageUploadRequest(BaseModel):
    """Multipart form fields accompanying the uploaded file."""

    session_id: uuid.UUID
    eye_side: EyeSide
    local_id: str | None = None
    captured_offline: bool = False

"""Retinal image upload and signed-URL access.

Images are never served from a public path. Clients receive a short-lived
signed URL; for the local development provider that URL points at ``/blob``,
which verifies an HMAC signature and expiry before returning bytes.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from app.api.deps import Access, DbSession, require_permission
from app.core.config import settings
from app.core.errors import PermissionDeniedError
from app.domain.enums import EyeSide, Permission
from app.schemas.image import RetinalImageRead, RetinalImageWithUrl
from app.services.image_service import ImageService
from app.storage import get_storage_provider
from app.storage.base import ObjectNotFoundError

router = APIRouter(prefix="/images", tags=["images"])

CanUpload = Annotated[Access, Depends(require_permission(Permission.IMAGE_UPLOAD))]
CanView = Annotated[Access, Depends(require_permission(Permission.IMAGE_VIEW))]


@router.post("", response_model=RetinalImageWithUrl, status_code=status.HTTP_201_CREATED)
async def upload_image(
    access: CanUpload,
    db: DbSession,
    file: Annotated[UploadFile, File(description="Retinal image (JPEG/PNG/WebP).")],
    session_id: Annotated[uuid.UUID, Form()],
    eye_side: Annotated[EyeSide, Form()],
    local_id: Annotated[str | None, Form()] = None,
    captured_offline: Annotated[bool, Form()] = False,
) -> RetinalImageWithUrl:
    """Upload one retinal capture. Re-uploading identical bytes is idempotent."""
    service = ImageService(db)
    data = await file.read()

    image = service.store_capture(
        session_id=session_id,
        eye_side=eye_side,
        data=data,
        uploaded_by=access.user,
        local_id=local_id,
        captured_offline=captured_offline,
    )
    # Confirm the caller may see this patient's imagery.
    access.authorize_patient(image.patient_id)

    return RetinalImageWithUrl(
        **RetinalImageRead.model_validate(image).model_dump(),
        url=service.signed_url(image),
        url_expires_in=settings.storage_signed_url_ttl_seconds,
    )


@router.get("/session/{session_id}", response_model=list[RetinalImageWithUrl])
def list_session_images(
    session_id: uuid.UUID,
    access: CanView,
    db: DbSession,
    active_only: bool = Query(default=False),
) -> list[RetinalImageWithUrl]:
    service = ImageService(db)
    images = service.list_for_session(session_id, active_only=active_only)
    if images:
        access.authorize_patient(images[0].patient_id)

    return [
        RetinalImageWithUrl(
            **RetinalImageRead.model_validate(image).model_dump(),
            url=service.signed_url(image),
            url_expires_in=settings.storage_signed_url_ttl_seconds,
        )
        for image in images
    ]


# NOTE: declared before "/{image_id}" so the literal path is not swallowed by
# the UUID path parameter — FastAPI matches routes in declaration order.
@router.get("/blob", include_in_schema=False)
def get_blob(
    key: str = Query(...),
    expires: int = Query(...),
    signature: str = Query(...),
    filename: str | None = Query(default=None),
) -> Response:
    """Serve a locally-stored object against a valid, unexpired signature.

    The signature *is* the authorization here (the S3 presigned-URL model), so
    no bearer token is required — but an invalid or expired signature is
    refused, and the URL is short-lived by configuration.
    """
    from app.storage.local import LocalFileSystemStorage, verify_signature

    provider = get_storage_provider()
    if not isinstance(provider, LocalFileSystemStorage):
        raise ObjectNotFoundError()

    if not verify_signature(key, expires, signature):
        raise PermissionDeniedError(
            "This image link has expired.", code="signed_url_invalid"
        )

    data = provider.download(key)
    headers = {"Cache-Control": "private, no-store"}
    if filename:
        headers["Content-Disposition"] = f'inline; filename="{filename}"'
    return Response(content=data, media_type="application/octet-stream", headers=headers)


@router.get("/{image_id}", response_model=RetinalImageWithUrl)
def get_image(image_id: uuid.UUID, access: CanView, db: DbSession) -> RetinalImageWithUrl:
    service = ImageService(db)
    image = service.get(image_id)
    access.authorize_patient(image.patient_id)

    return RetinalImageWithUrl(
        **RetinalImageRead.model_validate(image).model_dump(),
        url=service.signed_url(image),
        url_expires_in=settings.storage_signed_url_ttl_seconds,
    )

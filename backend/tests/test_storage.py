"""Object storage: provider contract, signed-URL security, image intake."""

from __future__ import annotations

import io
import time
import uuid

import pytest
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.domain.enums import EyeSide, RoleName
from app.models.patient import Patient
from app.models.screening import ScreeningSession
from app.services.image_service import ImageService
from app.storage.base import (
    StorageError,
    build_derived_key,
    build_retinal_image_key,
    compute_checksum,
    validate_key,
)
from app.storage.local import LocalFileSystemStorage, sign_key, verify_signature


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def make_image_bytes(size: tuple[int, int] = (64, 64), fmt: str = "JPEG") -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, color=(120, 40, 40)).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture
def storage(tmp_path) -> LocalFileSystemStorage:
    return LocalFileSystemStorage(root=str(tmp_path / "object-store"))


@pytest.fixture
def screening(db_session: Session) -> ScreeningSession:
    patient = Patient(patient_code=f"PT-{uuid.uuid4().hex[:8]}", full_name="Test Patient")
    db_session.add(patient)
    db_session.flush()
    session = ScreeningSession(patient_id=patient.id)
    db_session.add(session)
    db_session.commit()
    return session


# --------------------------------------------------------------------------- #
# Provider contract
# --------------------------------------------------------------------------- #
def test_upload_download_exists_delete_roundtrip(storage: LocalFileSystemStorage) -> None:
    data = make_image_bytes()
    key = "retinal-images/a/b/left/test.jpg"

    stored = storage.upload(key=key, data=data, content_type="image/jpeg")

    assert stored.size == len(data)
    assert stored.checksum == compute_checksum(data)
    assert storage.exists(key)
    assert storage.download(key) == data

    storage.delete(key)
    assert not storage.exists(key)


def test_download_missing_object_raises_not_found(storage: LocalFileSystemStorage) -> None:
    from app.storage.base import ObjectNotFoundError

    with pytest.raises(ObjectNotFoundError):
        storage.download("retinal-images/does/not/exist.jpg")


def test_delete_is_idempotent(storage: LocalFileSystemStorage) -> None:
    storage.delete("retinal-images/never/existed.jpg")  # must not raise


@pytest.mark.parametrize(
    "bad_key",
    [
        "../../../etc/passwd",
        "retinal-images/../../secrets.env",
        "/absolute/path.jpg",
        "",
        "with space.jpg",
    ],
)
def test_path_traversal_and_malformed_keys_are_rejected(
    storage: LocalFileSystemStorage, bad_key: str
) -> None:
    with pytest.raises(StorageError):
        storage.upload(key=bad_key, data=b"x", content_type="image/jpeg")


def test_keys_contain_no_patient_identifying_text() -> None:
    key = build_retinal_image_key(
        patient_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        eye_side=EyeSide.LEFT,
        extension="jpg",
    )
    assert validate_key(key) == key
    assert key.startswith("retinal-images/")
    assert key.endswith(".jpg")


def test_derived_key_sits_beside_its_source() -> None:
    source = "retinal-images/p/s/left/abc123.jpg"
    derived = build_derived_key(source, kind="gradcam", extension="png")

    assert derived == "retinal-images/p/s/left/abc123.gradcam.png"


# --------------------------------------------------------------------------- #
# Signed URLs
# --------------------------------------------------------------------------- #
def test_signed_url_is_time_limited_and_verifies(storage: LocalFileSystemStorage) -> None:
    key = "retinal-images/a/b/left/x.jpg"
    url = storage.generate_signed_url(key, ttl_seconds=60)

    assert "signature=" in url and "expires=" in url
    expires = int(time.time()) + 60
    assert verify_signature(key, expires, sign_key(key, expires))


def test_expired_signature_is_rejected() -> None:
    key = "retinal-images/a/b/left/x.jpg"
    expired = int(time.time()) - 1

    assert verify_signature(key, expired, sign_key(key, expired)) is False


def test_tampered_signature_is_rejected() -> None:
    key = "retinal-images/a/b/left/x.jpg"
    expires = int(time.time()) + 300

    assert verify_signature(key, expires, "deadbeef") is False
    # A signature minted for a different object must not unlock this one.
    assert verify_signature(key, expires, sign_key("other/key.jpg", expires)) is False


def test_signature_for_extended_expiry_is_rejected() -> None:
    """A client cannot widen its own access window."""
    key = "retinal-images/a/b/left/x.jpg"
    expires = int(time.time()) + 300
    signature = sign_key(key, expires)

    assert verify_signature(key, expires + 86_400, signature) is False


# --------------------------------------------------------------------------- #
# Image intake
# --------------------------------------------------------------------------- #
def test_store_capture_persists_metadata_not_bytes(
    db_session: Session, screening: ScreeningSession, make_user, monkeypatch, tmp_path
) -> None:
    _use_temp_storage(monkeypatch, tmp_path)
    worker = make_user("intake@example.com", RoleName.HEALTH_WORKER)
    data = make_image_bytes((128, 96))

    image = ImageService(db_session).store_capture(
        session_id=screening.id, eye_side=EyeSide.LEFT, data=data, uploaded_by=worker
    )

    assert image.checksum == compute_checksum(data)
    assert (image.width, image.height) == (128, 96)
    assert image.mime_type == "image/jpeg"
    assert image.file_size == len(data)
    assert image.is_active is True
    assert image.capture_index == 0


def test_identical_bytes_are_stored_once(
    db_session: Session, screening: ScreeningSession, monkeypatch, tmp_path
) -> None:
    """Offline sync retries must not duplicate a clinical image record."""
    _use_temp_storage(monkeypatch, tmp_path)
    service = ImageService(db_session)
    data = make_image_bytes()

    first = service.store_capture(session_id=screening.id, eye_side=EyeSide.LEFT, data=data)
    second = service.store_capture(session_id=screening.id, eye_side=EyeSide.LEFT, data=data)

    assert first.id == second.id
    assert len(service.list_for_session(screening.id)) == 1


def test_replayed_local_id_returns_the_same_record(
    db_session: Session, screening: ScreeningSession, monkeypatch, tmp_path
) -> None:
    _use_temp_storage(monkeypatch, tmp_path)
    service = ImageService(db_session)

    first = service.store_capture(
        session_id=screening.id,
        eye_side=EyeSide.LEFT,
        data=make_image_bytes((64, 64)),
        local_id="device-capture-001",
    )
    # Same local id, different bytes (e.g. recompressed on the device).
    second = service.store_capture(
        session_id=screening.id,
        eye_side=EyeSide.LEFT,
        data=make_image_bytes((80, 80)),
        local_id="device-capture-001",
    )

    assert first.id == second.id


def test_retake_supersedes_the_previous_capture(
    db_session: Session, screening: ScreeningSession, monkeypatch, tmp_path
) -> None:
    _use_temp_storage(monkeypatch, tmp_path)
    service = ImageService(db_session)

    first = service.store_capture(
        session_id=screening.id, eye_side=EyeSide.LEFT, data=make_image_bytes((64, 64))
    )
    retake = service.store_capture(
        session_id=screening.id, eye_side=EyeSide.LEFT, data=make_image_bytes((72, 72))
    )

    db_session.refresh(first)
    assert first.is_active is False
    assert retake.is_active is True
    assert retake.capture_index == 1
    assert service.images.active_for_eye(screening.id, "left").id == retake.id


def test_each_eye_is_tracked_independently(
    db_session: Session, screening: ScreeningSession, monkeypatch, tmp_path
) -> None:
    _use_temp_storage(monkeypatch, tmp_path)
    service = ImageService(db_session)

    left = service.store_capture(
        session_id=screening.id, eye_side=EyeSide.LEFT, data=make_image_bytes((64, 64))
    )
    right = service.store_capture(
        session_id=screening.id, eye_side=EyeSide.RIGHT, data=make_image_bytes((66, 66))
    )

    assert left.is_active and right.is_active
    assert left.capture_index == right.capture_index == 0


def test_non_image_content_is_rejected(
    db_session: Session, screening: ScreeningSession, monkeypatch, tmp_path
) -> None:
    """A client-supplied content type must never be trusted."""
    _use_temp_storage(monkeypatch, tmp_path)

    with pytest.raises(ValidationError):
        ImageService(db_session).store_capture(
            session_id=screening.id,
            eye_side=EyeSide.LEFT,
            data=b"#!/bin/sh\nrm -rf /\n",
        )


def test_empty_upload_is_rejected(
    db_session: Session, screening: ScreeningSession, monkeypatch, tmp_path
) -> None:
    _use_temp_storage(monkeypatch, tmp_path)

    with pytest.raises(ValidationError):
        ImageService(db_session).store_capture(
            session_id=screening.id, eye_side=EyeSide.LEFT, data=b""
        )


def test_oversized_image_is_rejected(
    db_session: Session, screening: ScreeningSession, monkeypatch, tmp_path
) -> None:
    _use_temp_storage(monkeypatch, tmp_path)
    monkeypatch.setattr("app.services.image_service.settings.storage_max_image_bytes", 128)

    with pytest.raises(ValidationError):
        ImageService(db_session).store_capture(
            session_id=screening.id, eye_side=EyeSide.LEFT, data=make_image_bytes((256, 256))
        )


def test_upload_to_unknown_session_is_rejected(
    db_session: Session, monkeypatch, tmp_path
) -> None:
    from app.core.errors import NotFoundError

    _use_temp_storage(monkeypatch, tmp_path)

    with pytest.raises(NotFoundError):
        ImageService(db_session).store_capture(
            session_id=uuid.uuid4(), eye_side=EyeSide.LEFT, data=make_image_bytes()
        )


def test_storage_key_is_never_exposed_in_the_api_schema() -> None:
    from app.schemas.image import RetinalImageRead

    assert "storage_key" not in RetinalImageRead.model_fields


# --------------------------------------------------------------------------- #
def _use_temp_storage(monkeypatch, tmp_path) -> None:
    """Point the memoised provider at an isolated temp directory."""
    from app.storage import factory

    provider = LocalFileSystemStorage(root=str(tmp_path / "object-store"))
    monkeypatch.setattr(factory, "_provider", provider)
    monkeypatch.setattr(
        "app.services.image_service.get_storage_provider", lambda: provider
    )

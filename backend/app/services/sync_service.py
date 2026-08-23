"""Offline synchronisation.

A device queues work locally while offline and pushes it when connectivity
returns. Every item carries a client-generated ``local_id``; the pair
(``local_id``, ``entity_type``) is unique, so replaying a batch after a dropped
connection updates the existing record instead of creating a duplicate clinical
entry.

Items are processed independently: one bad record never blocks the rest of a
batch, and a failed item is returned with a reason so the device can retry it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ValidationError
from app.core.logging import get_logger
from app.domain.enums import (
    AuditAction,
    ConsentType,
    EyeSide,
    SyncEntityType,
    SyncOperation,
    SyncStatus,
)
from app.models.identity import User
from app.models.system import SyncQueueItem
from app.repositories.base import BaseRepository
from app.services.audit_service import AuditService
from app.services.patient_service import PatientService
from app.services.screening_service import ScreeningService

logger = get_logger(__name__)


class SyncQueueRepository(BaseRepository[SyncQueueItem]):
    model = SyncQueueItem

    def find(self, local_id: str, entity_type: str) -> SyncQueueItem | None:
        return self.db.execute(
            select(SyncQueueItem).where(
                SyncQueueItem.local_id == local_id,
                SyncQueueItem.entity_type == entity_type,
            )
        ).scalars().first()


@dataclass
class SyncItemResult:
    local_id: str
    entity_type: str
    status: str
    server_id: uuid.UUID | None = None
    error: str | None = None


@dataclass
class SyncBatchResult:
    accepted: int = 0
    duplicates: int = 0
    failed: int = 0
    items: list[SyncItemResult] = field(default_factory=list)


class SyncService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = SyncQueueRepository(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------------ #
    def push_batch(
        self,
        items: list[dict[str, Any]],
        *,
        actor: User | None = None,
        device_id: str | None = None,
    ) -> SyncBatchResult:
        result = SyncBatchResult()
        for payload in items:
            try:
                item_result = self._process_item(payload, actor=actor, device_id=device_id)
            except AppError as exc:
                item_result = SyncItemResult(
                    local_id=str(payload.get("local_id", "")),
                    entity_type=str(payload.get("entity_type", "")),
                    status=SyncStatus.FAILED.value,
                    error=exc.message,
                )
            except Exception:  # noqa: BLE001
                logger.exception("Sync item failed unexpectedly")
                item_result = SyncItemResult(
                    local_id=str(payload.get("local_id", "")),
                    entity_type=str(payload.get("entity_type", "")),
                    status=SyncStatus.FAILED.value,
                    error="This item could not be synchronised.",
                )

            result.items.append(item_result)
            if item_result.status == SyncStatus.SYNCED.value:
                result.accepted += 1
            elif item_result.status == "duplicate":
                result.duplicates += 1
            else:
                result.failed += 1

        self.audit.record(
            action=AuditAction.SYNC_PROCESSED,
            actor=actor,
            resource_type="sync_queue",
            context={
                "accepted": result.accepted,
                "duplicates": result.duplicates,
                "failed": result.failed,
                "device_id": device_id or "",
            },
        )
        self.db.commit()
        return result

    # ------------------------------------------------------------------ #
    def _process_item(
        self, payload: dict[str, Any], *, actor: User | None, device_id: str | None
    ) -> SyncItemResult:
        local_id = str(payload.get("local_id") or "").strip()
        entity_type = str(payload.get("entity_type") or "").strip()
        operation = str(payload.get("operation") or SyncOperation.CREATE.value)
        data = payload.get("payload") or {}

        if not local_id:
            raise ValidationError("Each sync item needs a local_id.")
        try:
            entity = SyncEntityType(entity_type)
        except ValueError as exc:
            raise ValidationError(f"Unknown entity type '{entity_type}'.") from exc

        record = self.repo.find(local_id, entity_type)
        if record is not None and record.status == SyncStatus.SYNCED.value:
            # Idempotent replay — acknowledge without re-applying.
            return SyncItemResult(
                local_id=local_id,
                entity_type=entity_type,
                status="duplicate",
                server_id=record.server_id,
            )

        if record is None:
            record = SyncQueueItem(
                local_id=local_id,
                entity_type=entity_type,
                operation=operation,
                payload=data,
                status=SyncStatus.UPLOADING.value,
                device_id=device_id,
                submitted_by_user_id=actor.id if actor else None,
            )
            self.db.add(record)
        else:
            record.status = SyncStatus.RETRYING.value
            record.payload = data

        record.attempt_count += 1
        record.last_attempt_at = datetime.now(tz=timezone.utc)
        self.db.flush()

        try:
            server_id = self._apply(entity, data, local_id=local_id, actor=actor)
        except AppError as exc:
            record.status = SyncStatus.FAILED.value
            record.last_error = exc.message[:512]
            self.db.flush()
            raise

        record.status = SyncStatus.SYNCED.value
        record.server_id = server_id
        record.last_error = None
        self.db.flush()

        return SyncItemResult(
            local_id=local_id,
            entity_type=entity_type,
            status=SyncStatus.SYNCED.value,
            server_id=server_id,
        )

    # ------------------------------------------------------------------ #
    def _apply(
        self,
        entity: SyncEntityType,
        data: dict[str, Any],
        *,
        local_id: str,
        actor: User | None,
    ) -> uuid.UUID:
        """Apply one queued change through the normal service layer.

        Sync deliberately reuses the same services as online requests, so
        validation, consent checks and auditing are identical either way.
        """
        if entity == SyncEntityType.PATIENT:
            service = PatientService(self.db)
            existing = service.repo.get_by(patient_code=data.get("patient_code", ""))
            if existing is not None:
                return existing.id
            patient = service.register(
                full_name=data["full_name"],
                patient_code=data.get("patient_code"),
                date_of_birth=_parse_date(data.get("date_of_birth")),
                sex=data.get("sex"),
                phone=data.get("phone"),
                has_diabetes=data.get("has_diabetes"),
                diabetes_duration_years=data.get("diabetes_duration_years"),
                clinic_id=_parse_uuid(data.get("clinic_id")),
                actor=actor,
                consents=data.get("consents")
                or {ConsentType.SCREENING.value: True},
            )
            return patient.id

        if entity == SyncEntityType.SCREENING_SESSION:
            session = ScreeningService(self.db).start_screening(
                patient_id=_require_uuid(data.get("patient_id"), "patient_id"),
                actor=actor,
                clinic_id=_parse_uuid(data.get("clinic_id")),
                local_id=local_id,
                captured_offline=True,
            )
            return session.id

        if entity == SyncEntityType.RETINAL_IMAGE:
            import base64

            content = data.get("content_base64")
            if not content:
                raise ValidationError("Image sync items must include content_base64.")
            session_id = _require_uuid(data.get("session_id"), "session_id")
            try:
                raw = base64.b64decode(content, validate=True)
            except Exception as exc:  # noqa: BLE001
                raise ValidationError("The uploaded image data is not valid.") from exc

            outcome = ScreeningService(self.db).capture_eye(
                session_id=session_id,
                eye_side=EyeSide(str(data.get("eye_side", EyeSide.LEFT.value))),
                data=raw,
                actor=actor,
                local_id=local_id,
                captured_offline=True,
            )
            return outcome.image.id

        raise ValidationError(
            f"Synchronising '{entity.value}' is not supported by this endpoint."
        )

    # ------------------------------------------------------------------ #
    def queue_status(self, *, device_id: str | None = None) -> dict[str, int]:
        from sqlalchemy import func

        stmt = select(SyncQueueItem.status, func.count()).group_by(SyncQueueItem.status)
        if device_id:
            stmt = stmt.where(SyncQueueItem.device_id == device_id)
        counts = {status: 0 for status in (s.value for s in SyncStatus)}
        for status, total in self.db.execute(stmt).all():
            counts[str(status)] = int(total)
        return counts

    def list_items(
        self, *, status: str | None = None, device_id: str | None = None, limit: int = 100
    ) -> list[SyncQueueItem]:
        stmt = select(SyncQueueItem).order_by(SyncQueueItem.created_at.desc())
        if status:
            stmt = stmt.where(SyncQueueItem.status == status)
        if device_id:
            stmt = stmt.where(SyncQueueItem.device_id == device_id)
        return list(self.db.execute(stmt.limit(limit)).scalars().all())


def _parse_uuid(value: Any) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _require_uuid(value: Any, field_name: str) -> uuid.UUID:
    parsed = _parse_uuid(value)
    if parsed is None:
        raise ValidationError(f"'{field_name}' must be a valid identifier.")
    return parsed


def _parse_date(value: Any):  # noqa: ANN201
    if not value:
        return None
    from datetime import date

    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None

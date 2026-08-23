"""Offline synchronisation endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import Access, DbSession, require_permission
from app.domain.enums import Permission, SyncEntityType, SyncOperation
from app.schemas.common import ORMModel
from app.services.sync_service import SyncService

router = APIRouter(prefix="/sync", tags=["sync"])

CanSync = Annotated[Access, Depends(require_permission(Permission.SYNC_WRITE))]


class SyncItemInput(BaseModel):
    local_id: str = Field(min_length=1, max_length=64)
    entity_type: SyncEntityType
    operation: SyncOperation = SyncOperation.CREATE
    payload: dict[str, Any] = Field(default_factory=dict)


class SyncPushRequest(BaseModel):
    device_id: str | None = Field(default=None, max_length=64)
    items: list[SyncItemInput] = Field(default_factory=list, max_length=200)


class SyncItemResultOut(BaseModel):
    local_id: str
    entity_type: str
    status: str
    server_id: uuid.UUID | None = None
    error: str | None = None


class SyncPushResponse(BaseModel):
    accepted: int
    duplicates: int
    failed: int
    items: list[SyncItemResultOut]


class SyncQueueItemRead(ORMModel):
    id: uuid.UUID
    local_id: str
    server_id: uuid.UUID | None
    entity_type: str
    operation: str
    status: str
    attempt_count: int
    last_attempt_at: datetime | None
    last_error: str | None
    device_id: str | None
    created_at: datetime


@router.post("/push", response_model=SyncPushResponse)
def push(payload: SyncPushRequest, access: CanSync, db: DbSession) -> SyncPushResponse:
    """Upload a batch of queued offline changes.

    Idempotent: re-pushing an already-applied item is acknowledged as a
    duplicate rather than creating a second clinical record.
    """
    result = SyncService(db).push_batch(
        [item.model_dump() for item in payload.items],
        actor=access.user,
        device_id=payload.device_id,
    )
    return SyncPushResponse(
        accepted=result.accepted,
        duplicates=result.duplicates,
        failed=result.failed,
        items=[SyncItemResultOut(**item.__dict__) for item in result.items],
    )


@router.get("/status")
def queue_status(
    access: CanSync, db: DbSession, device_id: str | None = Query(default=None)
) -> dict:
    return {"counts": SyncService(db).queue_status(device_id=device_id)}


@router.get("/queue", response_model=list[SyncQueueItemRead])
def list_queue(
    access: CanSync,
    db: DbSession,
    status: str | None = Query(default=None),
    device_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[SyncQueueItemRead]:
    items = SyncService(db).list_items(status=status, device_id=device_id, limit=limit)
    return [SyncQueueItemRead.model_validate(i) for i in items]

"""Audit-log persistence and querying."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, select

from app.models.system import AuditLog
from app.repositories.base import BaseRepository


class AuditRepository(BaseRepository[AuditLog]):
    model = AuditLog

    def search_statement(
        self,
        *,
        actor_user_id=None,
        action: str | None = None,
        resource_type: str | None = None,
        result: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Select:
        stmt = select(AuditLog)
        if actor_user_id is not None:
            stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if resource_type:
            stmt = stmt.where(AuditLog.resource_type == resource_type)
        if result:
            stmt = stmt.where(AuditLog.result == result)
        if date_from:
            stmt = stmt.where(AuditLog.created_at >= date_from)
        if date_to:
            stmt = stmt.where(AuditLog.created_at <= date_to)
        return stmt.order_by(AuditLog.created_at.desc())

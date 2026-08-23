"""Audit logging.

Records *what happened*, never the sensitive payload. Raw patient data,
credentials, tokens and image bytes must never reach this service.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.enums import AuditAction, AuditResult
from app.models.identity import User
from app.models.system import AuditLog
from app.repositories.audit_repository import AuditRepository

logger = get_logger(__name__)

# Keys that must never be persisted in audit context.
_FORBIDDEN_CONTEXT_KEYS = {
    "password",
    "new_password",
    "current_password",
    "password_hash",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "image_bytes",
    "payload",
}


def _sanitize(context: dict[str, Any] | None) -> dict[str, Any]:
    if not context:
        return {}
    return {
        k: v
        for k, v in context.items()
        if k.lower() not in _FORBIDDEN_CONTEXT_KEYS and _is_jsonable(v)
    }


def _is_jsonable(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool, type(None), list, dict))


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AuditRepository(db)

    def record(
        self,
        *,
        action: AuditAction | str,
        result: AuditResult | str = AuditResult.SUCCESS,
        actor: User | None = None,
        actor_email: str | None = None,
        actor_role: str | None = None,
        resource_type: str | None = None,
        resource_id: str | uuid.UUID | None = None,
        ip_address: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor_user_id=actor.id if actor else None,
            actor_email=actor_email or (actor.email if actor else None),
            actor_role=actor_role,
            action=str(action),
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            result=str(result),
            ip_address=ip_address,
            context=_sanitize(context),
        )
        self.db.add(entry)
        self.db.flush()
        logger.info(
            "audit action=%s result=%s resource=%s/%s",
            entry.action,
            entry.result,
            entry.resource_type,
            entry.resource_id,
        )
        return entry

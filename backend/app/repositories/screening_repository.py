"""Persistence for screening sessions and retinal images."""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import func, select

from app.models.screening import RetinalImage, ScreeningSession
from app.repositories.base import BaseRepository


class ScreeningSessionRepository(BaseRepository[ScreeningSession]):
    model = ScreeningSession

    def get_by_local_id(self, local_id: str) -> ScreeningSession | None:
        return self.get_by(local_id=local_id)

    def for_patient(self, patient_id: uuid.UUID) -> Sequence[ScreeningSession]:
        stmt = (
            select(ScreeningSession)
            .where(ScreeningSession.patient_id == patient_id)
            .order_by(ScreeningSession.created_at.desc())
        )
        return self.db.execute(stmt).scalars().all()


class RetinalImageRepository(BaseRepository[RetinalImage]):
    model = RetinalImage

    def for_session(
        self, session_id: uuid.UUID, *, active_only: bool = False
    ) -> Sequence[RetinalImage]:
        stmt = select(RetinalImage).where(RetinalImage.session_id == session_id)
        if active_only:
            stmt = stmt.where(RetinalImage.is_active.is_(True))
        stmt = stmt.order_by(RetinalImage.eye_side, RetinalImage.capture_index)
        return self.db.execute(stmt).scalars().all()

    def find_by_checksum(
        self, session_id: uuid.UUID, checksum: str
    ) -> RetinalImage | None:
        """Used for idempotent re-upload: the same bytes are stored once."""
        stmt = select(RetinalImage).where(
            RetinalImage.session_id == session_id, RetinalImage.checksum == checksum
        )
        return self.db.execute(stmt).scalars().first()

    def next_capture_index(self, session_id: uuid.UUID, eye_side: str) -> int:
        stmt = select(func.count()).select_from(RetinalImage).where(
            RetinalImage.session_id == session_id, RetinalImage.eye_side == eye_side
        )
        return int(self.db.execute(stmt).scalar_one())

    def supersede_previous(self, session_id: uuid.UUID, eye_side: str) -> int:
        """Mark earlier captures of the same eye inactive (a retake wins)."""
        rows = self.db.execute(
            select(RetinalImage).where(
                RetinalImage.session_id == session_id,
                RetinalImage.eye_side == eye_side,
                RetinalImage.is_active.is_(True),
            )
        ).scalars().all()
        for row in rows:
            row.is_active = False
        self.db.flush()
        return len(rows)

    def active_for_eye(
        self, session_id: uuid.UUID, eye_side: str
    ) -> RetinalImage | None:
        stmt = (
            select(RetinalImage)
            .where(
                RetinalImage.session_id == session_id,
                RetinalImage.eye_side == eye_side,
                RetinalImage.is_active.is_(True),
            )
            .order_by(RetinalImage.capture_index.desc())
        )
        return self.db.execute(stmt).scalars().first()

"""Generic repository.

All database access goes through repositories — route handlers never build
queries or touch the session directly.
"""

from __future__ import annotations

import uuid
from typing import Any, Generic, Sequence, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- reads ----
    def get(self, entity_id: uuid.UUID) -> ModelT | None:
        return self.db.get(self.model, entity_id)

    def get_by(self, **filters: Any) -> ModelT | None:
        stmt = select(self.model).filter_by(**filters).limit(1)
        return self.db.execute(stmt).scalar_one_or_none()

    def list(self, *, limit: int | None = None, offset: int = 0, **filters: Any) -> Sequence[ModelT]:
        stmt = select(self.model).filter_by(**filters).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return self.db.execute(stmt).scalars().all()

    def count(self, **filters: Any) -> int:
        stmt = select(func.count()).select_from(self.model).filter_by(**filters)
        return int(self.db.execute(stmt).scalar_one())

    def paginate(self, stmt: Select, *, limit: int, offset: int) -> tuple[Sequence[ModelT], int]:
        """Run a prepared statement plus its matching total count."""
        total_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int(self.db.execute(total_stmt).scalar_one())
        rows = self.db.execute(stmt.limit(limit).offset(offset)).scalars().all()
        return rows, total

    # ---- writes (flush, never commit — the service owns the transaction) ----
    def add(self, entity: ModelT) -> ModelT:
        self.db.add(entity)
        self.db.flush()
        return entity

    def create(self, **values: Any) -> ModelT:
        return self.add(self.model(**values))

    def delete(self, entity: ModelT) -> None:
        self.db.delete(entity)
        self.db.flush()

"""Engine + session factory. Portable between SQLite (dev) and PostgreSQL (prod)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _ensure_sqlite_dir(database_url: str) -> None:
    """Create the parent directory for a file-based SQLite DB if needed."""
    prefix = "sqlite+pysqlite:///"
    if database_url.startswith(prefix):
        rel = database_url[len(prefix) :]
        if rel and rel != ":memory:":
            Path(rel).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def _build_engine() -> Engine:
    # The resolved URL, so a relative SQLite path points at the same file
    # whether the process was started from the repo root or from backend/.
    database_url = settings.database_url_resolved
    _ensure_sqlite_dir(database_url)
    connect_args: dict = {}
    if settings.is_sqlite:
        connect_args["check_same_thread"] = False
    engine = create_engine(
        database_url,
        echo=settings.db_echo,
        pool_pre_ping=True,
        future=True,
        connect_args=connect_args,
    )
    if settings.is_sqlite:

        @event.listens_for(engine, "connect")
        def _fk_pragma(dbapi_connection, _record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine: Engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def bind_port() -> int:
    """Render injects an unprefixed PORT; prefer it over RS_PORT."""
    return int(os.environ.get("PORT", settings.port))

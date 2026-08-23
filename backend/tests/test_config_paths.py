"""Configured filesystem paths must not depend on the working directory.

This bug has bitten this project twice. The first time, ``RS_MODEL_DIR=./ml/models``
resolved against the process working directory, so a service started from
``backend/`` looked for the artefact in ``backend/ml/models`` and reported
"MODEL NOT AVAILABLE" while the file sat in ``ml/models``.

The second time was quieter and worse: the SQLite URL had the same flaw, so
``alembic upgrade`` run from one directory and ``uvicorn`` started from another
operated on two different database files. A model registered in one was simply
absent from the other, with no error anywhere to suggest why.

Every configured path now anchors to the repository root. These tests pin that,
including the property that actually matters — that changing the working
directory changes nothing.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.config import REPO_ROOT, Settings


def settings_with(**overrides) -> Settings:
    """A Settings instance with defaults overridden, ignoring any local .env."""
    return Settings(_env_file=None, **overrides)


# --------------------------------------------------------------------------- #
# database URL
# --------------------------------------------------------------------------- #


def test_relative_sqlite_path_anchors_to_the_repository_root() -> None:
    resolved = settings_with(
        database_url="sqlite+pysqlite:///./var/retinasight_dev.sqlite3"
    ).database_url_resolved

    assert resolved.endswith("/var/retinasight_dev.sqlite3")
    assert (REPO_ROOT / "var").as_posix() in resolved


def test_the_resolved_database_does_not_move_with_the_working_directory(
    tmp_path, monkeypatch
) -> None:
    """The property the whole fix exists for."""
    settings = settings_with(database_url="sqlite+pysqlite:///./var/dev.sqlite3")

    from_here = settings.database_url_resolved
    monkeypatch.chdir(tmp_path)
    from_elsewhere = settings.database_url_resolved

    assert from_here == from_elsewhere


def test_absolute_sqlite_paths_are_left_alone() -> None:
    # Four-slash form: already absolute by construction.
    four_slash = "sqlite+pysqlite:////srv/data/retinasight.sqlite3"
    assert settings_with(database_url=four_slash).database_url_resolved == four_slash

    # Drive-letter form, as used on Windows.
    drive = "sqlite+pysqlite:///C:/data/retinasight.sqlite3"
    assert settings_with(database_url=drive).database_url_resolved == drive


def test_in_memory_database_is_left_alone() -> None:
    url = "sqlite+pysqlite:///:memory:"
    assert settings_with(database_url=url).database_url_resolved == url


def test_postgresql_urls_pass_through_untouched() -> None:
    """Production runs PostgreSQL; there is no filesystem path to anchor."""
    url = "postgresql+psycopg://user:pw@db.internal:5432/retinasight"
    assert settings_with(database_url=url).database_url_resolved == url


# --------------------------------------------------------------------------- #
# directories
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("field", "attribute", "relative"),
    [
        ("model_dir", "model_dir_path", "./ml/models"),
        ("storage_local_root", "storage_local_root_path", "./var/object-store"),
    ],
)
def test_relative_directories_anchor_to_the_repository_root(
    field, attribute, relative, tmp_path, monkeypatch
) -> None:
    settings = settings_with(**{field: relative})

    expected = (REPO_ROOT / relative.lstrip("./")).resolve()
    assert getattr(settings, attribute) == expected

    monkeypatch.chdir(tmp_path)
    assert getattr(settings, attribute) == expected


@pytest.mark.parametrize(
    ("field", "attribute"),
    [("model_dir", "model_dir_path"), ("storage_local_root", "storage_local_root_path")],
)
def test_absolute_directories_are_honoured_as_given(field, attribute, tmp_path) -> None:
    settings = settings_with(**{field: str(tmp_path)})

    assert getattr(settings, attribute) == Path(tmp_path).resolve()


def test_the_default_model_directory_is_where_training_writes() -> None:
    """The specific mismatch that produced a spurious MODEL NOT AVAILABLE."""
    assert settings_with().model_dir_path == (REPO_ROOT / "ml" / "models").resolve()


def test_environment_still_overrides_the_default(monkeypatch) -> None:
    """Anchoring must not break configurability — this is not a hardcoded path."""
    monkeypatch.setenv("RS_MODEL_DIR", "/opt/models")

    assert Settings(_env_file=None).model_dir_path == Path(
        os.path.abspath("/opt/models")
    )

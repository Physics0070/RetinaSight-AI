"""Shared test fixtures.

Each test gets an isolated in-memory SQLite database with the full schema and
the real RBAC policy seeded — authorization is exercised for real, never mocked.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import hash_password
from app.db.base import Base
from app.domain.enums import RoleName, UserStatus
from app.main import create_app
from app.models import User
from app.models.patient import Patient
from app.services.rbac_service import RBACService

TEST_PASSWORD = "TestPassw0rd!2024"


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Iterator[None]:
    """Rate-limit counters are process-global; isolate them between tests."""
    from app.core.rate_limit import login_limiter

    login_limiter.reset()
    yield
    login_limiter.reset()


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()

    RBACService(session).seed_policy()
    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    app = create_app()

    def _override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db_session: Session):
    """Factory creating an active user with a role (and patient link if needed)."""

    def _make(
        email: str,
        role: RoleName,
        *,
        password: str = TEST_PASSWORD,
        status: UserStatus = UserStatus.ACTIVE,
        link_patient: bool = False,
    ) -> User:
        user = User(
            email=email.lower(),
            password_hash=hash_password(password),
            full_name=f"Test {role.value}",
            status=status.value,
        )
        db_session.add(user)
        db_session.flush()
        RBACService(db_session).assign_role(user_id=user.id, role_name=role)

        if link_patient:
            db_session.add(
                Patient(
                    patient_code=f"PT-{user.id.hex[:8]}",
                    full_name=user.full_name,
                    portal_user_id=user.id,
                )
            )
        db_session.commit()
        return user

    return _make


@pytest.fixture
def login(client: TestClient):
    """Authenticate and return an Authorization header."""

    def _login(email: str, password: str = TEST_PASSWORD) -> dict[str, str]:
        response = client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        assert response.status_code == 200, response.text
        token = response.json()["tokens"]["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _login

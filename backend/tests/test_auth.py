"""Authentication behaviour: login, token rotation, replay defence, logout."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.domain.enums import RoleName, UserStatus
from tests.conftest import TEST_PASSWORD


def test_login_returns_tokens_and_identity(client: TestClient, make_user) -> None:
    make_user("worker@example.com", RoleName.HEALTH_WORKER)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "worker@example.com", "password": TEST_PASSWORD},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tokens"]["access_token"]
    assert body["tokens"]["refresh_token"]
    assert body["user"]["roles"] == [RoleName.HEALTH_WORKER.value]
    assert "SCREENING_CREATE" in body["user"]["permissions"]


def test_login_rejects_wrong_password_without_revealing_account(
    client: TestClient, make_user
) -> None:
    make_user("worker@example.com", RoleName.HEALTH_WORKER)

    wrong = client.post(
        "/api/v1/auth/login",
        json={"email": "worker@example.com", "password": "NotTheRightPassword1!"},
    )
    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "NotTheRightPassword1!"},
    )

    assert wrong.status_code == 401
    assert unknown.status_code == 401
    # Identical response for both → no account enumeration.
    assert wrong.json() == unknown.json()


def test_inactive_account_cannot_log_in(client: TestClient, make_user) -> None:
    make_user("dormant@example.com", RoleName.DOCTOR, status=UserStatus.INACTIVE)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "dormant@example.com", "password": TEST_PASSWORD},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_inactive"


def test_password_is_never_returned_or_stored_in_plaintext(
    client: TestClient, make_user, db_session
) -> None:
    user = make_user("secure@example.com", RoleName.ADMIN)

    assert TEST_PASSWORD not in user.password_hash
    assert user.password_hash.startswith("$argon2")

    body = client.post(
        "/api/v1/auth/login",
        json={"email": "secure@example.com", "password": TEST_PASSWORD},
    ).text
    assert TEST_PASSWORD not in body
    assert "password_hash" not in body


def test_refresh_rotates_token_and_old_token_stops_working(
    client: TestClient, make_user
) -> None:
    make_user("rotate@example.com", RoleName.DOCTOR)
    tokens = client.post(
        "/api/v1/auth/login",
        json={"email": "rotate@example.com", "password": TEST_PASSWORD},
    ).json()["tokens"]

    refreshed = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()["tokens"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    # The rotated-away token must be rejected.
    replayed = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replayed.status_code == 401


def test_refresh_replay_revokes_the_whole_token_family(
    client: TestClient, make_user
) -> None:
    make_user("replay@example.com", RoleName.DOCTOR)
    first = client.post(
        "/api/v1/auth/login",
        json={"email": "replay@example.com", "password": TEST_PASSWORD},
    ).json()["tokens"]

    second = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    ).json()["tokens"]

    # Replaying the old token signals compromise...
    client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})

    # ...so even the currently-valid token is revoked.
    after = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]}
    )
    assert after.status_code == 401


def test_me_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_returns_effective_permissions(client: TestClient, make_user, login) -> None:
    make_user("doc@example.com", RoleName.DOCTOR)
    headers = login("doc@example.com")

    body = client.get("/api/v1/auth/me", headers=headers).json()

    assert body["email"] == "doc@example.com"
    assert "CLINICAL_REVIEW" in body["permissions"]
    assert "CONFIG_MANAGE" not in body["permissions"]


def test_garbage_token_is_rejected(client: TestClient) -> None:
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


def test_logout_revokes_refresh_token(client: TestClient, make_user, login) -> None:
    make_user("bye@example.com", RoleName.HEALTH_WORKER)
    tokens = client.post(
        "/api/v1/auth/login",
        json={"email": "bye@example.com", "password": TEST_PASSWORD},
    ).json()["tokens"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    out = client.post(
        "/api/v1/auth/logout",
        headers=headers,
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert out.status_code == 200

    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 401
    )


def test_health_and_readiness(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/health/ready").status_code == 200

"""Login rate limiting.

The limiter is a mitigation, not a guarantee — see app/core/rate_limit.py for
its documented single-process scope. These tests pin the behaviour that does
hold.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.errors import RateLimitError
from app.core.rate_limit import SlidingWindowLimiter, login_key, login_limiter
from app.domain.enums import RoleName
from tests.conftest import TEST_PASSWORD


# --------------------------------------------------------------------------- #
# Limiter mechanics
# --------------------------------------------------------------------------- #
def test_allows_attempts_up_to_the_limit() -> None:
    limiter = SlidingWindowLimiter(limit=3)

    for _ in range(3):
        limiter.check("key")  # must not raise


def test_blocks_the_attempt_past_the_limit() -> None:
    limiter = SlidingWindowLimiter(limit=3)
    for _ in range(3):
        limiter.check("key")

    with pytest.raises(RateLimitError) as exc:
        limiter.check("key")

    assert "wait" in exc.value.message.lower()
    assert exc.value.status_code == 429


def test_counters_are_independent_per_key() -> None:
    """One attacker must not exhaust another user's allowance."""
    limiter = SlidingWindowLimiter(limit=2)
    limiter.check("attacker|victim@example.com")
    limiter.check("attacker|victim@example.com")

    # The victim signing in from their own address is unaffected.
    limiter.check("victim-ip|victim@example.com")


def test_window_expiry_restores_the_allowance(monkeypatch) -> None:
    """Driven by a fake clock — a real one has coarse resolution on Windows,
    which would make this flaky rather than meaningful."""
    clock = {"now": 1000.0}
    monkeypatch.setattr("app.core.rate_limit.time.monotonic", lambda: clock["now"])

    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
    limiter.check("key")
    limiter.check("key")
    with pytest.raises(RateLimitError):
        limiter.check("key")

    clock["now"] += 61  # the window has now elapsed
    limiter.check("key")
    limiter.check("key")


def test_attempts_inside_the_window_still_count(monkeypatch) -> None:
    clock = {"now": 500.0}
    monkeypatch.setattr("app.core.rate_limit.time.monotonic", lambda: clock["now"])

    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
    limiter.check("key")
    clock["now"] += 30  # still inside the window
    limiter.check("key")

    with pytest.raises(RateLimitError):
        limiter.check("key")


def test_a_zero_limit_disables_limiting() -> None:
    limiter = SlidingWindowLimiter(limit=0)

    for _ in range(100):
        limiter.check("key")


def test_key_combines_address_and_email() -> None:
    key = login_key("203.0.113.7", "  User@Example.COM ")

    assert key == "203.0.113.7|user@example.com"
    # A missing address still produces a usable, stable key.
    assert login_key(None, "a@b.com") == "unknown|a@b.com"


def test_expired_keys_are_evicted_so_memory_does_not_grow(monkeypatch) -> None:
    """A spray of unique keys must not exhaust memory.

    Eviction normally triggers only above MAX_TRACKED_KEYS (10,000); the cap is
    lowered here so the behaviour can be exercised without allocating that many.
    """
    clock = {"now": 100.0}
    monkeypatch.setattr("app.core.rate_limit.time.monotonic", lambda: clock["now"])
    monkeypatch.setattr("app.core.rate_limit.MAX_TRACKED_KEYS", 50)

    limiter = SlidingWindowLimiter(limit=5, window_seconds=60)
    for index in range(60):
        limiter.check(f"key-{index}")
    assert len(limiter._hits) == 60  # noqa: SLF001

    # Once every entry has aged out, the next call reclaims them.
    clock["now"] += 120
    limiter.check("fresh-key")

    assert len(limiter._hits) < 60  # noqa: SLF001


# --------------------------------------------------------------------------- #
# Endpoint behaviour
# --------------------------------------------------------------------------- #
def test_repeated_failed_logins_are_eventually_refused(
    client: TestClient, make_user, monkeypatch
) -> None:
    make_user("target@example.com", RoleName.DOCTOR)
    monkeypatch.setattr(login_limiter, "limit", 5)

    statuses = [
        client.post(
            "/api/v1/auth/login",
            json={"email": "target@example.com", "password": "WrongPassword!123"},
        ).status_code
        for _ in range(7)
    ]

    assert statuses[:5] == [401] * 5
    assert 429 in statuses[5:]


def test_rate_limited_response_is_user_readable(
    client: TestClient, make_user, monkeypatch
) -> None:
    make_user("readable@example.com", RoleName.DOCTOR)
    monkeypatch.setattr(login_limiter, "limit", 1)

    client.post(
        "/api/v1/auth/login",
        json={"email": "readable@example.com", "password": "Wrong!12345"},
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "readable@example.com", "password": "Wrong!12345"},
    )

    assert response.status_code == 429
    body = response.json()["error"]
    assert body["code"] == "rate_limited"
    # No stack trace, no internal detail.
    assert "Traceback" not in body["message"]
    assert body["details"]["retry_after_seconds"] > 0


def test_a_successful_login_clears_the_counter(
    client: TestClient, make_user, monkeypatch
) -> None:
    """A user who mistypes twice should not be locked out for the window."""
    make_user("forgiving@example.com", RoleName.DOCTOR)
    monkeypatch.setattr(login_limiter, "limit", 4)

    for _ in range(2):
        client.post(
            "/api/v1/auth/login",
            json={"email": "forgiving@example.com", "password": "Wrong!12345"},
        )

    ok = client.post(
        "/api/v1/auth/login",
        json={"email": "forgiving@example.com", "password": TEST_PASSWORD},
    )
    assert ok.status_code == 200

    # The allowance is restored, not merely partially consumed.
    for _ in range(3):
        retry = client.post(
            "/api/v1/auth/login",
            json={"email": "forgiving@example.com", "password": "Wrong!12345"},
        )
        assert retry.status_code == 401

"""Tests for the reliability layer (all offline)."""

import time

import pytest
from fastapi.testclient import TestClient

from food_ingredients_ai.harness.runner import CircuitBreaker, CircuitOpenError
from food_ingredients_ai.interop.auth import issue_token
from food_ingredients_ai.service import app as app_module
from food_ingredients_ai.service import reliability
from food_ingredients_ai.service.app import app
from food_ingredients_ai.service.reliability import (
    IdempotencyStore,
    RateLimiter,
    RateLimitExceeded,
    RetryExhausted,
    backoff_delay,
    retry_sync,
)

client = TestClient(app)


def _auth(subject, scopes):
    return {"Authorization": f"Bearer {issue_token(subject, scopes)}"}


@pytest.fixture()
def fresh_breaker(monkeypatch):
    """Isolate the global live-LLM circuit breaker per test."""
    monkeypatch.setattr(
        reliability, "live_llm_breaker", CircuitBreaker(failure_threshold=3, cooldown_seconds=60.0)
    )


@pytest.fixture()
def no_retries(monkeypatch):
    monkeypatch.setattr(reliability, "SERVICE_RETRY_MAX", 0)


# -- retry_sync --------------------------------------------------------------


def test_retry_succeeds_after_transient_failures():
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise ConnectionError("boom")
        return "ok"

    assert retry_sync(flaky, base_delay=0, jitter=False) == "ok"
    assert len(attempts) == 3


def test_retry_exhausted_raises_last_error():
    def always_fails():
        raise ConnectionError("down")

    with pytest.raises(RetryExhausted) as exc_info:
        retry_sync(always_fails, max_retries=2, base_delay=0, jitter=False)
    assert isinstance(exc_info.value.last_error, ConnectionError)
    assert exc_info.value.attempts == 3


def test_retry_does_not_retry_non_transient_errors():
    calls = []

    def bad():
        calls.append(1)
        raise ValueError("programmer error")

    with pytest.raises(ValueError):
        retry_sync(bad, max_retries=3, base_delay=0)
    assert len(calls) == 1


def test_backoff_delay_bounds():
    # No jitter: exact exponential.
    assert backoff_delay(1, 0.5, 30.0, jitter=False) == 0.5
    assert backoff_delay(3, 0.5, 30.0, jitter=False) == 2.0
    # Capped at max_delay.
    assert backoff_delay(10, 0.5, 30.0, jitter=False) == 30.0
    # Jitter: within [0, computed].
    for _ in range(20):
        d = backoff_delay(2, 0.5, 30.0, jitter=True)
        assert 0.0 <= d <= 1.0


def test_retry_sleeps_with_backoff():
    sleeps = []

    def fails():
        raise TimeoutError("t")

    with pytest.raises(RetryExhausted):
        retry_sync(fails, max_retries=2, base_delay=0.5, jitter=False,
                   sleep=lambda s: sleeps.append(s))
    assert sleeps == [0.5, 1.0]


# -- circuit breaker ---------------------------------------------------------


def test_breaker_opens_and_fails_fast():
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=60.0)

    def boom():
        raise ConnectionError("x")

    with pytest.raises(ConnectionError):
        breaker.call(boom)
    with pytest.raises(ConnectionError):
        breaker.call(boom)
    # Now open: rejected without calling fn.
    with pytest.raises(CircuitOpenError):
        breaker.call(lambda: "never")


# -- rate limiter ------------------------------------------------------------


def test_rate_limiter_allows_then_429s():
    limiter = RateLimiter(per_minute=2)
    limiter.check("c1")
    limiter.check("c1")
    with pytest.raises(RateLimitExceeded) as exc_info:
        limiter.check("c1")
    assert exc_info.value.retry_after_seconds >= 1
    # Other clients unaffected.
    limiter.check("c2")


def test_idempotency_store_roundtrip_and_expiry():
    store = IdempotencyStore(ttl_seconds=0.05)
    assert store.get("s", "k") is None
    store.put("s", "k", 200, {"a": 1})
    assert store.get("s", "k") == (200, {"a": 1})
    time.sleep(0.06)
    assert store.get("s", "k") is None


# -- service-level: graceful degradation -------------------------------------


def test_live_failure_falls_back_to_offline_degraded(
    monkeypatch, fresh_breaker, no_retries
):
    def fake_run(ctx, live):
        if live:
            raise ConnectionError("azure openai unreachable")
        return {"analyze_ingredients": {"flagged_count": 1}}

    monkeypatch.setattr(app_module, "_run_workflow_sync", fake_run)
    r = client.post(
        "/api/reformulate",
        json={"scenario": "sweet_bakery_cake", "live": True},
        headers=_auth("degraded-client", ["formulation:write"]),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["degraded"] is True
    assert body["mode"] == "offline"
    assert "degraded_reason" in body
    assert r.headers["X-Service-Degraded"] == "true"


def test_open_circuit_degrades_without_calling_live(monkeypatch, fresh_breaker):
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=600.0)

    def boom():
        raise ConnectionError("x")

    with pytest.raises(ConnectionError):
        breaker.call(boom)
    assert breaker.state == CircuitBreaker.OPEN
    monkeypatch.setattr(reliability, "live_llm_breaker", breaker)

    live_calls = []

    def fake_run(ctx, live):
        live_calls.append(live)
        if live:
            raise AssertionError("live should not be attempted with open circuit")
        return {"ok": True}

    monkeypatch.setattr(app_module, "_run_workflow_sync", fake_run)
    r = client.post(
        "/api/reformulate",
        json={"scenario": "sweet_bakery_cake", "live": True},
        headers=_auth("breaker-client", ["formulation:write"]),
    )
    assert r.status_code == 200
    assert r.json()["degraded"] is True
    assert live_calls == [False]


# -- service-level: idempotency ----------------------------------------------


def test_idempotency_key_dedups_post(monkeypatch):
    calls = []

    def counting_run(ctx, live):
        calls.append((ctx["formula_id"], live))
        return {"analyze_ingredients": {"flagged_count": 2}}

    monkeypatch.setattr(app_module, "_run_workflow_sync", counting_run)
    headers = _auth("idem-client", ["formulation:write"])
    headers["Idempotency-Key"] = "key-123"
    body = {"scenario": "sweet_bakery_cake"}

    r1 = client.post("/api/reformulate", json=body, headers=headers)
    r2 = client.post("/api/reformulate", json=body, headers=headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.headers.get("X-Idempotent-Replay") == "true"
    assert r1.json() == r2.json()
    assert len(calls) == 1  # executed once


def test_different_idempotency_keys_execute_twice(monkeypatch):
    calls = []

    def counting_run(ctx, live):
        calls.append(1)
        return {"ok": True}

    monkeypatch.setattr(app_module, "_run_workflow_sync", counting_run)
    base = _auth("idem-client-2", ["formulation:write"])
    h1 = {**base, "Idempotency-Key": "k1"}
    h2 = {**base, "Idempotency-Key": "k2"}
    client.post("/api/reformulate", json={"scenario": "sweet_bakery_cake"}, headers=h1)
    client.post("/api/reformulate", json={"scenario": "sweet_bakery_cake"}, headers=h2)
    assert len(calls) == 2


# -- service-level: rate limiting --------------------------------------------


def test_rate_limit_returns_429(monkeypatch):
    monkeypatch.setattr(reliability, "rate_limiter", RateLimiter(per_minute=2))
    headers = _auth("limited-client", ["esg:read"])
    r1 = client.post("/api/agents/esg/run", json={}, headers=headers)
    r2 = client.post("/api/agents/esg/run", json={}, headers=headers)
    r3 = client.post("/api/agents/esg/run", json={}, headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert "Retry-After" in r3.headers

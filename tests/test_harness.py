"""Tests for the harness-engineering package (runner, breaker, guardrails)."""

import time

import pytest

import ingredion_ai.harness.runner as runner_module
from ingredion_ai.harness import (
    CircuitBreaker,
    CircuitOpenError,
    GuardrailViolation,
    Harness,
    policy_guardrail,
)


def _ok(*args, **kwargs):
    return "done"


def test_run_success_first_try():
    harness = Harness(max_retries=2, base_delay=0.001)
    records = []
    harness.on_run_end.append(records.append)
    assert harness.run(_ok, 1, key="v") == "done"
    assert len(records) == 1
    record = records[0]
    assert record["fn_name"] == "_ok"
    assert record["success"] is True
    assert record["attempts"] == 1
    assert record["error"] is None
    assert record["latency_s"] >= 0.0


def test_run_retry_then_success():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("not yet")
        return "recovered"

    harness = Harness(max_retries=3, base_delay=0.001)
    records = []
    harness.on_run_end.append(records.append)
    assert harness.run(flaky) == "recovered"
    assert calls["n"] == 3
    assert records[0]["success"] is True
    assert records[0]["attempts"] == 3


def test_run_exhausts_retries_raises_last_error():
    def always_fails():
        raise ValueError("boom")

    harness = Harness(max_retries=2, base_delay=0.001)
    records = []
    harness.on_run_end.append(records.append)
    with pytest.raises(ValueError, match="boom"):
        harness.run(always_fails)
    record = records[0]
    assert record["success"] is False
    assert record["attempts"] == 3  # first try + 2 retries
    assert "ValueError" in record["error"]


def test_backoff_delays_grow(monkeypatch):
    sleeps = []
    monkeypatch.setattr(runner_module.time, "sleep", sleeps.append)

    def always_fails():
        raise RuntimeError("x")

    harness = Harness(max_retries=3, base_delay=0.1)
    with pytest.raises(RuntimeError):
        harness.run(always_fails)
    # deterministic exponential backoff: 0.1, 0.2, 0.4
    assert sleeps == [0.1, 0.2, 0.4]


def test_timeout_raises_timeout_error():
    def slow():
        time.sleep(0.5)
        return "too late"

    harness = Harness(max_retries=0, base_delay=0.001, timeout_seconds=0.05)
    with pytest.raises(TimeoutError):
        harness.run(slow)


def test_circuit_breaker_opens_and_half_opens():
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.01)

    def bad():
        raise RuntimeError("down")

    assert breaker.state == "closed"
    with pytest.raises(RuntimeError):
        breaker.call(bad)
    with pytest.raises(RuntimeError):
        breaker.call(bad)
    assert breaker.state == "open"
    # open circuit rejects immediately without calling fn
    with pytest.raises(CircuitOpenError):
        breaker.call(_ok)
    # after cooldown, a trial call succeeds -> circuit closes
    time.sleep(0.02)
    assert breaker.call(_ok) == "done"
    assert breaker.state == "closed"
    assert breaker.consecutive_failures == 0


def test_circuit_breaker_half_open_failure_reopens():
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.01)

    def bad():
        raise RuntimeError("still down")

    with pytest.raises(RuntimeError):
        breaker.call(bad)
    assert breaker.state == "open"
    time.sleep(0.02)
    with pytest.raises(RuntimeError):
        breaker.call(bad)  # half-open trial fails -> re-opens
    assert breaker.state == "open"
    with pytest.raises(CircuitOpenError):
        breaker.call(_ok)


def test_pre_hook_veto_raises_guardrail_violation():
    harness = Harness()

    def veto_everything(fn_name, *args, **kwargs):
        return False

    harness.pre_hooks.append(veto_everything)
    records = []
    harness.on_run_end.append(records.append)
    with pytest.raises(GuardrailViolation):
        harness.run(_ok)
    assert records[0]["success"] is False
    assert records[0]["attempts"] == 0


def test_post_hook_observes_result():
    seen = []

    def observer(fn_name, result):
        seen.append((fn_name, result))

    harness = Harness()
    harness.post_hooks.append(observer)
    harness.run(_ok)
    assert seen == [("_ok", "done")]


def test_on_run_end_receives_record_with_attempts():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("first fails")
        return "fine"

    records = []
    harness = Harness(max_retries=1, base_delay=0.001)
    harness.on_run_end.append(records.append)
    harness.run(flaky)
    (record,) = records
    assert record["fn_name"] == "flaky"
    assert record["success"] is True
    assert record["attempts"] == 2
    assert isinstance(record["latency_s"], float)


def test_policy_guardrail_denies_disallowed_action():
    harness = Harness()
    records = []
    harness.on_run_end.append(records.append)
    # 'place_order' is explicitly denied for rd_formulation in demo policy
    hook = policy_guardrail("place_order", agent="rd_formulation")
    harness.pre_hooks.append(hook)
    with pytest.raises(GuardrailViolation):
        harness.run(_ok)
    assert "denied" in hook.last_reason
    assert records[0]["attempts"] == 0


def test_policy_guardrail_allows_listed_action():
    harness = Harness()
    hook = policy_guardrail("analyze_ingredients", agent="rd_formulation")
    harness.pre_hooks.append(hook)
    assert harness.run(_ok) == "done"
    assert "allowed" in hook.last_reason

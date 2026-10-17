"""Tests for the agent control plane (all deterministic, no network)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from food_ingredients_ai.controlplane import (
    ActionBudget,
    BehaviorDrift,
    BudgetManager,
    CircuitBreaker,
    ControlLedger,
    EnforcementGate,
    KillSwitch,
    SpendCap,
)


class FakeClock:
    def __init__(self) -> None:
        self.now_dt = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now_dt

    def advance(self, **kwargs) -> None:
        self.now_dt += timedelta(**kwargs)


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------


def test_action_budget_allows_under_limit():
    b = ActionBudget(max_per_run=3)
    for _ in range(3):
        allowed, _ = b.check_and_record("rd")
        assert allowed


def test_action_budget_denies_at_run_limit_with_reason():
    b = ActionBudget(max_per_run=2)
    b.check_and_record("rd")
    b.check_and_record("rd")
    allowed, reason = b.check_and_record("rd")
    assert not allowed
    assert "run" in reason and "rd" in reason


def test_action_budget_daily_reset_with_fake_clock():
    clock = FakeClock()
    b = ActionBudget(max_per_day=2, clock=clock)
    b.check_and_record("rd")
    b.check_and_record("rd")
    assert not b.check("rd")[0]
    clock.advance(minutes=721)  # past UTC midnight
    allowed, _ = b.check("rd")
    assert allowed


def test_action_budget_hourly_window_expires():
    clock = FakeClock()
    b = ActionBudget(max_per_hour=2, clock=clock)
    b.check_and_record("rd")
    b.check_and_record("rd")
    assert not b.check("rd")[0]
    clock.advance(minutes=61)
    assert b.check("rd")[0]


def test_spend_cap_denies_over_run_cap_with_reason():
    cap = SpendCap(max_usd_per_run=1.0)
    assert cap.check_and_record("rd", 0.6)[0]
    allowed, reason = cap.check_and_record("rd", 0.5)
    assert not allowed
    assert "spend cap" in reason


def test_spend_cap_daily_cap_denies():
    clock = FakeClock()
    cap = SpendCap(max_usd_per_day=1.0, clock=clock)
    assert cap.check_and_record("rd", 0.9)[0]
    allowed, _ = cap.check_and_record("rd", 0.2)
    assert not allowed
    clock.advance(days=1)
    assert cap.check_and_record("rd", 0.2)[0]


def test_budget_manager_check_signature_records_on_allow():
    mgr = BudgetManager(
        action_budget=ActionBudget(max_per_run=5),
        spend_cap=SpendCap(max_usd_per_run=10.0),
    )
    allowed, reason = mgr.check("supply_chain", "forecast_demand", 0.01, run_id="r1")
    assert allowed
    assert "forecast_demand" in reason
    assert mgr.action_budget.usage("supply_chain", "r1")["run"] == 1
    assert mgr.spend_cap.spend("supply_chain", "r1")["run_usd"] == pytest.approx(0.01)


def test_budget_manager_denies_without_recording():
    mgr = BudgetManager(
        action_budget=ActionBudget(max_per_run=1),
        spend_cap=SpendCap(max_usd_per_run=10.0),
    )
    mgr.check("rd", "a", 0.0, run_id="r1")
    allowed, _ = mgr.check("rd", "b", 0.0, run_id="r1")
    assert not allowed
    assert mgr.action_budget.usage("rd", "r1")["run"] == 1  # denied action not counted


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


def test_circuit_trips_after_threshold_failures():
    cb = CircuitBreaker(failure_threshold=3, window_seconds=60)
    for _ in range(2):
        cb.record_failure("rd")
        assert cb.allows("rd")[0]
    cb.record_failure("rd")
    assert cb.status("rd")["state"] == "open"
    assert not cb.allows("rd")[0]


def test_circuit_blocks_while_open_with_reason():
    cb = CircuitBreaker(failure_threshold=1, window_seconds=60)
    cb.record_failure("rd")
    allowed, reason = cb.allows("rd")
    assert not allowed
    assert "open" in reason


def test_circuit_half_open_probe_success_closes():
    clock = FakeClock()
    cb = CircuitBreaker(
        failure_threshold=2, window_seconds=60, cooldown_seconds=30, clock=clock
    )
    cb.record_failure("rd")
    cb.record_failure("rd")
    assert not cb.allows("rd")[0]
    clock.advance(seconds=31)
    allowed, reason = cb.allows("rd")
    assert allowed and "half-open" in reason
    cb.record_success("rd")
    assert cb.status("rd")["state"] == "closed"
    assert cb.allows("rd")[0]


def test_circuit_half_open_probe_failure_reopens():
    clock = FakeClock()
    cb = CircuitBreaker(
        failure_threshold=1, window_seconds=60, cooldown_seconds=30, clock=clock
    )
    cb.record_failure("rd")
    clock.advance(seconds=31)
    assert cb.allows("rd")[0]  # probe
    cb.record_failure("rd")  # probe failed
    assert cb.status("rd")["state"] == "open"
    assert not cb.allows("rd")[0]


def test_circuit_ignores_failures_outside_window():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=3, window_seconds=60, clock=clock)
    cb.record_failure("rd")
    cb.record_failure("rd")
    clock.advance(seconds=61)  # both failures age out
    cb.record_failure("rd")
    assert cb.status("rd")["state"] == "closed"
    assert cb.allows("rd")[0]


def test_circuit_reset_force_closes():
    cb = CircuitBreaker(failure_threshold=1)
    cb.record_failure("rd")
    assert not cb.allows("rd")[0]
    cb.reset("rd")
    assert cb.status("rd")["state"] == "closed"
    assert cb.allows("rd")[0]


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------


def test_killswitch_global_halt_blocks_all_agents():
    ks = KillSwitch()
    ks.engage()
    assert ks.is_halted("rd")
    assert ks.is_halted("supply_chain")
    assert ks.is_global_halt()


def test_killswitch_per_agent_halt_blocks_only_one():
    ks = KillSwitch()
    ks.engage("rd")
    assert ks.is_halted("rd")
    assert not ks.is_halted("supply_chain")
    assert not ks.is_global_halt()
    assert ks.halted_agents() == ["rd"]


def test_killswitch_release_restores():
    ks = KillSwitch()
    ks.engage("rd")
    ks.release("rd")
    assert not ks.is_halted("rd")
    ks.engage()
    ks.release()
    assert not ks.is_halted("rd")


def test_killswitch_global_release_keeps_per_agent_halts():
    ks = KillSwitch()
    ks.engage("rd")
    ks.engage()
    ks.release()
    assert not ks.is_global_halt()
    assert ks.is_halted("rd")  # deliberate per-agent halt survives


# ---------------------------------------------------------------------------
# Enforcement gate
# ---------------------------------------------------------------------------


def _tripped_gate() -> EnforcementGate:
    gate = EnforcementGate(
        budgets=BudgetManager(action_budget=ActionBudget(max_per_run=1))
    )
    gate.killswitch.engage("rd")
    gate.circuit.record_failure("rd")
    gate.circuit.record_failure("rd")
    gate.circuit.record_failure("rd")
    gate.circuit.record_failure("rd")
    gate.circuit.record_failure("rd")  # tripped (threshold 5)
    gate.budgets.check("rd", "x", 0.0, run_id="r1")  # exhaust run budget
    return gate


def test_enforcement_killswitch_beats_circuit_beats_budget():
    gate = _tripped_gate()
    decision = gate.authorize("rd", "analyze_ingredients", 0.0, run_id="r1")
    assert not decision["allowed"]
    assert "killswitch" in decision["reason"]
    # Short-circuit: later checks never evaluated.
    assert [c["name"] for c in decision["checks"]] == ["killswitch"]


def test_enforcement_circuit_denial_short_circuits_budget():
    gate = EnforcementGate()
    for _ in range(5):
        gate.circuit.record_failure("supply_chain")
    decision = gate.authorize("supply_chain", "forecast_demand", 0.0)
    assert not decision["allowed"]
    assert "circuit" in decision["reason"]
    assert [c["name"] for c in decision["checks"]] == ["killswitch", "circuit"]


def test_enforcement_all_clear_allows_with_full_check_trail():
    gate = EnforcementGate()
    decision = gate.authorize("esg", "collect_esg", 0.01, run_id="r1")
    assert decision["allowed"]
    assert [c["name"] for c in decision["checks"]] == [
        "killswitch",
        "circuit",
        "budget",
    ]
    assert all(c["allowed"] for c in decision["checks"])


def test_enforcement_ledger_records_every_decision():
    gate = EnforcementGate()
    gate.authorize("rd", "a", 0.0)
    gate.killswitch.engage("rd")
    gate.authorize("rd", "b", 0.0)
    entries = list(gate.ledger.read())
    assert len(entries) == 2
    assert entries[0]["allowed"] and not entries[1]["allowed"]
    assert entries[1]["action"] == "b"


def test_enforcement_report_outcome_feeds_circuit():
    gate = EnforcementGate(
        circuit=CircuitBreaker(failure_threshold=2, window_seconds=60)
    )
    assert gate.authorize("rd", "a", 0.0)["allowed"]
    gate.report_outcome("rd", "a", success=False)
    assert gate.authorize("rd", "b", 0.0)["allowed"]
    gate.report_outcome("rd", "b", success=False)  # trips the circuit
    decision = gate.authorize("rd", "c", 0.0)
    assert not decision["allowed"]
    assert "circuit" in decision["reason"]


# ---------------------------------------------------------------------------
# Behavior drift
# ---------------------------------------------------------------------------


def test_drift_flags_unseen_action_spike():
    d = BehaviorDrift(baseline_minimum=20, recent_window=10, unseen_threshold=0.3)
    for _ in range(20):
        d.record("rd", "analyze_ingredients")
    for _ in range(6):
        d.record("rd", "analyze_ingredients")
    for _ in range(4):
        d.record("rd", "place_order")  # 40% unseen
    drifted, reason = d.check("rd")
    assert drifted
    assert "place_order" in reason


def test_drift_no_flag_on_normal_traffic():
    d = BehaviorDrift(baseline_minimum=20, recent_window=10, unseen_threshold=0.3)
    actions = ["analyze_ingredients", "suggest_substitutes", "validate_claims"]
    for i in range(30):
        d.record("rd", actions[i % 3])
    drifted, _ = d.check("rd")
    assert not drifted


def test_drift_insufficient_data_never_flags():
    d = BehaviorDrift(baseline_minimum=20, recent_window=10)
    for _ in range(10):
        d.record("rd", "brand_new_action")
    drifted, reason = d.check("rd")
    assert not drifted
    assert "insufficient data" in reason


def test_drift_reset_clears_history():
    d = BehaviorDrift(baseline_minimum=5, recent_window=3, unseen_threshold=0.3)
    for _ in range(5):
        d.record("rd", "a")
    d.reset("rd")
    drifted, reason = d.check("rd")
    assert not drifted and "insufficient data" in reason


# ---------------------------------------------------------------------------
# Control ledger
# ---------------------------------------------------------------------------


def test_ledger_appends_with_sequence_numbers():
    ledger = ControlLedger()
    e1 = ledger.record("rd", "a", True, "ok")
    e2 = ledger.record("rd", "b", False, "denied")
    assert (e1["seq"], e2["seq"]) == (1, 2)
    assert len(ledger) == 2


def test_ledger_verify_chain_passes_and_detects_tampering():
    ledger = ControlLedger()
    ledger.record("rd", "a", True, "ok")
    ledger.record("rd", "b", False, "denied")
    assert ledger.verify_chain()
    list(ledger.read())[0]["reason"] = "tampered"
    assert not ledger.verify_chain()


def test_ledger_denials_filters_by_agent():
    ledger = ControlLedger()
    ledger.record("rd", "a", False, "nope")
    ledger.record("esg", "b", False, "nope")
    ledger.record("rd", "c", True, "ok")
    assert len(ledger.denials()) == 2
    assert [e["agent_id"] for e in ledger.denials("rd")] == ["rd"]

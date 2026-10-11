"""Tests for the supply chain agent (all offline, deterministic)."""

import pytest

from ingredion_ai.agents.supply_chain import SupplyChainAgent
from ingredion_ai.agents.supply_chain import forecaster, inventory, quality, scheduler


def _agent():
    return SupplyChainAgent()


def test_forecast_first_point_exact():
    out = forecaster.forecast_sku("PF-200", periods=4)
    assert out["forecast"][0] == 56.6
    assert len(out["forecast"]) == 4


def test_forecast_deterministic():
    assert forecaster.forecast_sku("HB-10") == forecaster.forecast_sku("HB-10")


def test_forecast_needs_two_points():
    with pytest.raises(ValueError):
        forecaster.forecast([5.0], periods=2)


def test_forecast_unknown_sku():
    with pytest.raises(KeyError):
        forecaster.forecast_sku("NOPE")


def test_forecast_confidence_interval_nonnegative():
    out = forecaster.forecast([10.0, 10.0, 10.0, 10.0], periods=2)
    assert out["forecast"] == [10.0, 10.0]
    assert out["confidence_interval"] == 0.0


def test_reorder_point_exact():
    assert inventory.reorder_point(8.0, 7.0, 0.2) == 67.2


def test_reorder_point_negative_raises():
    with pytest.raises(ValueError):
        inventory.reorder_point(-1.0, 7.0)


def test_suggest_purchases_below_rop():
    inv = {"PF-200": {"on_hand_tonnes": 20.0}}
    fc = {"PF-200": [56.6, 57.2, 57.8, 58.4]}
    suggestions = inventory.suggest_purchases(inv, fc, lead_time_days=7.0)
    assert len(suggestions) == 1
    assert suggestions[0]["sku"] == "PF-200"
    assert suggestions[0]["suggested_order_tonnes"] > 0


def test_suggest_purchases_above_rop_empty():
    inv = {"PF-200": {"on_hand_tonnes": 500.0}}
    fc = {"PF-200": [56.6, 57.2, 57.8, 58.4]}
    assert inventory.suggest_purchases(inv, fc) == []


def test_scheduler_respects_capacity():
    demand = [
        {"sku": "PF-200", "qty": 150.0, "need_day": 5},
        {"sku": "HB-10", "qty": 60.0, "need_day": 5},
    ]
    out = scheduler.schedule_production(demand, 100.0, 7)
    per_day = {}
    for s in out["schedule"]:
        per_day[s["day"]] = per_day.get(s["day"], 0.0) + s["qty"]
    assert all(qty <= 100.0 for qty in per_day.values())
    assert out["total_qty"] == 210.0


def test_scheduler_respects_shelf_life():
    demand = [{"sku": "X", "qty": 150.0, "need_day": 5}]
    out = scheduler.schedule_production(demand, 100.0, 3)
    assert all(s["day"] >= 5 - 3 for s in out["schedule"])


def test_scheduler_infeasible_raises():
    demand = [{"sku": "X", "qty": 500.0, "need_day": 5}]
    with pytest.raises(ValueError):
        scheduler.schedule_production(demand, 100.0, 1)


def test_scheduler_bad_capacity_raises():
    with pytest.raises(ValueError):
        scheduler.schedule_production([], 0.0, 3)


def test_quality_flags_out_of_spec():
    readings = [
        {"batch_id": "B1", "metric": "moisture", "value": 14.5},
        {"batch_id": "B2", "metric": "moisture", "value": 12.0},
    ]
    anomalies = quality.detect_anomalies(readings, {"moisture": (10.0, 14.0)})
    assert len(anomalies) == 1
    assert anomalies[0]["batch_id"] == "B1"
    assert anomalies[0]["deviation"] == 0.5


def test_quality_ignores_unknown_metric():
    readings = [{"batch_id": "B1", "metric": "mystery", "value": 999.0}]
    assert quality.detect_anomalies(readings, {}) == []


def test_agent_forecast_demand_task():
    out = _agent().execute("forecast_demand", {"skus": ["VP-80"], "periods": 2})
    assert len(out["forecasts"]["VP-80"]["forecast"]) == 2


def test_agent_optimize_inventory_uses_blackboard():
    agent = _agent()
    fc = agent.execute("forecast_demand", {"skus": ["PF-200"], "periods": 4})
    out = agent.execute(
        "optimize_inventory",
        {
            "inventory": {"PF-200": {"on_hand_tonnes": 1.0}},
            "blackboard": {"forecast_demand": fc},
        },
    )
    assert len(out["purchases"]) == 1


def test_agent_schedule_task():
    out = _agent().execute(
        "schedule_production",
        {
            "demand": [{"sku": "X", "qty": 50.0, "need_day": 3}],
            "capacity_per_day": 100.0,
            "shelf_life_days": 7,
        },
    )
    assert out["total_qty"] == 50.0


def test_agent_quality_task():
    out = _agent().execute(
        "detect_quality_anomalies",
        {
            "readings": [{"batch_id": "B9", "metric": "ph", "value": 9.0}],
            "spec_limits": {"ph": (5.0, 7.0)},
        },
    )
    assert out["anomaly_count"] == 1


def test_agent_unknown_task_raises():
    with pytest.raises(ValueError):
        _agent().execute("nope", {})

"""Tests for the four multi-agent business orchestration graphs.

All offline and deterministic (no API keys): every agent executes its
local ``execute()`` paths. Each flow is tested on its happy path and on
at least one conditional branch path; every path must terminate and
return per-node results in the final state.
"""

from __future__ import annotations

from food_ingredients_ai.graph.cost_spike_graph import run_cost_spike_graph
from food_ingredients_ai.graph.product_launch_graph import run_product_launch_graph
from food_ingredients_ai.graph.quality_issue_graph import run_quality_issue_graph
from food_ingredients_ai.graph.supply_disruption_graph import (
    run_supply_disruption_graph,
)

# -- supply disruption ------------------------------------------------------


def test_supply_disruption_shortage_notifies_customer():
    state = run_supply_disruption_graph()
    assert state["shortage"] is True
    assert state["outcome"] == "customer_notified"
    # Per-node results are all present in the final state.
    assert state["inventory"]["purchases"], "expected a purchase suggestion"
    assert state["substitute"]["substituted_count"] >= 0
    assert "carbon" in state["carbon"]
    assert "tech_sheet_markdown" in state["notification"]
    assert "Customer Technical Sheet" in state["notification"]["tech_sheet_markdown"]


def test_supply_disruption_no_shortage_takes_no_action():
    state = run_supply_disruption_graph(on_hand_tonnes=50.0)
    assert state["shortage"] is False
    assert state["outcome"] == "no_action"
    assert "notification" not in state  # response chain never ran
    assert "reason" in state


# -- product launch ---------------------------------------------------------


def test_product_launch_feasible_produces_launch_pack():
    state = run_product_launch_graph()
    assert state["feasible"] is True
    assert state["outcome"] == "launch_ready"
    assert "reformulated_formula" in state["formulation"]
    assert state["feasibility"]["total_qty"] > 0
    assert "report_markdown" in state["esg"]
    pack = state["launch_pack"]
    assert "cost_per_kg_usd" in pack["pricing"]["pricing"]
    assert "tech_sheet_markdown" in pack["tech_sheet"]


def test_product_launch_infeasible_is_blocked():
    state = run_product_launch_graph(capacity_per_day=0.001)
    assert state["feasible"] is False
    assert state["outcome"] == "blocked"
    assert "launch_pack" not in state  # launch chain never ran
    assert "error" in state["feasibility"]


# -- quality issue ----------------------------------------------------------


def test_quality_issue_anomaly_triggers_corrective_action():
    state = run_quality_issue_graph()
    assert state["anomaly_found"] is True
    assert state["outcome"] == "corrective_action_issued"
    assert state["trace"]["anomaly_count"] == 1
    assert state["trace"]["anomalies"][0]["batch_id"] == "B-1042"
    assert "flagged" in state["investigation"]
    assert state["investigation"]["formula_id"] == "sweet_bakery_cake"
    assert "report_markdown" in state["esg"]
    assert "tech_sheet_markdown" in state["corrective_note"]


def test_quality_issue_clean_batch_needs_no_action():
    state = run_quality_issue_graph(inject_anomaly=False)
    assert state["anomaly_found"] is False
    assert state["outcome"] == "no_issue_found"
    assert "corrective_note" not in state  # investigation never ran


# -- cost spike -------------------------------------------------------------


def test_cost_spike_saving_found_updates_pricing():
    state = run_cost_spike_graph()
    assert state["outcome"] == "price_updated"
    saving = state["saving"]
    assert saving["meets_hurdle"] is True
    assert saving["saving_pct"] >= 5.0
    # Saving is measured against the spiked baseline, not the old cost.
    assert saving["spiked_cost_per_kg_usd"] > saving["old_cost_per_kg_usd"]
    assert saving["new_cost_per_kg_usd"] < saving["spiked_cost_per_kg_usd"]
    assert "carbon" in state["carbon"]
    assert "cost_per_kg_usd" in state["pricing"]["pricing"]


def test_cost_spike_below_hurdle_takes_no_action():
    state = run_cost_spike_graph(min_saving_pct=999.0)
    assert state["outcome"] == "no_action"
    assert state["saving"]["meets_hurdle"] is False
    assert "pricing" not in state  # pricing never updated


def test_cost_spike_no_spike_means_no_saving():
    state = run_cost_spike_graph(spike_pct=0.0)
    assert state["outcome"] == "no_action"
    # Without a spike the clean-label swap costs more: nothing to save.
    assert state["saving"]["saving_pct"] < 0

"""Tests for the agentic-ERP finance graphs and FinOps forecasting.

All offline and deterministic (no API keys). Each finance flow is tested
on its happy path and on every conditional branch; every path must
terminate and return per-node results in the final state.
"""

from __future__ import annotations

from ingredion_ai.governance.approvals import ApprovalGate
from ingredion_ai.graph.invoice_graph import run_invoice_graph
from ingredion_ai.graph.procurement_graph import run_procurement_graph
from ingredion_ai.observability.costs import forecast_spend


# -- procurement ------------------------------------------------------------


def test_procurement_under_threshold_auto_issues_po():
    state = run_procurement_graph(approval_threshold_usd=20000.0)
    assert state["demand_justified"] is True
    assert state["needs_approval"] is False
    assert state["outcome"] == "po_issued"
    po = state["purchase_order"]
    assert po["po_id"] == "PO-CITRIC-ACID-5000"
    assert po["total_usd"] == 10500.0
    assert "approval" not in state  # HITL never ran
    assert state["supplier_notification"]["to"].startswith("Acme")


def test_procurement_over_threshold_approved_issues_po():
    # Default: $10,500 total over the $10,000 threshold; the demo
    # approver auto-approves, so the PO is still issued.
    state = run_procurement_graph()
    assert state["needs_approval"] is True
    assert state["approved"] is True
    assert state["outcome"] == "po_issued"
    assert state["approval"]["decision"] == "approved"
    assert state["approval"]["rounds"] == 1
    assert "po_id" in state["purchase_order"]


def test_procurement_rejected_when_human_denies():
    state = run_procurement_graph(approver=ApprovalGate(auto_approve=False))
    assert state["needs_approval"] is True
    assert state["approved"] is False
    assert state["outcome"] == "rejected"
    assert "purchase_order" not in state  # no PO created
    assert "reason" in state


def test_procurement_unjustified_demand_is_held():
    state = run_procurement_graph(on_hand_tonnes=100000.0)
    assert state["demand_justified"] is False
    assert state["outcome"] == "held"
    assert "purchase_order" not in state
    assert "reason" in state


# -- invoice ----------------------------------------------------------------


def test_invoice_mismatch_escalates():
    state = run_invoice_graph()
    assert state["matched"] is False
    assert state["outcome"] == "escalated"
    match = state["match"]
    assert match["po_total_usd"] == 10500.0
    assert match["invoice_total_usd"] == 10710.0
    flagged = state["investigation"]["flagged_lines"]
    assert len(flagged) == 1
    assert flagged[0]["variance_pct"] == 2.0
    assert state["escalation"]["invoice_id"] == "INV-2041"
    assert "payment" not in state  # payment never scheduled


def test_invoice_clean_match_schedules_payment():
    state = run_invoice_graph(inject_mismatch=False)
    assert state["matched"] is True
    assert state["outcome"] == "payment_scheduled"
    payment = state["payment"]
    assert payment["amount_usd"] == 10500.0
    assert payment["terms"] == "NET_30"
    assert payment["scheduled_date"] == "2026-11-10"
    assert state["ledger_entry"]["entry_id"] == "JE-INV-2041"
    assert "escalation" not in state  # investigation never ran


# -- FinOps forecasting ------------------------------------------------------


def test_forecast_empty_history_returns_zeros():
    result = forecast_spend([])
    assert result["projected_spend"] == 0.0
    assert result["daily_average"] == 0.0
    assert "no run history" in result["confidence_note"]


def test_forecast_flat_history_projects_flat():
    result = forecast_spend([1.0] * 10)
    assert result["daily_average"] == 1.0
    assert result["trend"] == "stable"
    assert result["projected_spend"] == 30.0
    assert "medium" in result["confidence_note"]


def test_forecast_growing_history_projects_growth():
    result = forecast_spend([1.0, 2.0, 3.0, 4.0, 5.0])
    assert result["trend"] == "growing"
    assert result["trend_pct_per_day"] > 0
    # Linear growth must project above the flat baseline of 3.0 * 30.
    assert result["projected_spend"] > 90.0
    assert "low" in result["confidence_note"]  # fewer than 7 points


def test_forecast_declining_history_projects_decline():
    result = forecast_spend([5.0, 4.0, 3.0, 2.0, 1.0])
    assert result["trend"] == "declining"
    assert result["projected_spend"] < 90.0
    assert result["projected_spend"] >= 0.0


def test_forecast_respects_window_and_horizon():
    # Window limits the daily average to the most recent runs.
    result = forecast_spend([100.0] * 10 + [1.0] * 3, window=3, days_ahead=10)
    assert result["daily_average"] == 1.0
    assert result["projected_spend"] <= 10.0 * 1.5  # near-flat recent trend

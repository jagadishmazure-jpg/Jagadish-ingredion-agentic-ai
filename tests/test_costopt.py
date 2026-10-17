"""Tests for cost optimization: price tables, budgets, recommendations."""

import pytest

from food_ingredients_ai.observability.costs import (
    BudgetTracker,
    CostTracker,
    recommend_optimizations,
)


def test_price_table_per_model():
    tracker = CostTracker()
    cheap = tracker.record("a", "op", 1.0, input_tokens=1000, output_tokens=1000,
                           model="demo-cheap")
    premium = tracker.record("a", "op", 1.0, input_tokens=1000, output_tokens=1000,
                             model="demo-premium")
    assert premium.cost_usd > cheap.cost_usd
    assert cheap.model == "demo-cheap"


def test_unknown_model_raises():
    tracker = CostTracker()
    with pytest.raises(KeyError):
        tracker.record("a", "op", 1.0, input_tokens=10, output_tokens=10,
                       model="nope")


def test_default_rates_unchanged():
    # Backward compat: defaults still use the original demo rates.
    tracker = CostTracker()
    r = tracker.record("a", "op", 1.0, input_tokens=1000, output_tokens=1000)
    assert r.cost_usd == pytest.approx(0.005 + 0.015)
    assert r.model == "demo-standard"


def test_budget_warning_then_breach():
    b = BudgetTracker(budget_usd=1.0, warn_at=0.8)
    assert b.add(0.5) == []
    assert b.status()["state"] == "ok"
    fired = b.add(0.4)  # 0.9 -> warning
    assert [a.level for a in fired] == ["warning"]
    assert b.status()["state"] == "warning"
    fired = b.add(0.2)  # 1.1 -> breach
    assert [a.level for a in fired] == ["breached"]
    assert b.status()["pct_used"] == 110.0
    # alerts fire once per level
    assert b.add(0.1) == []


def test_budget_invalid_args():
    with pytest.raises(ValueError):
        BudgetTracker(budget_usd=0)
    with pytest.raises(ValueError):
        BudgetTracker(budget_usd=1, warn_at=1.5)


def test_recommendations_empty_history():
    assert recommend_optimizations(CostTracker()) == []


def test_recommendations_cache_responses():
    tracker = CostTracker()
    for _ in range(3):
        tracker.record("a", "op", 1.0, input_tokens=100, output_tokens=2000)
    codes = {r.code for r in recommend_optimizations(tracker)}
    assert "CACHE_RESPONSES" in codes


def test_recommendations_downshift_model():
    tracker = CostTracker()
    tracker.record("a", "op", 1.0, input_tokens=50, output_tokens=50,
                   model="demo-cheap")
    tracker.record("a", "op", 1.0, input_tokens=50, output_tokens=50,
                   model="demo-premium")
    codes = {r.code for r in recommend_optimizations(tracker)}
    assert "DOWNSHIFT_MODEL" in codes


def test_recommendations_cache_rag():
    tracker = CostTracker()
    for _ in range(3):
        tracker.record("a", "rag_lookup", 1.0, input_tokens=200, output_tokens=200)
    codes = {r.code for r in recommend_optimizations(tracker)}
    assert "CACHE_RAG" in codes


def test_recommendations_batch_small_ops():
    tracker = CostTracker()
    for _ in range(5):
        tracker.record("a", "op", 1.0, input_tokens=10, output_tokens=10)
    codes = {r.code for r in recommend_optimizations(tracker)}
    assert "BATCH_SMALL_OPS" in codes


def test_recommendation_shape():
    tracker = CostTracker()
    tracker.record("a", "op", 1.0, input_tokens=100, output_tokens=2000)
    rec = recommend_optimizations(tracker)[0]
    d = rec.to_dict()
    assert {"code", "message", "estimated_saving_pct"} <= set(d)

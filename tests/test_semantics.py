"""Tests for the semantic metric layer: registry, lineage, explainer,
agent tools, and the metric-insight graph. All deterministic, offline."""

from __future__ import annotations

import pytest

from food_ingredients_ai.core.tools import ToolRegistry
from food_ingredients_ai.graph.metric_insight_graph import run_metric_insight_graph
from food_ingredients_ai.semantics.agent_tools import (
    DEMO_PERIOD_DATA,
    build_semantic_tools,
    register_semantic_tools,
)
from food_ingredients_ai.semantics.explainer import explain_change, summarize
from food_ingredients_ai.semantics.lineage import explain_lineage
from food_ingredients_ai.semantics.metrics import MetricDefinition
from food_ingredients_ai.semantics.registry import MetricRegistry, default_metric_registry


def _reg() -> MetricRegistry:
    return default_metric_registry()


# -- registry ---------------------------------------------------------------


def test_default_registry_has_six_metrics():
    reg = _reg()
    assert len(reg.list()) == 6
    for name in (
        "gross_margin_pct",
        "revenue",
        "cogs",
        "clean_label_share_pct",
        "otif_pct",
        "carbon_intensity_kg_per_tonne",
    ):
        assert name in reg.list()


def test_registry_get_latest_version_by_default():
    reg = MetricRegistry()
    m = _reg().get("revenue")
    reg.register(m)
    v2 = MetricDefinition(
        name="revenue",
        description="v2",
        unit="USD",
        formula="revenue = demand_tonnes * price_per_tonne",
        inputs=["demand_tonnes", "price_per_tonne"],
        owner="Finance",
        version="v2",
    )
    reg.register(v2)
    assert reg.get("revenue").version == "v2"
    assert reg.get("revenue", "v1").version == "v1"
    assert reg.versions("revenue") == ["v1", "v2"]


def test_registry_duplicate_name_version_guard():
    reg = _reg()
    dup = reg.get("revenue")
    with pytest.raises(ValueError, match="already registered"):
        reg.register(dup)


def test_registry_unknown_metric_raises():
    with pytest.raises(KeyError, match="unknown metric"):
        _reg().get("ebitda")


def test_find_by_text_resolves_aliases():
    reg = _reg()
    assert reg.find_by_text("why did gross margin drop?").name == "gross_margin_pct"
    assert reg.find_by_text("carbon intensity rose").name == "carbon_intensity_kg_per_tonne"
    assert reg.find_by_text("OTIF performance").name == "otif_pct"
    assert reg.find_by_text("something about unicorns") is None


def test_metric_evaluate_missing_input_raises():
    metric = _reg().get("revenue")
    with pytest.raises(KeyError, match="missing inputs"):
        metric.evaluate({"demand_tonnes": 1.0})


# -- lineage ----------------------------------------------------------------


def test_lineage_chain_has_three_levels():
    chain = explain_lineage("gross_margin_pct", _reg())["chain"]
    assert [c["level"] for c in chain] == [
        "metric",
        "base_measures",
        "upstream_datasets",
    ]


def test_lineage_lists_inputs_and_datasets():
    out = explain_lineage("gross_margin_pct", _reg())
    assert out["chain"][1]["names"] == ["revenue", "cogs"]
    datasets = [e["dataset"] for e in out["chain"][2]["entries"]]
    assert datasets == ["demand", "formulas", "ingredients"]


def test_lineage_citation_is_auditable():
    out = explain_lineage("carbon_intensity_kg_per_tonne", _reg())
    assert "carbon_intensity_kg_per_tonne@v1" in out["citation"]
    assert "esg_readings" in out["citation"]


def test_lineage_pins_dataset_versions_when_given():
    out = explain_lineage(
        "otif_pct", _reg(), dataset_versions={"demand": "v9"}
    )
    entries = out["chain"][2]["entries"]
    assert entries[0]["version"] == "v9"


# -- explainer --------------------------------------------------------------


def test_explainer_margin_attribution_sums_to_delta():
    reg = _reg()
    metric = reg.get("gross_margin_pct")
    data = DEMO_PERIOD_DATA["gross_margin_pct"]
    out = explain_change(metric, data["Q2"], data["Q3"], label_a="Q2", label_b="Q3")
    assert out["value_a"] == pytest.approx(35.0)
    assert out["value_b"] == pytest.approx(30.0)
    assert out["delta"] == pytest.approx(-5.0)
    total = sum(d["contribution"] for d in out["drivers"])
    assert total == pytest.approx(out["delta"], abs=1e-6)
    assert abs(out["residual"]) < 1e-6


def test_explainer_identifies_cost_driver():
    reg = _reg()
    metric = reg.get("gross_margin_pct")
    data = DEMO_PERIOD_DATA["gross_margin_pct"]
    out = explain_change(metric, data["Q2"], data["Q3"])
    by_driver = {d["driver"]: d for d in out["drivers"]}
    assert by_driver["cogs"]["direction"] == "down"
    assert by_driver["cogs"]["contribution"] < 0
    assert by_driver["revenue"]["direction"] == "up"


def test_explainer_flat_data_yields_empty_drivers():
    reg = _reg()
    metric = reg.get("otif_pct")
    flat = {"on_time_full_orders": 900.0, "total_orders": 1000.0}
    out = explain_change(metric, flat, dict(flat))
    assert out["delta"] == pytest.approx(0.0)
    assert out["drivers"] == []
    assert "No change" in out["confidence_note"]


def test_explainer_carbon_intensity_uses_demo_shape():
    reg = _reg()
    metric = reg.get("carbon_intensity_kg_per_tonne")
    data = DEMO_PERIOD_DATA["carbon_intensity_kg_per_tonne"]
    out = explain_change(metric, data["Q2"], data["Q3"])
    # 85*1000/500 = 170 ; 92*1000/520 ≈ 176.92
    assert out["value_a"] == pytest.approx(170.0)
    assert out["value_b"] == pytest.approx(176.923, abs=0.01)
    assert len(out["drivers"]) == 2


def test_explainer_drivers_cite_lineage():
    reg = _reg()
    metric = reg.get("revenue")
    data = DEMO_PERIOD_DATA["revenue"]
    out = explain_change(metric, data["Q2"], data["Q3"])
    for d in out["drivers"]:
        assert "revenue@v1" in d["cites"]


def test_summarize_mentions_drivers_and_flat_case():
    reg = _reg()
    metric = reg.get("cogs")
    data = DEMO_PERIOD_DATA["cogs"]
    text = summarize(explain_change(metric, data["Q2"], data["Q3"]))
    assert "cogs" in text
    assert "ingredient_cost_per_tonne" in text
    flat = {"ingredient_cost_per_tonne": 1.0, "production_tonnes": 1.0}
    flat_text = summarize(explain_change(metric, flat, dict(flat)))
    assert "flat" in flat_text


# -- agent tools ------------------------------------------------------------


def test_semantic_tools_register_and_list():
    tools = build_semantic_tools()
    assert sorted(t.name for t in tools) == [
        "define_metric",
        "explain_metric_change",
        "get_metric_definition",
        "list_metrics",
    ]
    out = [t for t in tools if t.name == "list_metrics"][0].call()
    assert len(out["metrics"]) == 6


def test_tool_get_metric_definition():
    tools = {t.name: t for t in build_semantic_tools()}
    out = tools["get_metric_definition"].call(name="otif_pct", version="")
    assert out["owner"] == "Supply Chain"
    assert "on_time_full_orders" in out["inputs"]


def test_tool_explain_metric_change_returns_cited_attribution():
    tools = {t.name: t for t in build_semantic_tools()}
    out = tools["explain_metric_change"].call(
        metric_name="gross_margin_pct", period_a="Q2", period_b="Q3"
    )
    assert out["delta"] == pytest.approx(-5.0)
    assert "lineage" in out
    assert "summary" in out
    assert "gross_margin_pct@v1" in out["lineage"]["citation"]


def test_tool_define_metric_registers_new_metric():
    tools = {t.name: t for t in build_semantic_tools()}
    out = tools["define_metric"].call(
        name="demo_nps",
        description="demo net promoter score",
        unit="points",
        formula="demo_nps = promoters - detractors",
        inputs=["promoters", "detractors"],
        owner="CX",
        upstream_datasets=["demand"],
    )
    assert out["registered"]["name"] == "demo_nps"
    fetched = tools["get_metric_definition"].call(name="demo_nps", version="")
    assert fetched["owner"] == "CX"


def test_register_semantic_tools_on_tool_registry():
    tr = ToolRegistry()
    register_semantic_tools(tr)
    assert "explain_metric_change" in tr.names()
    out = tr.call("list_metrics")
    assert len(out["metrics"]) == 6


# -- graph ------------------------------------------------------------------


def test_graph_answers_margin_question():
    state = run_metric_insight_graph("why did gross margin drop in Q3?")
    assert state["outcome"] == "answered"
    assert state["metric_found"] is True
    assert "gross_margin_pct" in state["answer"]
    assert "-5.0" in state["answer"]
    assert any("cogs" in c for c in state["citations"])


def test_graph_carbon_question():
    state = run_metric_insight_graph("why did carbon intensity rise?")
    assert state["outcome"] == "answered"
    assert state["metric_name"] == "carbon_intensity_kg_per_tonne"


def test_graph_unknown_metric_suggests():
    state = run_metric_insight_graph("why did unicorn sparkle index fall?")
    assert state["outcome"] == "metric_not_found"
    assert state["metric_found"] is False
    assert "gross_margin_pct" in state["suggestions"]
    assert len(state["suggestions"]) == 6


def test_graph_attribution_values_match_explainer():
    state = run_metric_insight_graph("why did revenue change?")
    attribution = state["attribution"]
    assert attribution["delta"] == pytest.approx(120_000.0)
    assert attribution["lineage"]["metric"] == "revenue"

"""Tests for the customer advisor agent (all offline, deterministic)."""

import pytest

from ingredion_ai.agents.customer_advisor import CustomerAdvisorAgent
from ingredion_ai.agents.customer_advisor import claims, formulation, pricing, recommender, tech_sheet
from ingredion_ai.data.loader import get_formula


def _agent():
    return CustomerAdvisorAgent()


def test_recommend_clean_label_excludes_flagged():
    recs = recommender.recommend(category="sweetener", claims=("clean_label",))
    ids = {r["id"] for r in recs}
    assert "HFCS-42" not in ids
    assert "FS-40" in ids


def test_recommend_natural_excludes_refined_sugar():
    recs = recommender.recommend(category="sweetener", claims=("natural",))
    assert "RCS-01" not in {r["id"] for r in recs}


def test_recommend_region_filter():
    recs = recommender.recommend(category="color", region="EU")
    assert "R40" not in {r["id"] for r in recs}
    assert "BC-12" in {r["id"] for r in recs}


def test_recommend_sorted_by_cost():
    recs = recommender.recommend()
    costs = [r["cost_index"] for r in recs]
    assert costs == sorted(costs)


def test_recommend_max_results():
    assert len(recommender.recommend(max_results=3)) == 3


def test_sample_formula_sums_to_100():
    formula = formulation.generate_sample_formula(["WF-01", "HO-30", "RCS-01", "BS-01"])
    total = sum(i["pct"] for i in formula["ingredients"])
    assert abs(total - 100.0) < 0.01
    assert formula["demo"] is True


def test_sample_formula_empty_raises():
    with pytest.raises(ValueError):
        formulation.generate_sample_formula([])


def test_sample_formula_duplicate_function_raises():
    with pytest.raises(ValueError):
        formulation.generate_sample_formula(["WF-01", "HB-10"])


def test_sample_formula_unknown_id_raises():
    with pytest.raises(KeyError):
        formulation.generate_sample_formula(["NOPE"])


def test_claims_delegates_to_regulatory():
    formula = get_formula("gluten_free_bread")
    results = claims.validate(formula, ["natural"])
    assert results[0]["valid"] is True


def test_pricing_positive_and_ordered():
    formula = get_formula("gluten_free_bread")
    out = pricing.estimate_pricing(formula, ["natural"])
    assert out["cost_per_kg_usd"] > 0
    assert out["price_high_usd"] >= out["price_low_usd"]
    assert out["uplift_pct"] == 10.0


def test_pricing_no_claims_no_uplift():
    formula = get_formula("gluten_free_bread")
    out = pricing.estimate_pricing(formula, [])
    assert out["uplift_pct"] == 0.0
    assert out["price_high_usd"] == out["price_low_usd"]


def test_tech_sheet_contents():
    formula = get_formula("gluten_free_bread")
    claim_results = claims.validate(formula, ["natural"])
    price = pricing.estimate_pricing(formula, ["natural"])
    sheet = tech_sheet.generate_customer_tech_sheet(formula, claim_results, price)
    assert "# Customer Technical Sheet" in sheet
    assert "natural" in sheet
    assert "$" in sheet


def test_agent_recommend_task():
    out = _agent().execute("recommend_ingredients", {"category": "protein"})
    assert len(out["recommendations"]) > 0


def test_agent_sample_formula_task():
    out = _agent().execute(
        "generate_sample_formula", {"ingredient_ids": ["WF-01", "HO-30"]}
    )
    assert out["sample_formula"]["demo"] is True


def test_agent_estimate_pricing_needs_formula():
    with pytest.raises(ValueError):
        _agent().execute("estimate_pricing", {"valid_claims": []})


def test_agent_tech_sheet_task():
    formula = get_formula("gluten_free_bread")
    out = _agent().execute(
        "generate_tech_sheet",
        {"formula": formula, "claims": [], "pricing": pricing.estimate_pricing(formula, [])},
    )
    assert "# Customer Technical Sheet" in out["tech_sheet_markdown"]


def test_agent_unknown_task_raises():
    with pytest.raises(ValueError):
        _agent().execute("nope", {})

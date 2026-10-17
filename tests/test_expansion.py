"""Tests for the Part A expansion: new data, demo-assumption heuristics."""

from food_ingredients_ai.agents.customer_advisor import pricing
from food_ingredients_ai.agents.rd_formulation import (
    analyzer,
    cycle_time,
    predictor,
    regulatory,
    substitution,
)
from food_ingredients_ai.data.loader import get_formula, load_formulas, load_ingredients

NEW_INGREDIENT_IDS = {
    "AB-66", "AO-67", "BHA-68", "YS-58", "CAF-71",
    "SPS-72", "RCE-76", "MNK-77", "PEP-74", "CB-79",
}
NEW_FORMULA_IDS = {
    "savory_bakery_crackers",
    "cola_soft_drink",
    "energy_drink",
    "flavored_water",
    "nutritional_shake",
}


def test_new_ingredients_present():
    ids = {i["id"] for i in load_ingredients()}
    assert NEW_INGREDIENT_IDS <= ids


def test_new_formulas_present():
    ids = {f["id"] for f in load_formulas()}
    assert NEW_FORMULA_IDS <= ids


def test_new_formulas_cover_bakery_and_beverage():
    cats = {f["id"]: f["category"] for f in load_formulas()}
    assert cats["savory_bakery_crackers"] == "bakery"
    assert cats["cola_soft_drink"] == "beverage"
    assert cats["energy_drink"] == "beverage"
    assert cats["flavored_water"] == "beverage"
    assert cats["nutritional_shake"] == "beverage"


def test_analyzer_flags_new_injection_markers():
    formula = get_formula("cola_soft_drink")
    out = analyzer.analyze_formula(formula)
    flagged_ids = {f["ingredient_id"] for f in out["flagged"]}
    # cola contains a synthetic color + preservative equivalents (demo)
    assert len(flagged_ids) >= 1


def _cands():
    return [
        {"id": "X", "cost_index": 3.0, "texture_impact": 0.1},
        {"id": "Y", "cost_index": 1.0, "texture_impact": 0.5},
        {"id": "Z", "cost_index": 2.0, "texture_impact": 0.2},
    ]


def test_substitution_cost_aware_ranking_cheapest_first():
    ranked = substitution.rank_cost_aware(_cands())
    assert [c["id"] for c in ranked] == ["Y", "Z", "X"]


def test_substitution_cost_aware_does_not_mutate_input():
    cands = _cands()
    substitution.rank_cost_aware(cands)
    assert [c["id"] for c in cands] == ["X", "Y", "Z"]


def test_substitution_cost_aware_breaks_ties_on_texture():
    cands = [
        {"id": "A", "cost_index": 1.0, "texture_impact": 0.9},
        {"id": "B", "cost_index": 1.0, "texture_impact": 0.1},
    ]
    ranked = substitution.rank_cost_aware(cands)
    assert [c["id"] for c in ranked] == ["B", "A"]


def test_claim_hierarchy_natural_first():
    assert regulatory.CLAIM_PRIORITY[0] == "natural"
    ordered = regulatory.prioritize_claims(
        ["reduced sugar", "natural", "no artificial ingredients"]
    )
    assert ordered[0] == "natural"


def test_prioritize_claims_unknown_claim_last():
    ordered = regulatory.prioritize_claims(["mystery claim", "natural"])
    assert ordered[-1] == "mystery claim"


def _prediction_with_impact():
    return {"substitutions_evaluated": 2, "texture_match_pct": 92.2}


def test_bakery_stability_advisory_fires_for_bakery():
    formula = get_formula("savory_bakery_crackers")
    notes = predictor.bakery_stability_advisory(formula, _prediction_with_impact())
    assert len(notes) == 1
    assert "bakery" in notes[0].lower()


def test_bakery_stability_advisory_quiet_for_beverage():
    formula = get_formula("cola_soft_drink")
    notes = predictor.bakery_stability_advisory(formula, _prediction_with_impact())
    assert notes == []


def test_bakery_stability_advisory_empty_without_substitutions():
    formula = get_formula("savory_bakery_crackers")
    notes = predictor.bakery_stability_advisory(
        formula, {"substitutions_evaluated": 0, "texture_match_pct": 92.2}
    )
    assert notes == []


def test_wtp_band_labels():
    assert pricing.wtp_band(16.0) == "premium-plus"
    assert pricing.wtp_band(10.0) == "premium"  # 10%+ premium for valued claims
    assert pricing.wtp_band(7.0) == "value-plus"
    assert pricing.wtp_band(0.0) == "standard"


def test_pricing_includes_wtp_keys():
    formula = get_formula("sweet_bakery_cake")
    out = pricing.estimate_pricing(formula, ["natural"])
    assert "wtp_band" in out
    assert "wtp_rationale" in out
    assert out["wtp_band"] == "premium"  # natural -> 10% uplift


def test_cycle_time_estimate_shape():
    formula = get_formula("sweet_bakery_cake")
    out = cycle_time.estimate_cycle_time(
        formula,
        [{"action": "substitute"}, {"action": "remove"}],
        {"risk_flags": ["x"]},
    )
    assert "estimated_weeks" in out and "estimated_months" in out
    assert "baseline_months" in out  # 5-7 month demo baseline
    assert out["baseline_months"] == [5.0, 7.0]
    assert out["estimated_weeks"] > 0


def test_cycle_time_more_substitutions_takes_longer():
    formula = get_formula("sweet_bakery_cake")
    few = cycle_time.estimate_cycle_time(formula, [{"action": "substitute"}], {"risk_flags": []})
    many = cycle_time.estimate_cycle_time(
        formula, [{"action": "substitute"}] * 5, {"risk_flags": []}
    )
    assert many["estimated_weeks"] > few["estimated_weeks"]


def test_demo_scenarios_registry_covers_categories():
    from food_ingredients_ai.demo import SCENARIOS

    assert "sweet_bakery_cake" in SCENARIOS  # default unchanged
    assert "savory_bakery_crackers" in SCENARIOS
    assert "energy_drink" in SCENARIOS
    assert "flavored_water" in SCENARIOS
    assert "nutritional_shake" in SCENARIOS
    assert "cola_soft_drink" in SCENARIOS
    for name, sc in SCENARIOS.items():
        assert {"formula_id", "target_claims", "region"} <= set(sc), name

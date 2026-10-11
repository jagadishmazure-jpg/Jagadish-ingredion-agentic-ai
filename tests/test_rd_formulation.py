"""Tests for the R&D formulation agent (all offline, deterministic)."""

import pytest

from ingredion_ai.agents.rd_formulation import RDFormulationAgent
from ingredion_ai.agents.rd_formulation import analyzer, nutrition, predictor, regulatory, substitution
from ingredion_ai.agents.rd_formulation.documentation import (
    generate_formulation_spec,
    generate_technical_sheet,
)
from ingredion_ai.data.loader import get_formula

CAKE = "sweet_bakery_cake"
CONTEXT = {
    "formula_id": CAKE,
    "target_claims": ["no artificial ingredients", "reduced sugar", "natural"],
    "region": "NA",
    "adjustments": {"RCS-01": 14.0},
    "additions": {"SL-95": 0.3},
}


def _agent():
    return RDFormulationAgent()


def _full_blackboard():
    agent = _agent()
    bb = {}
    for task_name in (
        "analyze_ingredients",
        "suggest_substitutes",
        "predict_texture_shelf_life",
        "calculate_nutrition",
        "validate_claims",
    ):
        out = agent.execute(task_name, {**CONTEXT, "blackboard": bb})
        bb[task_name] = out
    return agent, bb


def test_analyzer_flags_seven_in_cake():
    analysis = analyzer.analyze_formula(get_formula(CAKE))
    assert analysis["flagged_count"] == 7
    assert not analysis["clean"]
    ids = {f["ingredient_id"] for f in analysis["flagged"]}
    assert ids == {"MCS-10", "HFCS-42", "AV-01", "TD-99", "R40", "SBZ", "P60"}


def test_analyzer_clean_formula():
    analysis = analyzer.analyze_formula(get_formula("gluten_free_bread"))
    assert analysis["clean"] and analysis["flagged_count"] == 0


def test_analyzer_reasons_nonempty():
    for f in analyzer.analyze_formula(get_formula(CAKE))["flagged"]:
        assert f["reasons"]


def test_substitution_counts():
    analysis = analyzer.analyze_formula(get_formula(CAKE))
    subs = substitution.suggest_substitutes(analysis["flagged"])
    assert len(subs) == 7
    actions = [s["action"] for s in subs]
    assert actions.count("substitute") == 6
    assert actions.count("remove") == 1


def test_substitution_removes_titanium_dioxide():
    analysis = analyzer.analyze_formula(get_formula(CAKE))
    subs = substitution.suggest_substitutes(analysis["flagged"])
    td = next(s for s in subs if s["old_id"] == "TD-99")
    assert td["action"] == "remove" and td["new_id"] is None


def test_substitution_uses_demo_mapping():
    analysis = analyzer.analyze_formula(get_formula(CAKE))
    subs = {s["old_id"]: s["new_id"] for s in substitution.suggest_substitutes(analysis["flagged"])}
    assert subs["MCS-10"] == "PF-200"
    assert subs["AV-01"] == "NV-60"
    assert subs["SBZ"] == "CD-55"


def test_apply_substitutions_sums_to_100():
    formula = get_formula(CAKE)
    analysis = analyzer.analyze_formula(formula)
    subs = substitution.suggest_substitutes(analysis["flagged"])
    new_formula = substitution.apply_substitutions(
        formula, subs, adjustments={"RCS-01": 14.0}, additions={"SL-95": 0.3}
    )
    total = sum(i["pct"] for i in new_formula["ingredients"])
    assert abs(total - 100.0) < 0.01
    assert new_formula["id"].endswith("__clean_label")


def test_apply_substitutions_applies_adjustments():
    formula = get_formula(CAKE)
    analysis = analyzer.analyze_formula(formula)
    subs = substitution.suggest_substitutes(analysis["flagged"])
    new_formula = substitution.apply_substitutions(
        formula, subs, adjustments={"RCS-01": 14.0}, additions={"SL-95": 0.3}
    )
    by_id = {i["id"]: i["pct"] for i in new_formula["ingredients"]}
    assert by_id["RCS-01"] == 14.0
    assert by_id["SL-95"] == 0.3
    assert "TD-99" not in by_id and "PF-200" in by_id


def test_predictor_demo_values():
    formula = get_formula(CAKE)
    analysis = analyzer.analyze_formula(formula)
    subs = substitution.suggest_substitutes(analysis["flagged"])
    pred = predictor.predict(formula, subs)
    assert pred["texture_match_pct"] == 92.2
    assert pred["shelf_life_days"] == 8.2
    assert pred["risk_flags"] == []


def test_predictor_no_substitutions_is_perfect():
    pred = predictor.predict(get_formula(CAKE), [])
    assert pred["texture_match_pct"] == 100.0
    assert pred["shelf_life_days"] == 9.5


def test_predictor_flags_risks_on_heavy_impact():
    formula = get_formula(CAKE)
    subs = [
        {"action": "substitute", "new_id": "VP-80"},
        {"action": "substitute", "new_id": "VP-80"},
        {"action": "substitute", "new_id": "VP-80"},
        {"action": "substitute", "new_id": "VP-80"},
        {"action": "substitute", "new_id": "VP-80"},
        {"action": "substitute", "new_id": "VP-80"},
        {"action": "substitute", "new_id": "VP-80"},
        {"action": "substitute", "new_id": "VP-80"},
    ]
    pred = predictor.predict(formula, subs)
    assert pred["texture_match_pct"] < 85.0
    assert any("texture" in r for r in pred["risk_flags"])


def test_nutrition_original_sugar():
    panel = nutrition.calculate_nutrition(get_formula(CAKE))
    assert panel["per_100g"]["sugar_g"] == 31.44


def test_nutrition_reformulated_sugar_lower():
    formula = get_formula(CAKE)
    analysis = analyzer.analyze_formula(formula)
    subs = substitution.suggest_substitutes(analysis["flagged"])
    new_formula = substitution.apply_substitutions(
        formula, subs, adjustments={"RCS-01": 14.0}, additions={"SL-95": 0.3}
    )
    panel = nutrition.calculate_nutrition(new_formula)
    assert panel["per_100g"]["sugar_g"] == 20.25


def test_claim_no_artificial_valid_after_reformulation():
    agent, bb = _full_blackboard()
    claims = {c["claim"]: c["valid"] for c in bb["validate_claims"]["claims"]}
    assert claims["no artificial ingredients"] is True


def test_claim_reduced_sugar_valid():
    agent, bb = _full_blackboard()
    claims = {c["claim"]: c["valid"] for c in bb["validate_claims"]["claims"]}
    assert claims["reduced sugar"] is True


def test_claim_natural_rejected_with_refined_sugar():
    """The checker must reject 'natural' while refined sugar remains."""
    agent, bb = _full_blackboard()
    claim = next(
        c for c in bb["validate_claims"]["claims"] if c["claim"] == "natural"
    )
    assert claim["valid"] is False
    assert any("RCS-01" in r or "RefinedCaneSugar" in r for r in claim["reasons"])


def test_claim_natural_valid_for_clean_formula():
    results = regulatory.validate_claims(
        get_formula("gluten_free_bread"), ["natural"], region="NA"
    )
    assert results[0]["valid"] is True


def test_claim_reduced_sugar_rejected_when_small_cut():
    formula = get_formula(CAKE)
    panel = nutrition.calculate_nutrition(formula)
    results = regulatory.validate_claims(
        formula,
        ["reduced sugar"],
        baseline_sugar_g=panel["per_100g"]["sugar_g"] * 1.05,
    )
    assert results[0]["valid"] is False


def test_claim_reduced_sugar_needs_baseline():
    results = regulatory.validate_claims(get_formula(CAKE), ["reduced sugar"])
    assert results[0]["valid"] is False


def test_claim_high_protein_rejected_for_bread():
    results = regulatory.validate_claims(
        get_formula("gluten_free_bread"), ["high protein"]
    )
    assert results[0]["valid"] is False


def test_claim_unknown_rejected():
    results = regulatory.validate_claims(get_formula(CAKE), ["keto"])
    assert results[0]["valid"] is False
    assert "unknown claim" in results[0]["reasons"][0]


def test_claim_eu_color_rule():
    formula = get_formula(CAKE)
    results = regulatory.validate_claims(formula, ["natural"], region="EU")
    assert results[0]["valid"] is False


def test_agent_unknown_task_raises():
    with pytest.raises(ValueError):
        _agent().execute("teleport", {"formula_id": CAKE})


def test_agent_run_wraps_errors():
    from ingredion_ai.core.types import Task

    agent = _agent()
    result = agent.run(Task("analyze_ingredients", "rd_formulation"), {})
    assert not result.success  # missing formula_id -> KeyError wrapped


def test_documentation_spec_sections():
    agent, bb = _full_blackboard()
    out = agent.execute("generate_documentation", {**CONTEXT, "blackboard": bb})
    spec = out["spec_markdown"]
    assert "# Formulation Specification" in spec
    assert "Substitutions Applied" in spec
    assert "Claim Validation" in spec
    assert "PureField Starch PF-200" in spec


def test_documentation_tech_sheet():
    agent, bb = _full_blackboard()
    out = agent.execute("generate_documentation", {**CONTEXT, "blackboard": bb})
    sheet = out["tech_sheet_markdown"]
    assert "# Customer Technical Sheet" in sheet
    assert "no artificial ingredients" in sheet


def test_tools_registered():
    agent = _agent()
    for name in (
        "analyze_ingredients",
        "suggest_substitutes",
        "predict_texture_shelf_life",
        "calculate_nutrition",
        "validate_claims",
    ):
        assert name in agent.tools.names()

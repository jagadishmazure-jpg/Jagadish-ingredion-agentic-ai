"""Tests for the end-to-end demo and its regression eval."""

import io
from contextlib import redirect_stdout

import yaml

from ingredion_ai.agents import (
    CustomerAdvisorAgent,
    ESGAgent,
    RDFormulationAgent,
    SupplyChainAgent,
)
from ingredion_ai.core.planner import Orchestrator
from ingredion_ai.demo import FORMULA_ID, REGION, TARGET_CLAIMS, build_orchestrator, main


def _run_demo() -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        main()
    return buf.getvalue()


def test_demo_runs_and_completes():
    output = _run_demo()
    assert "DEMO COMPLETE" in output
    assert "not affiliated with ingredion" in output.lower()


def test_demo_is_deterministic():
    assert _run_demo() == _run_demo()


def test_demo_covers_all_steps():
    output = _run_demo()
    for step in (
        "STEP 1",
        "STEP 2",
        "STEP 3",
        "STEP 4",
        "STEP 5",
        "STEP 6",
        "Supply Chain",
        "ESG Agent",
        "Customer Advisor",
    ):
        assert step in output


def test_demo_reports_key_numbers():
    output = _run_demo()
    assert "92.2%" in output
    assert "8.2 days" in output


def test_orchestrator_reformulate_completes():
    state = build_orchestrator().run(
        "reformulate",
        {
            "formula_id": FORMULA_ID,
            "target_claims": TARGET_CLAIMS,
            "region": REGION,
            "adjustments": {"RCS-01": 14.0},
            "additions": {"SL-95": 0.3},
        },
    )
    assert state.status == "complete"
    assert len(state.results) == 6
    assert all(r.success for r in state.results.values())


def test_orchestrator_full_launch_completes():
    orch = Orchestrator(
        {
            "rd_formulation": RDFormulationAgent(),
            "supply_chain": SupplyChainAgent(),
            "esg": ESGAgent(),
            "customer_advisor": CustomerAdvisorAgent(),
        }
    )
    state = orch.run(
        "new product launch",
        {
            "formula_id": FORMULA_ID,
            "target_claims": TARGET_CLAIMS,
            "region": REGION,
            "adjustments": {"RCS-01": 14.0},
            "additions": {"SL-95": 0.3},
            "skus": ["PF-200"],
            "periods": 2,
            "inventory": {"PF-200": {"on_hand_tonnes": 1.0}},
        },
    )
    assert state.status == "complete"
    assert len(state.results) == 11


def test_regression_eval_matches_pipeline():
    with open("evals/regression_demo.yaml", encoding="utf-8") as fh:
        expected = yaml.safe_load(fh)["expected"]
    state = build_orchestrator().run(
        "reformulate",
        {
            "formula_id": FORMULA_ID,
            "target_claims": TARGET_CLAIMS,
            "region": REGION,
            "adjustments": {"RCS-01": 14.0},
            "additions": {"SL-95": 0.3},
        },
    )
    out = state.results
    assert out["analyze_ingredients"].output["flagged_count"] == expected["flagged_count"]
    subs = out["suggest_substitutes"].output
    assert subs["substituted_count"] == expected["substituted_count"]
    assert subs["removed_count"] == expected["removed_count"]
    pred = out["predict_texture_shelf_life"].output["prediction"]
    assert pred["texture_match_pct"] == expected["texture_match_pct"]
    assert pred["shelf_life_days"] == expected["shelf_life_days"]
    claims = {c["claim"]: c["valid"] for c in out["validate_claims"].output["claims"]}
    assert claims == expected["claims"]

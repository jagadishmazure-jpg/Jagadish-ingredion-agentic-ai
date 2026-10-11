"""End-to-end demo: clean-label reformulation of a sweet bakery cake.

Run with ``python -m ingredion_ai.demo``. Fully offline and deterministic —
an interview-ready narrative of the multi-agent workflow.
"""

from __future__ import annotations

from ingredion_ai.agents import (
    CustomerAdvisorAgent,
    ESGAgent,
    RDFormulationAgent,
    SupplyChainAgent,
)
from ingredion_ai.core.planner import Orchestrator
from ingredion_ai.data.loader import get_formula

FORMULA_ID = "sweet_bakery_cake"
TARGET_CLAIMS = ["no artificial ingredients", "reduced sugar", "natural"]
REGION = "NA"


def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def build_orchestrator() -> Orchestrator:
    return Orchestrator(
        {
            "rd_formulation": RDFormulationAgent(),
            "supply_chain": SupplyChainAgent(),
            "esg": ESGAgent(),
            "customer_advisor": CustomerAdvisorAgent(),
        }
    )


def main() -> None:
    print("INGREDION-INSPIRED CLEAN-LABEL REFORMULATION  (portfolio demo)")
    print("-" * 70)
    print("Independent demo project. All ingredients, formulas, readings and")
    print("numbers are SYNTHETIC and fictional. Not affiliated with Ingredion.")
    print("-" * 70)

    formula = get_formula(FORMULA_ID)
    print(f"\nScenario: reformulate '{formula['name']}' to clean label.")
    print(f"Target claims: {', '.join(TARGET_CLAIMS)} | Region: {REGION}")
    print("Constraints: cost-aware, shelf-life >= 7 days (demo targets).")

    orchestrator = build_orchestrator()
    state = orchestrator.run(
        "reformulate",
        {
            "formula_id": FORMULA_ID,
            "target_claims": TARGET_CLAIMS,
            "region": REGION,
            # demo reformulation levers: cut refined sugar, add stevia leaf
            "adjustments": {"RCS-01": 14.0},
            "additions": {"SL-95": 0.3},
        },
    )
    assert state.status == "complete", f"orchestration failed: {state.status}"

    analysis = state.results["analyze_ingredients"].output
    section("STEP 1 — Ingredient Analysis Agent")
    print(f"Flagged {analysis['flagged_count']} non-clean-label ingredients:")
    for f in analysis["flagged"]:
        print(f"  - {f['name']} ({f['pct']}%): {'; '.join(f['reasons'])}")

    subs = state.results["suggest_substitutes"].output
    section("STEP 2 — Substitution Agent (demo ingredient DB)")
    for s in subs["substitutions"]:
        if s["action"] == "remove":
            print(f"  - REMOVED {s['old_name']}: {s['reason']}")
        else:
            print(f"  - {s['old_name']} -> {s['new_name']}: {s['reason']}")
    print(
        f"Substituted: {subs['substituted_count']}, removed: {subs['removed_count']}."
    )

    prediction = state.results["predict_texture_shelf_life"].output["prediction"]
    section("STEP 3 — Texture & Shelf-Life Prediction Agent (demo heuristic)")
    print(f"  Texture match: {prediction['texture_match_pct']}%")
    print(f"  Shelf-life:    {prediction['shelf_life_days']} days")
    for flag in prediction["risk_flags"]:
        print(f"  RISK: {flag}")
    if not prediction["risk_flags"]:
        print("  No risk flags — within demo targets.")

    nutrition = state.results["calculate_nutrition"].output
    section("STEP 4 — Nutrition Agent (synthetic values)")
    old = nutrition["nutrition_original"]["per_100g"]
    new = nutrition["nutrition_reformulated"]["per_100g"]
    print(f"  Sugar: {old['sugar_g']}g -> {new['sugar_g']}g per 100g")

    claims = state.results["validate_claims"].output["claims"]
    section("STEP 5 — Regulatory & Claim Validation Agent (demo rules)")
    for c in claims:
        mark = "VALID" if c["valid"] else "INVALID"
        print(f"  [{mark}] {c['claim']}: {'; '.join(c['reasons'])}")

    docs = state.results["generate_documentation"].output
    section("STEP 6 — Documentation Agent")
    print("  Generated: formulation spec + customer technical sheet (markdown).")
    print("  --- spec preview ---")
    for line in docs["spec_markdown"].splitlines()[:14]:
        print("  " + line)

    # ---- supporting agents -------------------------------------------------
    section("BONUS — Supply Chain Agent (demo forecast)")
    sc = orchestrator.agents["supply_chain"]
    fc = sc.execute("forecast_demand", {"skus": ["PF-200"], "periods": 4})
    print(f"  PF-200 next-4-week forecast (tonnes): {fc['forecasts']['PF-200']['forecast']}")

    section("BONUS — ESG Agent (demo report)")
    esg = orchestrator.agents["esg"]
    readings = esg.execute("collect_esg", {})["readings"]
    carbon = esg.execute("esg_report", {"blackboard": {"collect_esg": {"readings": readings}}})
    first_lines = carbon["report_markdown"].splitlines()
    for line in first_lines[4:10]:
        print("  " + line)

    section("BONUS — Customer Advisor Agent (demo pricing)")
    ca = orchestrator.agents["customer_advisor"]
    valid_claims = [c["claim"] for c in claims if c["valid"]]
    new_formula = subs["reformulated_formula"]
    pricing = ca.execute(
        "estimate_pricing", {"formula": new_formula, "valid_claims": valid_claims}
    )["pricing"]
    print(f"  Cost: ${pricing['cost_per_kg_usd']}/kg | band: "
          f"${pricing['price_low_usd']}–${pricing['price_high_usd']}/kg "
          f"(uplift {pricing['uplift_pct']}%)")

    section("DEMO COMPLETE")
    print("Reformulation finished with full traceability across 4 specialist")
    print("agents + orchestrator. Every number above is synthetic demo data.")
    print("=" * 70)


if __name__ == "__main__":
    main()

"""End-to-end demo: clean-label reformulation of a sweet bakery cake.

Run with ``python -m food_ingredients_ai.demo`` (offline, deterministic) or
``python -m food_ingredients_ai.demo --live`` (Azure OpenAI via Microsoft Agent
Framework 1.0; needs the ``.env`` variables documented in ``.env.example``).

The demo runs the Microsoft Agent Framework 1.0 workflow: the R&D
formulation agent executes its 6-step tool phase, then fans out
concurrently to the supply-chain, ESG, and customer advisor agents. All
domain tools run the deterministic offline pipeline, so the offline run
is byte-identical every time — a consistent, repeatable narrative of the
multi-agent workflow.
"""

from __future__ import annotations

import argparse
import asyncio

from food_ingredients_ai.agents import (
    CustomerAdvisorAgent,
    ESGAgent,
    RDFormulationAgent,
    SupplyChainAgent,
)
from food_ingredients_ai.agents.rd_formulation import cycle_time
from food_ingredients_ai.core.planner import Orchestrator
from food_ingredients_ai.data.loader import get_formula
from food_ingredients_ai.framework.runner import build_demo_context, run_reformulation

FORMULA_ID = "sweet_bakery_cake"
TARGET_CLAIMS = ["no artificial ingredients", "reduced sugar", "natural"]
REGION = "NA"

# Named demo scenarios: bakery + beverage coverage beyond the default.
# The default scenario is byte-identical to previous runs (regression-pinned).
SCENARIOS = {
    "sweet_bakery_cake": {
        "formula_id": "sweet_bakery_cake",
        "target_claims": ["no artificial ingredients", "reduced sugar", "natural"],
        "region": "NA",
        "adjustments": {"RCS-01": 14.0},
        "additions": {"SL-95": 0.3},
    },
    "savory_bakery_crackers": {
        "formula_id": "savory_bakery_crackers",
        "target_claims": ["no artificial ingredients", "natural"],
        "region": "NA",
        "adjustments": {},
        "additions": {},
    },
    "cola_soft_drink": {
        "formula_id": "cola_soft_drink",
        "target_claims": ["no artificial ingredients", "reduced sugar"],
        "region": "NA",
        "adjustments": {},
        "additions": {},
    },
    "energy_drink": {
        "formula_id": "energy_drink",
        "target_claims": ["no artificial ingredients", "reduced sugar"],
        "region": "NA",
        "adjustments": {},
        "additions": {},
    },
    "flavored_water": {
        "formula_id": "flavored_water",
        "target_claims": ["no artificial ingredients", "natural"],
        "region": "NA",
        "adjustments": {},
        "additions": {},
    },
    "nutritional_shake": {
        "formula_id": "nutritional_shake",
        "target_claims": ["no artificial ingredients", "high protein"],
        "region": "NA",
        "adjustments": {},
        "additions": {},
    },
}


def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def build_orchestrator() -> Orchestrator:
    """Legacy deterministic orchestrator (kept for the regression eval)."""
    return Orchestrator(
        {
            "rd_formulation": RDFormulationAgent(),
            "supply_chain": SupplyChainAgent(),
            "esg": ESGAgent(),
            "customer_advisor": CustomerAdvisorAgent(),
        }
    )


def _print_report(bb: dict) -> None:
    analysis = bb["analyze_ingredients"]
    section("STEP 1 — Ingredient Analysis Agent")
    print(f"Flagged {analysis['flagged_count']} non-clean-label ingredients:")
    for f in analysis["flagged"]:
        print(f"  - {f['name']} ({f['pct']}%): {'; '.join(f['reasons'])}")

    subs = bb["suggest_substitutes"]
    section("STEP 2 — Substitution Agent (demo ingredient DB)")
    for s in subs["substitutions"]:
        if s["action"] == "remove":
            print(f"  - REMOVED {s['old_name']}: {s['reason']}")
        else:
            print(f"  - {s['old_name']} -> {s['new_name']}: {s['reason']}")
    print(
        f"Substituted: {subs['substituted_count']}, removed: {subs['removed_count']}."
    )

    prediction = bb["predict_texture_shelf_life"]["prediction"]
    section("STEP 3 — Texture & Shelf-Life Prediction Agent (demo heuristic)")
    print(f"  Texture match: {prediction['texture_match_pct']}%")
    print(f"  Shelf-life:    {prediction['shelf_life_days']} days")
    for flag in prediction["risk_flags"]:
        print(f"  RISK: {flag}")
    if not prediction["risk_flags"]:
        print("  No risk flags — within demo targets.")

    nutrition = bb["calculate_nutrition"]
    section("STEP 4 — Nutrition Agent (synthetic values)")
    old = nutrition["nutrition_original"]["per_100g"]
    new = nutrition["nutrition_reformulated"]["per_100g"]
    print(f"  Sugar: {old['sugar_g']}g -> {new['sugar_g']}g per 100g")

    claims = bb["validate_claims"]["claims"]
    section("STEP 5 — Regulatory & Claim Validation Agent (demo rules)")
    for c in claims:
        mark = "VALID" if c["valid"] else "INVALID"
        print(f"  [{mark}] {c['claim']}: {'; '.join(c['reasons'])}")

    docs = bb["generate_documentation"]
    section("STEP 6 — Documentation Agent")
    print("  Generated: formulation spec + customer technical sheet (markdown).")
    print("  --- spec preview ---")
    for line in docs["spec_markdown"].splitlines()[:14]:
        print("  " + line)

    # ---- supporting agents -------------------------------------------------
    section("BONUS — Supply Chain Agent (demo forecast)")
    fc = bb["forecast_demand"]
    print(f"  PF-200 next-4-week forecast (tonnes): {fc['forecasts']['PF-200']['forecast']}")

    section("BONUS — ESG Agent (demo report)")
    carbon = bb["esg_report"]
    first_lines = carbon["report_markdown"].splitlines()
    for line in first_lines[4:10]:
        print("  " + line)

    section("BONUS — Customer Advisor Agent (demo pricing)")
    pricing = bb["estimate_pricing"]["pricing"]
    print(f"  Cost: ${pricing['cost_per_kg_usd']}/kg | band: "
          f"${pricing['price_low_usd']}–${pricing['price_high_usd']}/kg "
          f"(uplift {pricing['uplift_pct']}%, WTP band: {pricing['wtp_band']})")

    section("STEP 7 — Cycle-Time Estimate Agent (demo heuristic)")
    ct = cycle_time.estimate_cycle_time(
        get_formula(bb["analyze_ingredients"]["formula_id"]),
        bb["suggest_substitutes"]["substitutions"],
        bb["predict_texture_shelf_life"]["prediction"],
    )
    print(f"  Estimated agentic cycle time: {ct['estimated_weeks']} weeks "
          f"({ct['estimated_months']} months)")
    print(f"  Baseline (public research): {ct['baseline_months'][0]}-"
          f"{ct['baseline_months'][1]} months "
          f"-> reduction {ct['reduction_pct']}% (demo)")

    section("DEMO COMPLETE")
    print("Reformulation finished with full traceability across 4 framework")
    print("agents + WorkflowBuilder workflow. Every number above is synthetic demo data.")
    print("=" * 70)


def main(argv: list | None = None) -> None:
    parser = argparse.ArgumentParser(description="Food-ingredients reformulation demo")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use Azure OpenAI via Microsoft Agent Framework (needs .env).",
    )
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        default="sweet_bakery_cake",
        help="Demo scenario to run (default: sweet_bakery_cake).",
    )
    parser.add_argument(
        "--audit-log",
        default=None,
        metavar="PATH",
        help="Write a governance audit trail (JSONL) of the demo run to PATH.",
    )
    # NB: default to [] (not sys.argv) so test runners' argv never leaks in;
    # the __main__ block below passes sys.argv[1:] explicitly.
    args = parser.parse_args([] if argv is None else argv)

    scenario = SCENARIOS[args.scenario]
    formula_id = scenario["formula_id"]
    target_claims = scenario["target_claims"]
    region = scenario["region"]

    print("FOOD-INGREDIENTS CLEAN-LABEL REFORMULATION  (portfolio demo)")
    print("-" * 70)
    print("Independent demo project. All ingredients, formulas, readings and")
    print("numbers are SYNTHETIC and fictional. Not affiliated with any real company.")
    print("-" * 70)
    if args.live:
        print("Mode: LIVE (Azure OpenAI + Microsoft Agent Framework 1.0)")
    else:
        print("Mode: OFFLINE (scripted fake client, deterministic)")
    print(f"Scenario: {args.scenario}")

    formula = get_formula(formula_id)
    print(f"\nScenario: reformulate '{formula['name']}' to clean label.")
    print(f"Target claims: {', '.join(target_claims)} | Region: {region}")
    print("Constraints: cost-aware, shelf-life >= 7 days (demo targets).")

    ctx = build_demo_context(
        formula_id,
        target_claims,
        region,
        adjustments=scenario["adjustments"],
        additions=scenario["additions"],
    )
    blackboard = asyncio.run(run_reformulation(ctx, live=args.live))
    _print_report(blackboard)

    if args.audit_log:
        from food_ingredients_ai.governance.audit import AuditTrail

        trail = AuditTrail(args.audit_log)
        trail.log(
            actor="demo",
            action="reformulation_demo",
            payload={
                "scenario": args.scenario,
                "formula_id": formula_id,
                "mode": "live" if args.live else "offline",
                "flagged_count": blackboard["analyze_ingredients"]["flagged_count"],
            },
            decision="completed",
        )
        trail.close()
        print(f"\nAudit trail written to {args.audit_log}")


if __name__ == "__main__":
    import sys

    main(sys.argv[1:])

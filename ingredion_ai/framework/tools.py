"""Framework function-tools: domain logic exposed to framework agents.

Each tool is a plain annotated Python function (the framework converts
these to function-tools automatically). Tools close over a demo *context*
dict carrying ``formula_id``/``target_claims``/``region``/``adjustments``/
``additions`` and a shared ``blackboard`` dict. Every tool:

1. calls the corresponding deterministic domain agent ``execute()``,
2. stores the raw result dict in the blackboard under its task name,
3. returns the result as a JSON string for the model.

Because the tools run the exact same ``execute()`` code paths as the
tested offline pipeline, results are byte-identical offline.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List

from ingredion_ai.agents import (
    CustomerAdvisorAgent,
    ESGAgent,
    RDFormulationAgent,
    SupplyChainAgent,
)

# Task names double as blackboard keys (mirrors the legacy orchestrator).
RD_TASKS = [
    "analyze_ingredients",
    "suggest_substitutes",
    "predict_texture_shelf_life",
    "calculate_nutrition",
    "validate_claims",
    "generate_documentation",
]


def _payload(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "formula_id": ctx["formula_id"],
        "target_claims": ctx["target_claims"],
        "region": ctx["region"],
        "adjustments": ctx.get("adjustments"),
        "additions": ctx.get("additions"),
        "blackboard": ctx["blackboard"],
    }


def _store(ctx: Dict[str, Any], task_name: str, result: Dict[str, Any]) -> str:
    ctx["blackboard"][task_name] = result
    return json.dumps(result, default=str)


def build_tool_functions(ctx: Dict[str, Any]) -> Dict[str, List[Callable[..., str]]]:
    """Build ``{agent_name: [tool functions]}`` bound to *ctx*."""
    rd = RDFormulationAgent()
    sc = SupplyChainAgent()
    esg = ESGAgent()
    ca = CustomerAdvisorAgent()
    bb = ctx["blackboard"]

    def analyze_ingredients() -> str:
        """Flag non-clean-label ingredients in the demo formula."""
        return _store(ctx, "analyze_ingredients", rd.execute("analyze_ingredients", _payload(ctx)))

    def suggest_substitutes() -> str:
        """Recommend clean-label substitute ingredients and build the reformulated formula."""
        return _store(ctx, "suggest_substitutes", rd.execute("suggest_substitutes", _payload(ctx)))

    def predict_texture_shelf_life() -> str:
        """Predict texture match and shelf-life for the reformulated formula."""
        return _store(
            ctx, "predict_texture_shelf_life", rd.execute("predict_texture_shelf_life", _payload(ctx))
        )

    def calculate_nutrition() -> str:
        """Compute nutritional panels for the original and reformulated formulas."""
        return _store(ctx, "calculate_nutrition", rd.execute("calculate_nutrition", _payload(ctx)))

    def validate_claims() -> str:
        """Validate label claims (e.g. no artificial ingredients, reduced sugar, natural) per region."""
        return _store(ctx, "validate_claims", rd.execute("validate_claims", _payload(ctx)))

    def generate_documentation() -> str:
        """Generate the formulation spec and customer technical sheet (markdown)."""
        return _store(
            ctx, "generate_documentation", rd.execute("generate_documentation", _payload(ctx))
        )

    def forecast_demand() -> str:
        """Forecast weekly ingredient demand for the demo SKUs."""
        return _store(
            ctx,
            "forecast_demand",
            sc.execute("forecast_demand", {"skus": ["PF-200"], "periods": 4}),
        )

    def collect_esg() -> str:
        """Collect synthetic ESG readings (energy, water, emissions) for demo plants."""
        result = esg.execute("collect_esg", {})
        bb["collect_esg"] = result
        return json.dumps(result, default=str)

    def esg_report() -> str:
        """Generate the ESG report (markdown) with traceable calculations."""
        return _store(ctx, "esg_report", esg.execute("esg_report", {"blackboard": bb}))

    def estimate_pricing() -> str:
        """Estimate cost and pricing bands for the reformulated formula."""
        return _store(
            ctx,
            "estimate_pricing",
            ca.execute(
                "estimate_pricing",
                {
                    "formula": bb["suggest_substitutes"]["reformulated_formula"],
                    "valid_claims": [
                        c["claim"] for c in bb["validate_claims"]["claims"] if c["valid"]
                    ],
                    "blackboard": bb,
                },
            ),
        )

    return {
        "rd_formulation": [
            analyze_ingredients,
            suggest_substitutes,
            predict_texture_shelf_life,
            calculate_nutrition,
            validate_claims,
            generate_documentation,
        ],
        "supply_chain": [forecast_demand],
        "esg": [collect_esg, esg_report],
        "customer_advisor": [estimate_pricing],
    }

"""Async runner for the framework-based reformulation demo."""

from __future__ import annotations

from typing import Any, Dict

from food_ingredients_ai.framework.agents import build_framework_agents
from food_ingredients_ai.framework.workflow import build_reformulation_workflow

DEMO_GOAL = (
    "Reformulate the demo sweet bakery cake to clean label: analyze its "
    "ingredients, suggest clean-label substitutes, predict texture and "
    "shelf-life impact, calculate nutrition, validate the target label "
    "claims, and generate documentation."
)


def build_demo_context(
    formula_id: str,
    target_claims: list,
    region: str,
    adjustments: Dict[str, Any] | None = None,
    additions: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build the shared context (inputs + blackboard) for a demo run."""
    return {
        "formula_id": formula_id,
        "target_claims": list(target_claims),
        "region": region,
        "adjustments": adjustments or {},
        "additions": additions or {},
        "blackboard": {},
    }


async def run_reformulation(ctx: Dict[str, Any], *, live: bool = False) -> Dict[str, Any]:
    """Run the framework workflow; return the populated blackboard.

    - ``live=False``: scripted fake clients (offline, deterministic).
    - ``live=True``: Azure OpenAI client from the environment.
    """
    agents = build_framework_agents(ctx, live=live)
    workflow = build_reformulation_workflow(agents)
    await workflow.run(DEMO_GOAL)
    return ctx["blackboard"]

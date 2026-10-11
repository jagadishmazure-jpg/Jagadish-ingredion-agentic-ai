"""Policy engine: allowed/disallowed actions per agent (demo).

The demo agents are read-only advisors — they analyze, recommend, predict,
and draft documents, but never mutate production systems. The policy engine
makes those boundaries explicit and checkable at runtime.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

# agent -> {"allow": [...], "deny": [...]}. Deny always wins over allow.
AGENT_POLICIES: Dict[str, Dict[str, List[str]]] = {
    "rd_formulation": {
        "allow": [
            "analyze_ingredients",
            "suggest_substitutes",
            "predict_texture_shelf_life",
            "calculate_nutrition",
            "validate_claims",
            "generate_documentation",
            "estimate_cycle_time",
            "lims_quality_lookup",
        ],
        "deny": [
            "approve_production",
            "modify_plm",
            "modify_sap",
            "place_order",
            "publish_claims",
        ],
    },
    "supply_chain": {
        "allow": [
            "forecast_demand",
            "optimize_inventory",
            "get_inventory",
            "schedule_production",
        ],
        "deny": [
            "place_order",
            "modify_sap",
            "approve_production",
            "modify_formula",
        ],
    },
    "esg": {
        "allow": ["collect_esg", "calculate_carbon", "esg_report"],
        "deny": ["publish_esg_report", "modify_esg_source_data", "modify_sap"],
    },
    "customer_advisor": {
        "allow": [
            "recommend_ingredients",
            "generate_sample_formula",
            "validate_claims",
            "estimate_pricing",
            "generate_tech_sheet",
        ],
        "deny": ["send_customer_proposal", "set_prices", "modify_formula"],
    },
    "orchestrator": {
        "allow": ["plan", "route_task", "aggregate_results"],
        "deny": ["execute_tool_directly", "bypass_approval_gate"],
    },
}


class PolicyEngine:
    """Check agent actions against the demo policy table."""

    def __init__(self, policies: Dict[str, Dict[str, List[str]]] | None = None) -> None:
        self.policies = policies if policies is not None else AGENT_POLICIES

    def check(self, agent: str, action: str) -> Tuple[bool, str]:
        """Return ``(allowed, reason)`` for *agent* performing *action*."""
        policy = self.policies.get(agent)
        if policy is None:
            return False, f"unknown agent in demo policy: {agent!r}"
        if action in policy.get("deny", []):
            return False, f"action {action!r} explicitly denied for {agent!r}"
        if action in policy.get("allow", []):
            return True, f"action {action!r} allowed for {agent!r}"
        return False, f"action {action!r} not in allow-list for {agent!r}"

    def allowed_actions(self, agent: str) -> List[str]:
        """Allow-listed actions for *agent* (empty for unknown agents)."""
        return list(self.policies.get(agent, {}).get("allow", []))


def check_action(agent: str, action: str) -> Tuple[bool, str]:
    """Module-level convenience check against the default demo policies."""
    return PolicyEngine().check(agent, action)

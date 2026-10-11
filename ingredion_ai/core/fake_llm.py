"""Deterministic offline stand-in for an LLM.

The whole portfolio runs without API keys or network access, so every agent
reasons through this scripted client. Responses are keyword-driven and fully
deterministic: the same prompt always yields the same completion.
"""


class FakeLLM:
    """Keyword-routed, deterministic fake language model."""

    def __init__(self, default: str = "ACK") -> None:
        self.default = default
        self.calls: list[str] = []

    def generate(self, prompt: str) -> str:
        """Return a scripted completion for *prompt* (deterministic)."""
        self.calls.append(prompt)
        lowered = prompt.lower()
        if "reformul" in lowered:
            return (
                "PLAN: analyze_ingredients -> suggest_substitutes -> "
                "predict_texture_shelf_life -> calculate_nutrition -> "
                "validate_claims -> generate_documentation"
            )
        if "launch" in lowered:
            return (
                "PLAN: reformulate -> forecast_demand -> optimize_inventory -> "
                "esg_report -> advise_customer"
            )
        if "supply" in lowered or "forecast" in lowered or "demand" in lowered:
            return (
                "PLAN: forecast_demand -> optimize_inventory -> "
                "schedule_production -> detect_quality_anomalies"
            )
        if "esg" in lowered or "carbon" in lowered or "sustainab" in lowered:
            return "PLAN: collect_esg -> calculate_carbon -> esg_report"
        if "customer" in lowered or "advisor" in lowered or "pricing" in lowered:
            return (
                "PLAN: recommend_ingredients -> generate_sample_formula -> "
                "validate_customer_claims -> estimate_pricing -> generate_tech_sheet"
            )
        return f"{self.default}: {prompt[:80]}"

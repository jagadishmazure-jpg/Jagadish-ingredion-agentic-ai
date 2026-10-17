"""Claim validation for the customer advisor (reuses the R&D ruleset)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from food_ingredients_ai.agents.rd_formulation import regulatory


def validate(
    formula: Dict[str, Any],
    claims: List[str],
    region: str = "NA",
    baseline_sugar_g: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Validate *claims* for a customer-facing demo formula."""
    return regulatory.validate_claims(
        formula, claims, region=region, baseline_sugar_g=baseline_sugar_g
    )

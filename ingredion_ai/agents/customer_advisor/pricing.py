"""Pricing estimator: cost + willingness-to-pay bands (demo)."""

from __future__ import annotations

from typing import Any, Dict, List

from ingredion_ai.data.loader import get_ingredient

BASE_COST_PER_KG_USD = 10.0  # demo scaling factor
MARGIN = 1.35  # demo base margin multiplier

# Demo willingness-to-pay uplift per *validated* claim.
WTP_UPLIFT = {
    "natural": 0.10,
    "no artificial ingredients": 0.08,
    "reduced sugar": 0.06,
    "high protein": 0.05,
}


def estimate_pricing(
    formula: Dict[str, Any], valid_claims: List[str]
) -> Dict[str, Any]:
    """Estimate cost and a price band for a demo formula."""
    cost = sum(
        (item["pct"] / 100.0) * get_ingredient(item["id"])["cost_index"]
        for item in formula["ingredients"]
    )
    cost_per_kg = round(cost * BASE_COST_PER_KG_USD, 2)
    uplift = round(
        sum(WTP_UPLIFT.get(c.strip().lower(), 0.0) for c in valid_claims), 4
    )
    price_low = round(cost_per_kg * MARGIN, 2)
    price_high = round(cost_per_kg * MARGIN * (1 + uplift), 2)
    return {
        "cost_per_kg_usd": cost_per_kg,
        "uplift_pct": round(uplift * 100, 2),
        "price_low_usd": price_low,
        "price_high_usd": price_high,
        "valid_claims_priced": list(valid_claims),
        "demo": True,
    }

"""Pricing estimator: cost + willingness-to-pay bands (demo)."""

from __future__ import annotations

from typing import Any, Dict, List

from ingredion_ai.data.loader import get_ingredient

BASE_COST_PER_KG_USD = 10.0  # demo scaling factor
MARGIN = 1.35  # demo base margin multiplier

# Demo willingness-to-pay uplift per *validated* claim.
# Rationale (paraphrased from public clean-label consumer research): about
# half of consumers will pay 10% or more for claims they value, so the demo
# maps total validated-claim uplift into named willingness-to-pay bands.
WTP_UPLIFT = {
    "natural": 0.10,
    "no artificial ingredients": 0.08,
    "reduced sugar": 0.06,
    "high protein": 0.05,
}


def wtp_band(uplift_pct: float) -> str:
    """Map a total uplift percentage to a named willingness-to-pay band."""
    if uplift_pct >= 15.0:
        return "premium-plus"
    if uplift_pct >= 10.0:
        return "premium"
    if uplift_pct >= 5.0:
        return "value-plus"
    return "standard"


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
    band = wtp_band(round(uplift * 100, 2))
    return {
        "cost_per_kg_usd": cost_per_kg,
        "uplift_pct": round(uplift * 100, 2),
        "price_low_usd": price_low,
        "price_high_usd": price_high,
        "valid_claims_priced": list(valid_claims),
        "wtp_band": band,
        "wtp_rationale": (
            f"validated claims support a '{band}' willingness-to-pay band "
            "(demo; ~50% of consumers pay 10%+ for valued claims per public research)"
        ),
        "demo": True,
    }

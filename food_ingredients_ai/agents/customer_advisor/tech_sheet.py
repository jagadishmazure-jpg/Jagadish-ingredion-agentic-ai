"""Customer technical sheet generator (demo markdown)."""

from __future__ import annotations

from typing import Any, Dict, List


def generate_customer_tech_sheet(
    formula: Dict[str, Any],
    claims: List[Dict[str, Any]],
    pricing: Dict[str, Any],
) -> str:
    """Render a customer-facing technical sheet as markdown (demo)."""
    from food_ingredients_ai.data.loader import get_ingredient

    valid = [c["claim"] for c in claims if c["valid"]]
    lines = [
        "# Customer Technical Sheet (Demo)",
        "",
        f"**Product concept:** {formula['name']}",
        "",
        "## Recommended Ingredients",
        "",
        "| Ingredient | % | Function |",
        "|---|---|---|",
    ]
    for item in sorted(formula["ingredients"], key=lambda i: -i["pct"])[:10]:
        ing = get_ingredient(item["id"])
        lines.append(f"| {ing['name']} | {item['pct']:.2f}% | {ing['function']} |")
    lines += [
        "",
        "## Validated Claims",
        "",
    ]
    lines += [f"- {claim}" for claim in valid] or ["- _none validated_"]
    lines += [
        "",
        "## Indicative Pricing (demo)",
        "",
        f"- Estimated cost: **${pricing['cost_per_kg_usd']}/kg**",
        f"- Suggested price band: **${pricing['price_low_usd']}–${pricing['price_high_usd']}/kg**",
        f"- Claim-driven uplift: **{pricing['uplift_pct']}%**",
        "",
        "_Demo document — synthetic data only. Not affiliated with any real company._",
        "",
    ]
    return "\n".join(lines)

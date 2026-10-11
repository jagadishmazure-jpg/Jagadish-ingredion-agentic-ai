"""Documentation generator: formulation spec + customer technical sheet."""

from __future__ import annotations

from typing import Any, Dict, List


def _ingredient_lines(formula: Dict[str, Any]) -> List[str]:
    from ingredion_ai.data.loader import get_ingredient

    lines = []
    for item in sorted(formula["ingredients"], key=lambda i: -i["pct"]):
        ing = get_ingredient(item["id"])
        lines.append(
            f"| {ing['name']} | {item['pct']:.2f}% | {ing['function']} | "
            f"{'yes' if ing['clean_label'] else 'no'} |"
        )
    return lines


def generate_formulation_spec(
    formula: Dict[str, Any],
    analysis: Dict[str, Any],
    substitutions: List[Dict[str, Any]],
    prediction: Dict[str, Any],
    nutrition: Dict[str, Any],
    claims: List[Dict[str, Any]],
) -> str:
    """Internal R&D formulation spec as markdown (demo)."""
    lines = [
        "# Formulation Specification (Demo)",
        "",
        f"**Formula:** {formula['name']} (`{formula['id']}`)",
        f"**Category:** {formula.get('category', 'n/a')} | **Servings:** {formula.get('servings', 'n/a')}",
        "",
        "## Composition",
        "",
        "| Ingredient | % | Function | Clean-label |",
        "|---|---|---|---|",
        *_ingredient_lines(formula),
        "",
        "## Non-Clean-Label Analysis",
        "",
    ]
    if analysis["clean"]:
        lines.append("No flagged ingredients — formula is clean-label per demo rules.")
    else:
        for f in analysis["flagged"]:
            lines.append(f"- **{f['name']}** ({f['pct']}%): {'; '.join(f['reasons'])}")
    lines += [
        "",
        "## Substitutions Applied",
        "",
    ]
    for s in substitutions:
        if s["action"] == "remove":
            lines.append(f"- REMOVED **{s['old_name']}**: {s['reason']}")
        else:
            lines.append(
                f"- **{s['old_name']}** -> **{s['new_name']}** "
                f"({s['new_pct']}%): {s['reason']}"
            )
    lines += [
        "",
        "## Predicted Performance (demo heuristic)",
        "",
        f"- Texture match: **{prediction['texture_match_pct']}%**",
        f"- Shelf-life: **{prediction['shelf_life_days']} days**",
    ]
    for flag in prediction["risk_flags"]:
        lines.append(f"- RISK: {flag}")
    lines += [
        "",
        "## Nutrition (per 100 g, synthetic values)",
        "",
    ]
    for nutrient, value in nutrition["per_100g"].items():
        lines.append(f"- {nutrient}: {value}")
    lines += ["", "## Claim Validation", ""]
    for c in claims:
        mark = "PASS" if c["valid"] else "FAIL"
        lines.append(f"- [{mark}] **{c['claim']}**: {'; '.join(c['reasons'])}")
    lines += ["", "_Demo document — synthetic data only._", ""]
    return "\n".join(lines)


def generate_technical_sheet(
    formula: Dict[str, Any],
    claims: List[Dict[str, Any]],
    nutrition: Dict[str, Any],
) -> str:
    """Customer-facing technical sheet as markdown (demo)."""
    valid_claims = [c["claim"] for c in claims if c["valid"]]
    lines = [
        "# Customer Technical Sheet (Demo)",
        "",
        f"**Product:** {formula['name']}",
        "",
        "## Validated Claims",
        "",
    ]
    lines += [f"- {claim}" for claim in valid_claims] or ["- _none validated_"]
    lines += [
        "",
        "## Key Ingredients",
        "",
        "| Ingredient | % |",
        "|---|---|",
        *_ingredient_lines(formula)[:8],
        "",
        "## Nutrition Highlights (per 100 g)",
        "",
        f"- Energy: {nutrition['per_100g']['kcal']} kcal",
        f"- Sugars: {nutrition['per_100g']['sugar_g']} g",
        f"- Protein: {nutrition['per_100g']['protein_g']} g",
        "",
        "_Demo document — synthetic data only. Not affiliated with Ingredion._",
        "",
    ]
    return "\n".join(lines)

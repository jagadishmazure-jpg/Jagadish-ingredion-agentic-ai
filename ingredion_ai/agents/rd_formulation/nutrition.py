"""Nutrition calculator over the synthetic ingredient database."""

from __future__ import annotations

from typing import Any, Dict

from ingredion_ai.data.loader import get_ingredient

NUTRIENTS = ["kcal", "protein_g", "carbs_g", "sugar_g", "fat_g", "sodium_mg"]


def calculate_nutrition(formula: Dict[str, Any]) -> Dict[str, Any]:
    """Nutritional panel per 100 g of *formula* (synthetic demo values)."""
    totals = {n: 0.0 for n in NUTRIENTS}
    for item in formula["ingredients"]:
        ing = get_ingredient(item["id"])
        factor = item["pct"] / 100.0
        for nutrient in NUTRIENTS:
            totals[nutrient] += factor * float(ing["nutrition"][nutrient])
    return {
        "formula_id": formula["id"],
        "per_100g": {n: round(v, 2) for n, v in totals.items()},
        "demo": True,
    }

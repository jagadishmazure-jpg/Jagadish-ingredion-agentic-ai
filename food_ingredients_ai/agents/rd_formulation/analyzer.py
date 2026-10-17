"""Ingredient analyzer: flags non-clean-label ingredients using demo rules."""

from __future__ import annotations

from typing import Any, Dict, List

from food_ingredients_ai.data.loader import get_ingredient

# (keyword, human-readable reason) — checked against demo ingredient names/ids.
NON_CLEAN_LABEL_MARKERS = [
    ("artificial", "name contains 'artificial' (synthetic ingredient)"),
    ("titanium dioxide", "titanium dioxide whitener is not clean-label"),
    ("red 40", "synthetic color (Red 40)"),
    ("red40", "synthetic color (Red 40)"),
    ("high fructose", "high-fructose sweetener is not clean-label"),
    ("modified", "chemically modified starch is not clean-label"),
    ("sodium benzoate", "synthetic preservative"),
    ("polysorbate", "synthetic emulsifier"),
    ("tbhq", "synthetic antioxidant"),
    # Markers for the extended demo DB (fictional ingredients).
    ("butylshield", "synthetic antioxidant (ButylShield)"),
    ("sunsetyellow", "synthetic color (SunsetYellow)"),
    ("caffeineboost", "synthetic caffeine stimulant"),
    ("sweetplus", "synthetic high-intensity sweetener"),
]


def analyze_formula(formula: Dict[str, Any]) -> Dict[str, Any]:
    """Flag non-clean-label ingredients in *formula* (demo ruleset).

    Returns ``{"formula_id", "flagged": [...], "flagged_count", "clean"}``.
    """
    flagged: List[Dict[str, Any]] = []
    for item in formula["ingredients"]:
        ing = get_ingredient(item["id"])
        reasons: List[str] = []
        if not ing["clean_label"]:
            reasons.append(ing.get("note") or "listed as non-clean-label in demo DB")
        blob = f"{ing['name']} {ing['id']}".lower()
        for keyword, reason in NON_CLEAN_LABEL_MARKERS:
            if keyword in blob and reason not in reasons:
                reasons.append(reason)
        if reasons:
            flagged.append(
                {
                    "ingredient_id": ing["id"],
                    "name": ing["name"],
                    "pct": item["pct"],
                    "function": ing["function"],
                    "reasons": reasons,
                }
            )
    return {
        "formula_id": formula["id"],
        "flagged": flagged,
        "flagged_count": len(flagged),
        "clean": not flagged,
    }

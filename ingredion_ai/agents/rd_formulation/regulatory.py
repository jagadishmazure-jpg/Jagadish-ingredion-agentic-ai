"""Regulatory claim checker (rule-based, demo ruleset).

Validates label claims such as "no artificial ingredients", "reduced sugar"
and "natural" against the synthetic formula and per-region demo rules.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ingredion_ai.agents.rd_formulation.analyzer import analyze_formula
from ingredion_ai.data.loader import get_ingredient

REDUCED_SUGAR_MIN_REDUCTION = 0.25  # >=25% less sugar vs baseline
HIGH_PROTEIN_MIN_G = 10.0  # per 100 g, demo threshold

# Claim priority for pursuit order.
# Rationale (paraphrased from public clean-label consumer research):
# "natural / all natural" ranks as the most important packaged-food claim,
# followed by no-artificial-ingredient cues, then reduced-sugar and
# high-protein cues. The demo uses this ordering when several claims are
# candidates so the highest-value claim is pursued first.
CLAIM_PRIORITY = [
    "natural",
    "no artificial ingredients",
    "reduced sugar",
    "high protein",
]


def prioritize_claims(claims: List[str]) -> List[str]:
    """Order *claims* by consumer-research priority (unknown claims last)."""
    def _rank(claim: str) -> tuple:
        normalized = claim.strip().lower()
        try:
            return (CLAIM_PRIORITY.index(normalized), normalized)
        except ValueError:
            return (len(CLAIM_PRIORITY), normalized)

    return sorted(claims, key=_rank)

# Demo EU rule: only these synthetic-DB colors are permitted with "natural".
EU_PERMITTED_COLORS = {"BC-12", "TC-08", "SB-05", "CO-22"}


def _check_no_artificial(formula: Dict[str, Any]) -> tuple[bool, List[str]]:
    analysis = analyze_formula(formula)
    if analysis["clean"]:
        return True, ["no flagged ingredients in demo analysis"]
    names = ", ".join(f["name"] for f in analysis["flagged"])
    return False, [f"flagged non-clean-label ingredients remain: {names}"]


def _check_reduced_sugar(
    nutrition: Dict[str, Any], baseline_sugar_g: Optional[float]
) -> tuple[bool, List[str]]:
    if baseline_sugar_g is None or baseline_sugar_g <= 0:
        return False, ["baseline sugar value required for 'reduced sugar'"]
    current = nutrition["per_100g"]["sugar_g"]
    reduction = (baseline_sugar_g - current) / baseline_sugar_g
    if reduction >= REDUCED_SUGAR_MIN_REDUCTION:
        return True, [
            f"sugar reduced {reduction:.1%} vs baseline "
            f"({baseline_sugar_g}g -> {current}g per 100g)"
        ]
    return False, [
        f"sugar reduction {reduction:.1%} below "
        f"{REDUCED_SUGAR_MIN_REDUCTION:.0%} demo threshold"
    ]


def _check_natural(formula: Dict[str, Any], region: str) -> tuple[bool, List[str]]:
    offenders = [
        get_ingredient(i["id"])["name"]
        for i in formula["ingredients"]
        if not get_ingredient(i["id"])["natural"]
    ]
    if offenders:
        return False, [
            "not eligible for 'natural': " + ", ".join(sorted(set(offenders)))
        ]
    if region.upper() == "EU":
        bad_colors = [
            i["id"]
            for i in formula["ingredients"]
            if get_ingredient(i["id"])["function"] == "color"
            and i["id"] not in EU_PERMITTED_COLORS
        ]
        if bad_colors:
            return False, [f"EU demo rule: colors not permitted: {bad_colors}"]
    return True, ["all ingredients natural-claim eligible under demo rules"]


def _check_high_protein(nutrition: Dict[str, Any]) -> tuple[bool, List[str]]:
    protein = nutrition["per_100g"]["protein_g"]
    if protein >= HIGH_PROTEIN_MIN_G:
        return True, [f"protein {protein}g per 100g meets demo threshold"]
    return False, [f"protein {protein}g per 100g below {HIGH_PROTEIN_MIN_G}g demo threshold"]


def validate_claims(
    formula: Dict[str, Any],
    claims: List[str],
    region: str = "NA",
    nutrition: Optional[Dict[str, Any]] = None,
    baseline_sugar_g: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Validate *claims* for *formula*; unknown claims are rejected."""
    from ingredion_ai.agents.rd_formulation.nutrition import calculate_nutrition

    nutrition = nutrition or calculate_nutrition(formula)
    results: List[Dict[str, Any]] = []
    for claim in claims:
        normalized = claim.strip().lower()
        if normalized == "no artificial ingredients":
            valid, reasons = _check_no_artificial(formula)
        elif normalized == "reduced sugar":
            valid, reasons = _check_reduced_sugar(nutrition, baseline_sugar_g)
        elif normalized == "natural":
            valid, reasons = _check_natural(formula, region)
        elif normalized == "high protein":
            valid, reasons = _check_high_protein(nutrition)
        else:
            valid, reasons = False, [f"unknown claim in demo ruleset: {claim!r}"]
        results.append({"claim": claim, "valid": valid, "reasons": reasons})
    return results

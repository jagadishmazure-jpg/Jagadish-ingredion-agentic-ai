"""Labeled synthetic eval datasets (demo).

Each entry is hand-labeled against the demo rulesets; the suites measure
whether the agent logic agrees with the labels. All data is synthetic.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Claim-validation eval set: (formula_id, claim, region, expected_valid).
# Labels were produced by reading the demo regulatory rules.
CLAIM_EVAL_SET: List[Dict[str, Any]] = [
    # Sweet bakery cake reformulation: all flagged ingredients replaced.
    {"formula_id": "sweet_bakery_cake__clean_label", "claim": "no artificial ingredients",
     "region": "NA", "expected": True},
    {"formula_id": "sweet_bakery_cake__clean_label", "claim": "natural",
     "region": "NA", "expected": False},  # refined sugar not natural-eligible
    # Raw baseline: still full of flagged ingredients.
    {"formula_id": "sweet_bakery_cake", "claim": "no artificial ingredients",
     "region": "NA", "expected": False},
    {"formula_id": "sweet_bakery_cake", "claim": "natural",
     "region": "NA", "expected": False},
    # Gluten-free bread baseline is already clean.
    {"formula_id": "gluten_free_bread", "claim": "no artificial ingredients",
     "region": "NA", "expected": True},
    {"formula_id": "gluten_free_bread", "claim": "natural",
     "region": "NA", "expected": True},
    # Energy drink reformulation: synthetic stimulant removed.
    {"formula_id": "energy_drink__clean_label", "claim": "no artificial ingredients",
     "region": "NA", "expected": True},
    {"formula_id": "energy_drink", "claim": "no artificial ingredients",
     "region": "NA", "expected": False},
    # Unknown claims are always rejected by the demo ruleset.
    {"formula_id": "gluten_free_bread", "claim": "keto certified",
     "region": "NA", "expected": False},
    # Savory crackers reformulation.
    {"formula_id": "savory_bakery_crackers__clean_label", "claim": "natural",
     "region": "NA", "expected": True},
]

# Substitution eval set: (flagged ingredient id -> expected top candidate).
SUBSTITUTION_EVAL_SET: List[Dict[str, str]] = [
    {"old_id": "MCS-10", "expected_top": "PF-200"},
    {"old_id": "HFCS-42", "expected_top": "FS-40"},
    {"old_id": "AV-01", "expected_top": "NV-60"},
    {"old_id": "R40", "expected_top": "BC-12"},
    {"old_id": "SBZ", "expected_top": "CD-55"},
    {"old_id": "P60", "expected_top": "SL-70"},
    {"old_id": "TBHQ", "expected_top": "RE-77"},
    {"old_id": "AB-66", "expected_top": "NV-60"},
    {"old_id": "YS-58", "expected_top": "BC-12"},
    {"old_id": "SPS-72", "expected_top": "MNK-77"},
]

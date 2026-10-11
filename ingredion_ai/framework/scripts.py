"""Deterministic fake-client scripts for the offline reformulation demo.

Each agent gets an ordered script; the ``FakeChatClient`` emits one
function call per script step (with fixed arguments) and finishes with a
fixed summary line. Because the tools execute the real deterministic
domain logic, the demo output is byte-identical across runs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# A script step is ("tool", tool_name, args) or ("text", final_text).
Script = List[Tuple[str, Any, Any]]

RD_SCRIPT: Script = [
    ("tool", "analyze_ingredients", {}),
    ("tool", "suggest_substitutes", {}),
    ("tool", "predict_texture_shelf_life", {}),
    ("tool", "calculate_nutrition", {}),
    ("tool", "validate_claims", {}),
    ("tool", "generate_documentation", {}),
    ("text", "R&D reformulation complete: 6/6 steps finished."),
]

SUPPLY_SCRIPT: Script = [
    ("tool", "forecast_demand", {}),
    ("text", "Supply forecast complete."),
]

ESG_SCRIPT: Script = [
    ("tool", "collect_esg", {}),
    ("tool", "esg_report", {}),
    ("text", "ESG report complete."),
]

ADVISOR_SCRIPT: Script = [
    ("tool", "estimate_pricing", {}),
    ("text", "Pricing estimate complete."),
]

DEMO_SCRIPTS: Dict[str, Script] = {
    "rd_formulation": RD_SCRIPT,
    "supply_chain": SUPPLY_SCRIPT,
    "esg": ESG_SCRIPT,
    "customer_advisor": ADVISOR_SCRIPT,
}

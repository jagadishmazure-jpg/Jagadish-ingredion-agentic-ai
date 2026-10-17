"""Dedicated guardrails package for the agent system.

Centralizes input/output safety checks that were previously ad-hoc:

- :mod:`food_ingredients_ai.guardrails.input` — prompt-injection/jailbreak
  detection, PII detection in inputs, domain-scope enforcement,
  input length/sanity limits.
- :mod:`food_ingredients_ai.guardrails.output` — PII scrubbing, claim-grounding
  checks, confidence thresholds, output safety patterns.
- :mod:`food_ingredients_ai.guardrails.policies` — configurable strictness
  levels (permissive/standard/strict) via env, with per-agent overrides.

Production Azure mapping (see ``docs/security.md``):

- ``input.py``  → Azure AI **Prompt Shields**
- ``output.py`` → Azure AI **Content Safety**
- ``policies.py`` → **Foundry Guardrails** (policy-as-code)

All data is synthetic demo data. Stdlib only.
"""

from __future__ import annotations

from .input import IN_DOMAIN_KEYWORDS, InputVerdict, check_input
from .output import OutputVerdict, check_output
from .policies import GuardrailPolicy, Strictness, load_policy

__all__ = [
    "IN_DOMAIN_KEYWORDS",
    "InputVerdict",
    "OutputVerdict",
    "GuardrailPolicy",
    "Strictness",
    "check_input",
    "check_output",
    "load_policy",
]

"""Guardrail strictness policies.

Levels:

- ``permissive`` — block only blatant instruction-override / forged-system
  attacks; PII is flagged, not blocked; domain enforcement off.
- ``standard`` (default) — block all known injection patterns; flag PII;
  off-topic inputs refused.
- ``strict`` — standard + encoded-payload blocking, aggressive off-topic
  refusal, PII in inputs blocked.

Configuration via env (12-factor; no code changes to retune):

- ``GUARDRAILS_STRICTNESS`` — permissive|standard|strict (default standard)
- ``GUARDRAILS_STRICTNESS_{AGENT}`` — per-agent override, e.g.
  ``GUARDRAILS_STRICTNESS_RD_FORMULATION=strict``
- ``GUARDRAILS_MAX_INPUT_CHARS`` — default 8000
- ``GUARDRAILS_MIN_CONFIDENCE`` — default 0.35

Production equivalent: Foundry Guardrails (policy-as-code).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Strictness(str, Enum):
    PERMISSIVE = "permissive"
    STANDARD = "standard"
    STRICT = "strict"


@dataclass(frozen=True)
class GuardrailPolicy:
    """Resolved guardrail policy for one agent (or the default)."""

    strictness: Strictness = Strictness.STANDARD
    max_input_chars: int = 8000
    min_confidence: float = 0.35
    domain_enforcement: bool = True
    block_encoded_payloads: bool = False
    block_pii_input: bool = False

    @property
    def check_injection(self) -> bool:
        return True  # injection checks are never disabled, only tuned

    @property
    def aggressive_off_topic(self) -> bool:
        return self.strictness is Strictness.STRICT


def _parse_strictness(raw: Optional[str]) -> Optional[Strictness]:
    if not raw:
        return None
    try:
        return Strictness(raw.strip().lower())
    except ValueError:
        return None


def load_policy(agent_name: Optional[str] = None) -> GuardrailPolicy:
    """Load the effective policy: global env, then per-agent override."""
    strictness = _parse_strictness(os.environ.get("GUARDRAILS_STRICTNESS"))
    if agent_name:
        override = _parse_strictness(
            os.environ.get(f"GUARDRAILS_STRICTNESS_{agent_name.upper()}")
        )
        if override is not None:
            strictness = override
    if strictness is None:
        strictness = Strictness.STANDARD

    try:
        max_chars = int(os.environ.get("GUARDRAILS_MAX_INPUT_CHARS", "8000"))
    except ValueError:
        max_chars = 8000
    try:
        min_conf = float(os.environ.get("GUARDRAILS_MIN_CONFIDENCE", "0.35"))
    except ValueError:
        min_conf = 0.35

    if strictness is Strictness.PERMISSIVE:
        return GuardrailPolicy(
            strictness=strictness,
            max_input_chars=max_chars,
            min_confidence=min_conf,
            domain_enforcement=False,
        )
    if strictness is Strictness.STRICT:
        return GuardrailPolicy(
            strictness=strictness,
            max_input_chars=max_chars,
            min_confidence=min_conf,
            domain_enforcement=True,
            block_encoded_payloads=True,
            block_pii_input=True,
        )
    return GuardrailPolicy(
        strictness=strictness,
        max_input_chars=max_chars,
        min_confidence=min_conf,
    )

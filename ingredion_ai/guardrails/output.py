"""Output guardrails: PII scrubbing, claim-grounding checks, confidence
thresholds, and output safety patterns.

- PII scrubbing reuses :func:`ingredion_ai.governance.security.scrub_pii`
  (single source of truth for patterns).
- Claim grounding: every factual claim in agent output should trace to
  RAG citations or dataset values; ungrounded claims are flagged so
  callers can abstain, escalate, or demand sources.
- Confidence thresholds: low-confidence outputs abstain/escalate instead
  of presenting guesses as facts.
- Output safety: scan outputs for leaked prompt-injection artifacts
  (e.g. echoed system instructions), which indicate prompt compromise.

Production equivalent: Azure AI Content Safety.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ingredion_ai.governance.security import INJECTION_PATTERNS, scrub_pii

from .policies import GuardrailPolicy, load_policy


@dataclass
class OutputVerdict:
    """Result of :func:`check_output`."""

    text: str  # PII-scrubbed output, safe to return/log
    flags: List[str] = field(default_factory=list)
    abstain: bool = False
    abstention_reason: Optional[str] = None


def _claim_grounded(claim_text: str, citations: Sequence[str]) -> bool:
    """A claim is grounded if its key text appears in any citation excerpt."""
    needle = " ".join(claim_text.lower().split())
    if len(needle) < 8:
        return True  # too short to judge; don't flag noise
    return any(needle in " ".join(c.lower().split()) for c in citations)


def check_output(
    text: Optional[str],
    *,
    claims: Optional[Sequence[Dict[str, object]]] = None,
    citations: Optional[Sequence[str]] = None,
    confidence: Optional[float] = None,
    policy: Optional[GuardrailPolicy] = None,
) -> OutputVerdict:
    """Evaluate agent output against the guardrail policy.

    - ``claims``: optional list of ``{"text": str, "sources": [...]}`` —
      claims with empty ``sources`` that don't appear in ``citations``
      are flagged as ungrounded.
    - ``citations``: RAG citation excerpts (or dataset-value strings).
    - ``confidence``: 0..1 model/tool confidence; below
      ``policy.min_confidence`` the verdict abstains.
    Never raises: returns a verdict.
    """
    policy = policy or load_policy()
    text = text or ""
    flags: List[str] = []

    # 1. PII scrubbing (always on).
    scrubbed = scrub_pii(text)

    # 2. Output safety: leaked prompt artifacts in the output suggest the
    #    model echoed or was steered by injected instructions.
    for pattern, desc in INJECTION_PATTERNS:
        if pattern.search(scrubbed):
            flags.append(f"output_safety:possible_prompt_leak:{desc}")
            break

    # 3. Claim grounding.
    citations = list(citations or [])
    for idx, claim in enumerate(claims or []):
        claim_text = str(claim.get("text", ""))
        sources = claim.get("sources") or []
        if sources:
            continue
        if not _claim_grounded(claim_text, citations):
            flags.append(f"ungrounded_claim:{idx}")

    # 4. Confidence threshold → abstain/escalate.
    abstain = False
    abstention_reason = None
    if confidence is not None and confidence < policy.min_confidence:
        abstain = True
        abstention_reason = (
            f"confidence {confidence:.2f} below threshold "
            f"{policy.min_confidence:.2f}; escalating for human review"
        )
        flags.append("low_confidence_abstain")

    return OutputVerdict(
        text=scrubbed,
        flags=flags,
        abstain=abstain,
        abstention_reason=abstention_reason,
    )

"""Input guardrails: injection/jailbreak detection, PII detection,
domain-scope enforcement, and input length/sanity limits.

Wraps the primitive pattern sets from
:mod:`ingredion_ai.governance.security` (kept as the single source of
truth for patterns) and adds policy-driven behavior:

- strictness levels tune which pattern families block vs. flag,
- domain-scope enforcement refuses clearly off-topic inputs,
- oversized inputs are refused before they reach any model.

Production equivalent: Azure AI Prompt Shields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from ingredion_ai.governance.security import (
    INJECTION_PATTERNS,
    PII_PATTERNS,
    scrub_pii,
)

from .policies import GuardrailPolicy, Strictness, load_policy

#: Extra jailbreak/prompt-extraction families beyond the base patterns.
EXTRA_INJECTION_PATTERNS = [
    (re.compile(r"role\s*play|role-play|pretend\s+(you\s+are|to\s+be)", re.I),
     "roleplay jailbreak"),
    (re.compile(r"(reveal|show|print|output).{0,40}(system\s+prompt|your\s+instructions)", re.I),
     "prompt extraction"),
    (re.compile(r"\bdeveloper\s+mode\b|\bdan\s+mode\b", re.I),
     "DAN/developer-mode jailbreak"),
    (re.compile(r"translate\s+.*\binstructions\b", re.I),
     "instruction smuggling via translation"),
]

#: Encoded-payload family (blocked only in strict mode; flagged otherwise).
ENCODED_PAYLOAD_PATTERNS = [
    (re.compile(r"base64\s*,\s*[A-Za-z0-9+/=]{20,}", re.I), "possible encoded payload"),
]

#: Food-manufacturing domain vocabulary for scope enforcement.
IN_DOMAIN_KEYWORDS = frozenset(
    """
    ingredient ingredients formulation reformulation reformulate
    recipe recipes formula formulas bakery beverage beverages
    drink drinks soda cola juice water bread cake cookie biscuit
    snack snacks cereal yogurt milk cheese soup sauce dressing
    confectionery frozen chilled ambient savory sweet
    sweetener sweeteners starch starches flour flours protein proteins
    sugar sugars sodium fat fats texture shelf-life shelf life
    clean label natural claims claim nutrition allergen allergens
    gluten dairy vegan plant-based plant based
    supply chain inventory forecast forecasts demand procurement
    plant plants warehouse warehouses quality assurance qa
    esg carbon sustainability emissions water energy regenerative
    agriculture sourcing traceability
    customer customers proposal proposals pricing price tech sheet
    crm account accounts opportunity pipeline
    fda efsa regulation regulations regulatory compliant compliance iso
    benchtop pilot scale-up manufacturing manufacture production
    """.split()
)

OFF_TOPIC_REFUSAL = (
    "I can only help with food-manufacturing topics (formulation, "
    "supply chain, ESG, customer proposals). Please rephrase your request "
    "within that scope."
)

TOO_LONG_REFUSAL = (
    "Input too long for safe processing; please shorten it and try again."
)


@dataclass
class InputVerdict:
    """Result of :func:`check_input`."""

    allowed: bool
    flags: List[str] = field(default_factory=list)
    refusal: Optional[str] = None
    scrubbed: str = ""  # PII-redacted copy, safe for logs


def _domain_score(text: str) -> int:
    words = set(re.findall(r"[a-z]+", text.lower()))
    return len(words & IN_DOMAIN_KEYWORDS)


def check_input(
    text: Optional[str],
    *,
    policy: Optional[GuardrailPolicy] = None,
    field_name: str = "input",
    check_domain: bool = True,
) -> InputVerdict:
    """Evaluate one user-supplied input string against the guardrail policy.

    Never raises: returns a verdict. ``allowed=False`` means the pipeline
    must reject the request (fail closed). Set ``check_domain=False`` for
    free-form prompts addressed to an already domain-scoped agent.
    """
    policy = policy or load_policy()
    text = text or ""

    # 1. Length / sanity limits (checked first: cheap, unconditional).
    if len(text) > policy.max_input_chars:
        return InputVerdict(
            allowed=False,
            flags=[f"{field_name}:input_too_long"],
            refusal=TOO_LONG_REFUSAL,
            scrubbed=scrub_pii(text[:500]),
        )

    flags: List[str] = []

    # 2. Injection / jailbreak detection.
    patterns = list(INJECTION_PATTERNS) + list(EXTRA_INJECTION_PATTERNS)
    if policy.strictness is Strictness.PERMISSIVE:
        # Permissive: only the blatant instruction-override family blocks.
        patterns = [p for p in patterns if "override" in p[1]]
    # Encoded payloads are handled separately below (block in strict,
    # notice otherwise) — never double-count them here.
    patterns = [p for p in patterns if "encoded payload" not in p[1]]
    for pattern, desc in patterns:
        if pattern.search(text):
            flags.append(f"{field_name}:injection:{desc}")
    encoded_hits = [
        desc for pattern, desc in ENCODED_PAYLOAD_PATTERNS if pattern.search(text)
    ]
    if encoded_hits:
        if policy.block_encoded_payloads:
            flags.append(f"{field_name}:injection:{encoded_hits[0]}")
        else:
            flags.append(f"{field_name}:notice:{encoded_hits[0]}")
    blocking_injection = [f for f in flags if ":injection:" in f]
    if blocking_injection:
        return InputVerdict(
            allowed=False,
            flags=flags,
            refusal=(
                "Input rejected by safety guardrails: "
                + "; ".join(sorted(set(blocking_injection)))
            ),
            scrubbed=scrub_pii(text[:500]),
        )

    # 3. PII detection in inputs (flag; block only in strict mode).
    pii_hits = [
        label for pattern, label in PII_PATTERNS if pattern.search(text)
    ]
    if pii_hits:
        flags.append(f"{field_name}:pii_detected")
        if policy.block_pii_input:
            return InputVerdict(
                allowed=False,
                flags=flags,
                refusal=(
                    "Input contains personal data; remove it and try again."
                ),
                scrubbed=scrub_pii(text[:500]),
            )

    # 4. Domain-scope enforcement (off-topic → safe refusal).
    # Only when requested: free-form prompts to an already domain-scoped
    # agent skip this (the agent's instructions are the scope).
    if check_domain and policy.domain_enforcement and len(text.strip()) >= 12:
        if _domain_score(text) == 0 and not _looks_like_greeting(text):
            return InputVerdict(
                allowed=False,
                flags=[f"{field_name}:off_topic"],
                refusal=OFF_TOPIC_REFUSAL,
                scrubbed=scrub_pii(text[:500]),
            )

    return InputVerdict(allowed=True, flags=flags, scrubbed=scrub_pii(text[:500]))


def _looks_like_greeting(text: str) -> bool:
    return bool(
        re.fullmatch(
            r"\s*(hi|hello|hey|good\s+(morning|afternoon|evening)|thanks|thank\s+you)[!.]?\s*",
            text,
            re.I,
        )
    )

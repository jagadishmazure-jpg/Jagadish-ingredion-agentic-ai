"""Simulated third-party vendor agent reachable over A2A (demo).

This module proves the A2A adapter does real cross-vendor work: it defines
a *vendor-owned* agent — a Dun & Bradstreet-style supplier-risk service —
with its own agent card, its own auth scopes, and a deterministic risk
engine. The vendor agent is registered on an ``A2AAdapter`` and reached
through the standard ``message/send`` path, with the adapter's bearer-token
auth and per-skill scope checks fully intact.

The vendor is simulated (no network) but the *protocol path is real*:
card discovery -> bearer auth -> scope check -> ``message/send`` ->
``tasks/get`` -> artifacts. In production the only change is the card URL
and the executor behind it; the calling side is identical.

All data is synthetic demo data.
"""

from __future__ import annotations

from typing import Any, Dict

from food_ingredients_ai.interop.a2a import A2AAdapter, AgentCard, AgentSkill

#: Key under which the vendor agent is registered in ``adapter.cards``.
VENDOR_AGENT_KEY = "vendor_risk"
VENDOR_SKILL_ID = "supplier_credit_check"
#: Scope the caller must hold to invoke the vendor skill.
VENDOR_SCOPE = "vendor:risk:read"

#: Country-risk loading added to the base score (0-100, higher = riskier).
COUNTRY_RISK_LOADING: Dict[str, int] = {"low": 0, "medium": 15, "high": 30}

RISK_TIER_LOW_MAX = 30
RISK_TIER_MEDIUM_MAX = 60


def score_supplier_risk(
    years_in_business: float = 0.0,
    past_defaults: int = 0,
    country_tier: str = "low",
) -> Dict[str, Any]:
    """Deterministic supplier risk score (0-100, higher = riskier).

    Transparent, explainable scoring a vendor would publish alongside the
    number: tenure reduces risk, past payment defaults add risk, and the
    supplier's country tier adds a fixed loading. The result cites every
    input so the calling enterprise can reproduce and audit it.
    """
    tier_key = (country_tier or "low").lower()
    if tier_key not in COUNTRY_RISK_LOADING:
        tier_key = "low"
    score = 50.0
    score -= min(2.0 * max(years_in_business, 0.0), 30.0)   # tenure helps
    score += min(25.0 * max(past_defaults, 0), 50.0)        # defaults hurt
    score += COUNTRY_RISK_LOADING[tier_key]                # country loading
    score = max(0.0, min(100.0, score))
    if score < RISK_TIER_LOW_MAX:
        tier = "low"
    elif score <= RISK_TIER_MEDIUM_MAX:
        tier = "medium"
    else:
        tier = "high"
    inputs = {
        "years_in_business": years_in_business,
        "past_defaults": past_defaults,
        "country_tier": tier_key,
    }
    report = (
        f"Supplier risk assessment (synthetic): score {score:.0f}/100 "
        f"({tier} risk). Tenure {years_in_business} years, "
        f"{past_defaults} past payment default(s), country tier '{tier_key}'. "
        f"Score = 50 - tenure credit - default penalty + country loading."
    )
    return {
        "risk_score": round(score, 1),
        "risk_tier": tier,
        "report": report,
        "inputs": inputs,
        "vendor": "demo-vendor-risk-agent",
    }


def build_vendor_card(
    base_url: str = "https://vendor.example.invalid/a2a",
) -> AgentCard:
    """Build the vendor agent's own agent card (vendor-published)."""
    card = AgentCard(
        name="vendor-risk-agent",
        description=(
            "Third-party supplier risk service (demo vendor): deterministic "
            "credit/risk scoring for suppliers from tenure, payment history, "
            "and country tier. Returns a scored report with cited inputs."
        ),
        url=f"{base_url}/vendor-risk-agent",
        version="1.2.0",
        skills=[
            AgentSkill(
                id=VENDOR_SKILL_ID,
                name="supplier_credit_check",
                description=(
                    "Score a supplier's credit risk (0-100) with a cited report."
                ),
                tags=["credit", "risk", "supplier", "procurement"],
                examples=["Credit check for supplier 'Acme Ingredients Co.'"],
                input_modes=["text/plain", "application/json"],
                output_modes=["text/plain", "application/json"],
            ),
        ],
        # The vendor declares which scopes a caller needs, per skill.
        skill_scopes={VENDOR_SKILL_ID: [VENDOR_SCOPE]},
    )
    return card


def vendor_risk_executor(
    message_text: str, context: Dict[str, Any]
) -> Dict[str, Any]:
    """The vendor's execution backend (simulated in-process for the demo).

    Takes the supplier attributes from the A2A message context, runs the
    deterministic risk engine, and returns the assessment as the
    blackboard the adapter formats into A2A artifacts.
    """
    supplier = context.get("supplier", {}) or {}
    assessment = score_supplier_risk(
        years_in_business=float(supplier.get("years_in_business", 0.0)),
        past_defaults=int(supplier.get("past_defaults", 0)),
        country_tier=str(supplier.get("country_tier", "low")),
    )
    return {
        "risk_assessment": assessment,
        "vendor_request": message_text,
        "supplier_name": supplier.get("name", "unknown"),
    }


def register_vendor_agent(adapter: A2AAdapter) -> A2AAdapter:
    """Register the vendor agent's card on an adapter instance.

    The adapter's ``message/send`` auth/scope machinery is untouched: the
    caller must still present a bearer token with ``vendor:risk:read``
    (see ``SKILL_SCOPES`` in ``food_ingredients_ai/interop/auth.py``).
    """
    adapter.cards[VENDOR_AGENT_KEY] = build_vendor_card()
    return adapter


def vendor_adapter() -> A2AAdapter:
    """Convenience: an adapter wired to the vendor's execution backend."""
    return register_vendor_agent(A2AAdapter(executor=vendor_risk_executor))

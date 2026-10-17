"""AI-agent identity pattern (demo, offline).

Models the identity architecture used when the agent service is deployed:
a human authenticates (Entra ID / OIDC), the service issues a short-lived,
scope-limited token bound to that human's identity, every sensitive action
is checked against the token's scopes at runtime, and the audit trail
attributes each machine action to both the agent and the originating human.

In the demo everything is local and deterministic; in production the token
issuance/validation moves to Entra ID + managed identity (see
docs/identity.md). No real cryptography here — expiry and scope checks only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional


@dataclass(frozen=True)
class AgentIdentity:
    """Identity of an agent execution: agent id + originating human."""

    agent_id: str
    human_subject: str  # e.g. Entra ID object id / UPN in production
    issued_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class ScopedToken:
    """Short-lived, scope-limited token for one agent execution (demo)."""

    token_id: str
    identity: AgentIdentity
    scopes: List[str]
    expires_at: datetime
    revoked: bool = False

    def is_valid(self, at: Optional[datetime] = None) -> bool:
        """Valid only if not revoked and not expired."""
        if self.revoked:
            return False
        now = at or datetime.now(timezone.utc)
        return now < self.expires_at

    def allows(self, scope: str, at: Optional[datetime] = None) -> bool:
        """Fine-grained runtime check: token must be valid and carry *scope*."""
        return self.is_valid(at) and scope in self.scopes


def issue_token(
    identity: AgentIdentity,
    scopes: List[str],
    ttl_minutes: int = 15,
) -> ScopedToken:
    """Issue a short-lived scoped token for *identity* (demo issuer)."""
    return ScopedToken(
        token_id=f"demo-{uuid.uuid4().hex[:12]}",
        identity=identity,
        scopes=list(scopes),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
    )


# Scope -> the policy actions it unlocks (demo mapping).
SCOPE_ACTIONS: Dict[str, List[str]] = {
    "reformulation:read": ["analyze_ingredients", "predict_texture_shelf_life",
                           "calculate_nutrition", "validate_claims"],
    "reformulation:draft": ["suggest_substitutes", "generate_documentation",
                            "estimate_cycle_time"],
    "supply:read": ["forecast_demand", "get_inventory"],
    "supply:plan": ["optimize_inventory", "schedule_production"],
    "esg:read": ["collect_esg", "calculate_carbon"],
    "esg:report": ["esg_report"],
    "advisor:read": ["recommend_ingredients", "estimate_pricing"],
    "advisor:propose": ["generate_sample_formula", "generate_tech_sheet"],
}


def authorize(token: ScopedToken, action: str) -> bool:
    """Runtime fine-grained check: does *token* unlock *action*?"""
    if not token.is_valid():
        return False
    return any(
        action in SCOPE_ACTIONS.get(scope, []) for scope in token.scopes
    )


def identity_attribution(token: ScopedToken, action: str) -> Dict[str, str]:
    """Identity-attributed audit fields for one machine action."""
    return {
        "agent_id": token.identity.agent_id,
        "human_subject": token.identity.human_subject,
        "token_id": token.token_id,
        "action": action,
    }

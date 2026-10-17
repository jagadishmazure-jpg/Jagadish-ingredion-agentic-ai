"""Inter-agent authentication & authorization (demo, offline).

Every agent-to-agent call must authenticate the caller and authorize the
requested skill/scope. This module provides:

- ``CallerIdentity``: the verified identity of a calling agent/service.
- ``issue_token`` / ``verify_token``: a JWT-shaped synthetic token for
  offline use and tests. **Production swap:** replace the internals of
  ``verify_token`` with OIDC validation against Entra ID's JWKS endpoint
  (``/.well-known/openid-configuration``); the interface stays the same.
  In AKS the caller would be a workload-identity-enabled service account
  and the adapter would validate the Entra ID access token instead.
- ``require_scopes``: enforce per-skill scopes (e.g. ``formulation:read``,
  ``proposal:write``), raising ``AuthorizationError`` on violations.

No real credentials anywhere: the demo signing key is a non-secret dev
constant overridable via ``DEMO_A2A_SIGNING_KEY``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List


class AuthenticationError(Exception):
    """Raised when a caller token is missing, malformed, expired, or forged."""


class AuthorizationError(Exception):
    """Raised when an authenticated caller lacks a required scope."""


DEMO_ISSUER = "demo-a2a-issuer"
# Demo-only dev signing key. NOT a secret, never used in production.
# Production uses Entra ID JWKS validation (see module docstring).
DEMO_SIGNING_KEY = os.environ.get("DEMO_A2A_SIGNING_KEY", "demo-only-dev-key-not-a-secret")


@dataclass(frozen=True)
class CallerIdentity:
    """Verified identity of an inter-agent caller (service identity)."""

    subject: str          # e.g. "svc:customer-advisor"
    scopes: frozenset      # e.g. frozenset({"proposal:read"})
    issuer: str
    expires_at: datetime

    def has_scopes(self, required: Iterable[str]) -> bool:
        return all(s in self.scopes for s in required)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def issue_token(
    subject: str,
    scopes: Iterable[str],
    ttl_seconds: int = 300,
    issuer: str = DEMO_ISSUER,
    issued_at: float | None = None,
) -> str:
    """Mint a short-lived synthetic JWT-shaped token (demo only)."""
    now = issued_at if issued_at is not None else time.time()
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": issuer,
        "sub": subject,
        "scopes": sorted(set(scopes)),
        "iat": int(now),
        "exp": int(now + ttl_seconds),
    }
    signing_input = (
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    )
    sig = hmac.new(
        DEMO_SIGNING_KEY.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    return signing_input + "." + _b64url_encode(sig)


def verify_token(token: str, issuer: str = DEMO_ISSUER) -> CallerIdentity:
    """Verify a synthetic token and return the caller identity.

    Raises ``AuthenticationError`` for missing/malformed/expired/forged
    tokens or issuer mismatch. Production replaces this body with Entra ID
    OIDC/JWKS validation (same interface, same exceptions).
    """
    if not token or not isinstance(token, str):
        raise AuthenticationError("missing bearer token")
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthenticationError("malformed token: expected 3 JWT segments")
    signing_input = parts[0] + "." + parts[1]
    try:
        provided_sig = _b64url_decode(parts[2])
        payload = json.loads(_b64url_decode(parts[1]))
    except Exception as exc:
        raise AuthenticationError(f"malformed token: {exc}") from exc
    expected_sig = hmac.new(
        DEMO_SIGNING_KEY.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(provided_sig, expected_sig):
        raise AuthenticationError("invalid token signature")
    if payload.get("iss") != issuer:
        raise AuthenticationError(
            f"unexpected issuer: {payload.get('iss')!r} (expected {issuer!r})"
        )
    now = int(time.time())
    if int(payload.get("exp", 0)) <= now:
        raise AuthenticationError("token expired")
    subject = payload.get("sub")
    if not subject:
        raise AuthenticationError("token missing subject")
    return CallerIdentity(
        subject=str(subject),
        scopes=frozenset(payload.get("scopes", [])),
        issuer=issuer,
        expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc),
    )


def require_scopes(identity: CallerIdentity, required: Iterable[str]) -> None:
    """Enforce that *identity* holds every scope in *required*.

    Raises ``AuthorizationError`` listing the missing scopes.
    """
    required = list(required)
    missing = [s for s in required if s not in identity.scopes]
    if missing:
        raise AuthorizationError(
            f"caller {identity.subject!r} missing required scope(s): "
            + ", ".join(sorted(missing))
        )


def authenticate_and_authorize(
    token: str | None, required_scopes: Iterable[str]
) -> CallerIdentity:
    """One-step helper: verify the token, then enforce *required_scopes*.

    Raises ``AuthenticationError`` for unauthenticated callers and
    ``AuthorizationError`` for out-of-scope requests.
    """
    if not token:
        raise AuthenticationError("unauthenticated: bearer token required")
    identity = verify_token(token)
    require_scopes(identity, required_scopes)
    return identity


# -- scope catalog (per agent skill) -----------------------------------------

#: Required scopes per agent skill, declared on the agent cards.
SKILL_SCOPES: Dict[str, Dict[str, List[str]]] = {
    "rd_formulation": {
        "reformulate": ["formulation:write"],   # high-impact: new formulations
        "validate-claims": ["formulation:read"],
    },
    "supply_chain": {
        "forecast-demand": ["supply:read"],
    },
    "esg": {
        "esg-report": ["esg:read"],
    },
    "customer_advisor": {
        "estimate-pricing": ["proposal:read"],
    },
    "mcp": {
        "invoke": ["mcp:invoke"],  # MCP tools/call when server auth is on
    },
    "vendor_risk": {
        # Third-party vendor agent skill (see interop/vendor_agents.py):
        # the *vendor* declares this scope on its own agent card.
        "supplier_credit_check": ["vendor:risk:read"],
    },
}

#: Extra scopes for high-impact outputs (proposal/report generation).
HIGH_IMPACT_SCOPES: Dict[str, List[str]] = {
    "customer_advisor:generate_proposal": ["proposal:write"],
    "esg:publish_report": ["esg:write"],
    "rd_formulation:reformulate": ["formulation:write"],
}


def required_scopes_for(agent_name: str, skill_id: str) -> List[str]:
    """Look up the required scopes for an agent skill (KeyError if unknown)."""
    return list(SKILL_SCOPES[agent_name][skill_id])


def describe_auth_requirements() -> Dict[str, Any]:
    """Human-readable auth-requirements summary (for docs/cards)."""
    return {
        "scheme": "bearer (demo synthetic JWT; OIDC/Entra ID in production)",
        "skill_scopes": {a: dict(s) for a, s in SKILL_SCOPES.items()},
        "note": "High-impact outputs (new formulations, customer proposals, "
        "published ESG reports) additionally require write scopes and a "
        "human-in-the-loop approval gate (see governance/approvals.py).",
    }

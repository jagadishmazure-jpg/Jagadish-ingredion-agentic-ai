"""Interoperability: A2A protocol adapter for the demo agents."""

from food_ingredients_ai.interop.a2a import (
    A2AAdapter,
    AgentCard,
    AgentSkill,
    FakeTransport,
    build_agent_cards,
)
from food_ingredients_ai.interop.auth import (
    HIGH_IMPACT_SCOPES,
    SKILL_SCOPES,
    AuthenticationError,
    AuthorizationError,
    CallerIdentity,
    authenticate_and_authorize,
    describe_auth_requirements,
    issue_token,
    require_scopes,
    required_scopes_for,
    verify_token,
)
from food_ingredients_ai.interop.mcp import (
    MCP_PROTOCOL_VERSION,
    InProcessClient,
    MCPServer,
)
from food_ingredients_ai.interop.vendor_agents import (
    VENDOR_AGENT_KEY,
    VENDOR_SCOPE,
    VENDOR_SKILL_ID,
    build_vendor_card,
    register_vendor_agent,
    score_supplier_risk,
    vendor_adapter,
    vendor_risk_executor,
)

__all__ = [
    "A2AAdapter",
    "AgentCard",
    "AgentSkill",
    "FakeTransport",
    "build_agent_cards",
    "MCPServer",
    "InProcessClient",
    "MCP_PROTOCOL_VERSION",
    "SKILL_SCOPES",
    "HIGH_IMPACT_SCOPES",
    "AuthenticationError",
    "AuthorizationError",
    "CallerIdentity",
    "authenticate_and_authorize",
    "describe_auth_requirements",
    "issue_token",
    "required_scopes_for",
    "require_scopes",
    "verify_token",
    "VENDOR_AGENT_KEY",
    "VENDOR_SCOPE",
    "VENDOR_SKILL_ID",
    "build_vendor_card",
    "register_vendor_agent",
    "score_supplier_risk",
    "vendor_adapter",
    "vendor_risk_executor",
]

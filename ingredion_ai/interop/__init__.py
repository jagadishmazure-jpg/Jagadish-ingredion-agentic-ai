"""Interoperability: A2A protocol adapter for the demo agents."""

from ingredion_ai.interop.a2a import (
    A2AAdapter,
    AgentCard,
    AgentSkill,
    FakeTransport,
    build_agent_cards,
)
from ingredion_ai.interop.mcp import (
    MCPServer,
    InProcessClient,
    MCP_PROTOCOL_VERSION,
)

from ingredion_ai.interop.auth import (
    SKILL_SCOPES,
    HIGH_IMPACT_SCOPES,
    AuthenticationError,
    AuthorizationError,
    CallerIdentity,
    authenticate_and_authorize,
    describe_auth_requirements,
    issue_token,
    required_scopes_for,
    require_scopes,
    verify_token,
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
]

"""HTTP agent service (FastAPI) + demo web UI.

Exposes the Microsoft Agent Framework 1.0 workflow and the four domain
agents over HTTP, with bearer-token auth enforced by
:mod:`ingredion_ai.interop.auth` (demo synthetic JWT offline; Entra ID
OIDC validation in production — see ``docs/identity.md``).

Endpoints:

- ``GET /`` — demo web UI (single page).
- ``GET /api/health`` — liveness/readiness probe (public).
- ``GET /api/scenarios`` — available demo scenarios (public).
- ``GET /api/agent-cards`` — the four A2A agent cards (public discovery).
- ``GET /.well-known/agent.json`` — A2A discovery document (public).
- ``POST /api/reformulate`` — full workflow run (auth: ``formulation:write``).
- ``POST /api/agents/{agent}/run`` — single-agent run (auth: skill scopes).

Offline by default (scripted fake chat clients, deterministic). Pass
``"live": true`` to use Azure OpenAI (needs the ``.env`` variables from
``.env.example``).
"""

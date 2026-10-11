# Identity & Access

> **Disclaimer.** Independent portfolio demo; all data synthetic; not
> affiliated with Ingredion Incorporated. Identity concepts below are
> paraphrased in our own words — no passages copied from vendor ebooks.

This project demonstrates identity at **two layers**: (1) the agent API
service and its Azure dependencies, and (2) agent-to-agent calls.

## 1. Service identity (API + Azure)

- **User auth:** the agent API service authenticates users via **Entra ID /
  OIDC** (authorization-code flow for interactive users). The service never
  mints its own user identities.
- **Service → Azure:** the service accesses Azure OpenAI and Key Vault with
  **managed identity** (system-assigned where possible), so no API keys or
  connection strings live in config. Local/dev falls back to
  `DefaultAzureCredential` (see `docs/foundry-deployment.md`).
- **Secrets:** `governance/security.py` — `require_env()` reads secrets from
  the environment only; `assert_no_hardcoded_secrets()` fails loudly if
  secret-shaped values appear in code. CI runs this check.
- **RBAC:** Azure RBAC roles scope what the managed identity can do
  (e.g. Cognitive Services OpenAI User on the Foundry project, Key Vault
  Secrets User on the vault). Documented for the AKS deployment in
  `docs/foundry-deployment.md`; Terraform/K8s manifests (later phase) will
  wire: `azurerm_role_assignment` for the workload identity + Kubernetes
  `ServiceAccount` federated with Entra ID via **workload identity**.

## 2. Inter-agent authn/authz (A2A)

Following the identity-for-AI-agents pattern (authenticate the user →
issue short-lived scoped tokens → fine-grained runtime checks → human
approval for sensitive actions → identity-attributed audit):

1. **Authenticate:** a calling agent presents a bearer token on every A2A
   `message/send` call. Offline/tests use the synthetic JWT-shaped token in
   `ingredion_ai/interop/auth.py` (`issue_token` / `verify_token`, HMAC
   demo key — not a secret). **Production swap:** `verify_token` keeps its
   interface but validates against Entra ID's OIDC JWKS endpoint; in AKS the
   caller is a workload-identity service account.
2. **Authorize:** each agent card declares `authentication.skillScopes`
   (see `AgentCard.to_dict()`), e.g. `reformulate → ["formulation:write"]`.
   `A2AAdapter.message_send` verifies the token and enforces the skill's
   scopes: missing token → 401-style error, wrong scope → 403-style error
   (`AuthenticationError` / `AuthorizationError`).
3. **Human approval:** high-impact skills (new formulations, customer
   proposals, published ESG reports) additionally require the HITL approval
   gate (`governance/approvals.py`) — a token alone is not enough.
4. **Audit:** the verified caller identity (`subject`, `scopes`) is attached
   to the A2A task record and flows into the hash-chained audit trail
   (`governance/audit.py`) via `identity_attribution()`.

### Scope catalog

| Scope | Meaning |
|---|---|
| `formulation:read` / `formulation:write` | Read vs. create reformulation outputs |
| `supply:read` | Demand/inventory planning data |
| `esg:read` / `esg:write` | Read vs. publish ESG reports |
| `proposal:read` / `proposal:write` | Read vs. generate customer proposals |

Write scopes are the high-impact set; see `interop/auth.py::HIGH_IMPACT_SCOPES`.

## 3. Where Terraform/K8s wire this (deployment track)

- Terraform (`infra/terraform/`): user-assigned managed identity for the
  agent service, federated credential bound to the AKS service account
  (`system:serviceaccount:ingredion-ai:ingredion-svc`), `azurerm_role_assignment`
  for Azure OpenAI (`Cognitive Services OpenAI User`) + Key Vault
  (`Key Vault Secrets User`) + ACR (`AcrPull` for the kubelet).
- Kubernetes (`infra/k8s/`): `ServiceAccount` annotated with the workload
  identity client ID, secrets via the Secrets Store CSI driver (never
  env-baked), PDB + anti-affinity + HPA for availability.
- Service auth (`ingredion_ai/service/app.py`): HTTP Bearer <redacted> on
  `POST /api/reformulate` and `POST /api/agents/{agent}/run`, verified by
  `interop/auth.py` (demo synthetic JWT offline; production swaps
  `verify_token` for Entra ID OIDC/JWKS validation — same interface).
  Discovery endpoints (`/api/health`, `/api/agent-cards`,
  `/.well-known/agent.json`) stay public per A2A.
- Reliability (`docs/reliability.md`): retry + jitter + circuit breaker on
  the live-LLM path with graceful offline fallback; rate limiting (429);
  idempotency keys; request timeouts.
- Stack mapping: [docs/stack-alignment.md](stack-alignment.md) maps every
  box of the Microsoft Azure Agentic AI Stack diagram to this repo
  (implemented vs. demo path vs. documented production path).

## Module map

| Concern | Module |
|---|---|
| Service-side identity pattern | `governance/identity.py` (`AgentIdentity`, `ScopedToken`, `authorize`) |
| A2A bearer tokens + scope enforcement | `interop/auth.py` |
| Auth declarations on cards | `interop/a2a.py` (`AgentCard.skill_scopes`) |
| Input sanitization / PII scrubbing / secret checks | `governance/security.py` |

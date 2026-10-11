# Security

Threat model, controls inventory, residual risks, and the production
hardening checklist for the Ingredion agentic AI demo. All data is
synthetic; the demo signing key is a non-secret dev constant.

## 1. Threat model

| # | Threat | Impact | Likelihood (demo) |
|---|--------|--------|-------------------|
| T1 | Prompt injection / jailbreak via API inputs or A2A messages | Agent misdirection, unsafe outputs | Medium |
| T2 | PII leakage in agent outputs, logs, or audit trail | Privacy violation | Low (synthetic data) |
| T3 | Unauthorized API / agent invocation (missing/broad auth) | Data exposure, resource abuse | Medium |
| T4 | Ungrounded model claims presented as fact | Bad decisions on false premises | Medium |
| T5 | Hardcoded secrets committed to the repo | Credential compromise | Low (env-only policy) |
| T6 | Container escape / privilege escalation in AKS | Cluster compromise | Low |
| T7 | Dependency supply-chain vulnerability | Code execution via lib | Low |
| T8 | DoS via oversized requests / rate abuse | Service degradation | Medium |
| T9 | Information disclosure via error messages | Internal path/stack leakage | Low |
| T10 | XSS in the demo UI via agent output | Session/token theft in browser | Low |

Out of scope for the demo (documented, not implemented): DDoS at the
edge (covered by Front Door), insider threats, model-weight theft.

## 2. Controls inventory

| Threat | Control | Location |
|--------|---------|----------|
| T1 | Input guardrails: injection/jailbreak patterns, encoded-payload rules, length limits — fail closed (400) | `guardrails/input.py`, pipeline stage 2 |
| T1 | Domain-scope enforcement: off-topic inputs refused | `guardrails/input.py` |
| T1 | Per-agent strictness policies (permissive/standard/strict) via env | `guardrails/policies.py` |
| T2 | PII scrubbing on all output paths (API bodies, UI, logs) | `guardrails/output.py`, `governance/security.py` |
| T2 | PII detection on inputs (flag; block in strict) | `guardrails/input.py` |
| T3 | Bearer-token auth + per-skill scopes on all write/run endpoints | `service/app.py` + `interop/auth.py` |
| T3 | A2A `message/send` requires token + scopes; `tasks/get`/`cancel` bound to the creating caller (or `a2a:admin`) | `interop/a2a.py` |
| T3 | MCP `tools/call` supports `require_auth` (Bearer + `mcp:invoke` scope); mandatory for any network transport | `interop/mcp.py` |
| T3 | Per-client rate limiting (429 + Retry-After) on all mutating routes | `service/reliability.py` |
| T3 | Human-in-the-loop approval gates for high-impact actions | `governance/approvals.py`, `legacy/autonomy.py` |
| T4 | Claim-grounding check: claims must trace to RAG citations or sources | `guardrails/output.py` |
| T4 | Confidence thresholds → abstain/escalate | `guardrails/output.py` |
| T4 | RAG grounding citations attached to every pipeline response | `service/pipeline.py` stage 4 |
| T5 | Env-only secrets; `assert_no_hardcoded_secrets` scan in the test suite | `governance/security.py`, `.env.example` |
| T5 | Secrets via Key Vault CSI (AKS) / APIM named values; ACR admin keys off | `infra/k8s/`, `infra/terraform/` |
| T6 | Non-root user, `runAsNonRoot`, `RuntimeDefault` seccomp, `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem`, `drop: [ALL]` | `Dockerfile`, `infra/k8s/deployment.yaml` |
| T6 | Base image pinned by digest | `Dockerfile` |
| T7 | `pip audit` clean on project deps (only sandbox `pip` itself flagged — environmental) | `pyproject.toml` |
| T8 | Request body size limit (413 over 1 MiB default) | `service/app.py` |
| T8 | Front Door WAF (OWASP + bot manager, Prevention) + APIM rate limits | `infra/terraform/` |
| T9 | Global 500 handler: generic message, traceback logged server-side only; timeouts → 504 | `service/app.py` |
| T10 | Output escaping (`esc()` incl. quotes) in the demo UI; `textContent` for status | `service/ui.py` |
| T10 | Security headers: `nosniff`, `DENY` framing, strict referrer policy | `service/app.py` |

### Guardrail → Azure production mapping

| This repo | Azure equivalent in production |
|-----------|-------------------------------|
| `guardrails/input.py` (Prompt Shields analogue) | **Azure AI Prompt Shields** — indirect/direct attack detection on inputs |
| `guardrails/output.py` (Content Safety analogue) | **Azure AI Content Safety** — hate/sexual/violence/self-harm filters + PII redaction on outputs |
| `guardrails/policies.py` (Foundry Guardrails analogue) | **Foundry Guardrails** — policy-as-code, rai-policy enforcement |
| `interop/auth.py` synthetic JWT | **Microsoft Entra ID** OIDC/JWKS validation (same interface) |
| `service` rate limiter | **API Management** rate-limit + quota policies (already in `infra/terraform/apim.tf`) |
| `observability/` tracing | **Application Insights** + Foundry Observability |

## 3. Residual risks (accepted for the demo)

1. **Synthetic JWT, not Entra ID.** The HMAC dev key is not a secret, but
   anyone holding it can mint tokens. Production must swap
   `verify_token` for Entra ID JWKS validation (interface unchanged).
2. **MCP auth off by default** for local stdio use. Any network transport
   (HTTP/SSE) must construct `MCPServer(require_auth=True)`.
3. **A2A task IDs are 48-bit** — unguessable in practice, but
   authorization (caller binding) is the real control, not secrecy.
4. **Content Safety categories** (hate/violence/etc.) are not implemented
   locally — the demo relies on pattern guardrails; production needs the
   Azure Content Safety API.
5. **Terraform is unvalidated** (no `terraform` binary in the build
   environment) — run `terraform validate` + `plan` before first apply.
6. **Playwright UI tests need a browser** — they typecheck but don't run
   in this sandbox; they run in CI via `qa.yml`.
7. **Session IDs are client-supplied** (`X-Session-Id`) — acceptable
   because sessions hold only turn counts/intents, no sensitive state.
8. **`degraded_reason`** may include live-LLM exception text — only in
   live mode; review before exposing broadly.

## 4. Production hardening checklist

- [ ] Replace `verify_token` internals with Entra ID OIDC/JWKS validation;
      rotate/remove `DEMO_A2A_SIGNING_KEY`.
- [ ] Enable `MCPServer(require_auth=True)` on every non-stdio transport.
- [ ] Wire Azure AI Content Safety + Prompt Shields in front of the
      service (or via Foundry Guardrails policies).
- [ ] Set `SERVICE_CORS_ORIGINS` explicitly if cross-origin clients exist
      (default is same-origin only — do not use `*`).
- [ ] Enable HSTS at the edge (Front Door / ingress TLS termination).
- [ ] `terraform validate` + `plan`; enable Azure Defender for Containers;
      add image scanning (ACR Tasks / Defender) to CI.
- [ ] Secret rotation runbook for the Azure OpenAI key fallback; prefer
      workload identity (already primary).
- [ ] Pin production image digests in `deploy.yml` (`img:tag@sha256:…`).
- [ ] Tune WAF from Detection → Prevention after a burn-in window;
      review APIM rate-limit quotas against load tests.
- [ ] Ship `/metrics` to Azure Monitor via Prometheus scraping or the
      OpenTelemetry collector; set up the burn-rate alerts in
      `infra/monitoring/prometheus-rules.yaml`.
- [ ] Restrict `readOnlyRootFilesystem` exceptions: if `SERVICE_AUDIT_LOG`
      points at a file, mount a writable volume for that path only.
- [ ] Run the Playwright UI suite in CI (`qa.yml`) once browser
      installation is available.

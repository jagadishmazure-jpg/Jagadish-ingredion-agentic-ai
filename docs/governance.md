# Governance

> **Disclaimer.** Independent portfolio demo; synthetic data only. These
> controls are real code, not documentation theater — every item below is
> exercised by tests.

## Policy engine (`governance/policy.py`)

Allow/deny lists **per agent**. `PolicyEngine.check_action(agent, action)`
→ `(allowed, reason)`. Examples: the R&D agent may analyze and recommend
but may not publish customer-facing claims without validation; the ESG
agent may draft reports but not publish them. Denied actions raise before
any tool runs.

## Human-in-the-loop approvals (`governance/approvals.py`)

High-impact outputs require approval:

| Output type | Gate |
|---|---|
| New formulations | `requires_approval("new_formulation")` → True |
| Customer proposals | `requires_approval("customer_proposal")` → True |
| ESG reports (publish) | `requires_approval("esg_report")` → True |
| Read-only analysis | No gate |

`ApprovalGate` records `ApprovalRecord`s (approver, decision, timestamp).
Offline/tests use the simulated approver; production wires a human reviewer.
The HITL loop (`loops/hitl.py`) re-requests until approved/rejected.

## Audit trail (`governance/audit.py`)

Append-only **JSONL** log; each entry hash-chains to the previous
(`_entry_hash`), so tampering breaks the chain. Entries carry timestamp,
actor (agent name), action, and — for A2A calls — the verified caller
identity (`interop/auth.py::identity_attribution`). Verify with
`AuditTrail.verify_chain()`.

## Security (`governance/security.py`)

- **Input sanitizer:** `sanitize_input()` strips prompt-injection patterns
  (instruction overrides, role-play jailbreaks, tool-use smuggling) and
  reports what it removed. Run on all agent inputs.
- **PII scrubber:** `scrub_pii()` redacts emails, phones, and ID-like
  patterns from outputs.
- **Secrets:** `require_env()` reads secrets from the environment only;
  `assert_no_hardcoded_secrets()` scans the tree and fails loudly on
  secret-shaped literals.

## Identity (`governance/identity.py` + `interop/auth.py`)

`AgentIdentity` + short-lived `ScopedToken` (the Auth0 pattern);
`authorize()` checks scopes per action. A2A calls carry bearer tokens with
per-skill scopes declared on agent cards. Full pattern in
`docs/identity.md`.

## RBAC / managed identity (deployment)

Documented in `docs/identity.md` §1/§3 and `docs/foundry-deployment.md`:
Entra ID/OIDC for users, managed identity for service→Azure, workload
identity in AKS, Terraform-managed role assignments (later phase).

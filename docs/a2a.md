# Agent-to-Agent (A2A) Interoperability

This project implements the Google Agent2Agent (A2A) protocol so the
enterprise agents can delegate work to — and be discovered by — agents
outside the organization: vendor pre-built agents, partner services, and
platform agents (Copilot Studio, Salesforce Agentforce, ServiceNow).

Complementary protocols:

- **A2A** (this document): agent → agent delegation (task lifecycle).
- **MCP** (`docs/integrations.md`): agent → tool invocation.
- **Auth** (`food_ingredients_ai/interop/auth.py`): bearer tokens with per-skill
  scopes; OIDC/Entra ID in production, synthetic JWT in the demo.

## How two enterprise agents talk

The sequence is the same whether the counterparty is in-house or a
third-party vendor:

1. **Discovery** — the vendor agent publishes an **agent card** (JSON at
   `/.well-known/agent.json`): name, description, skills, input/output
   modes, and the auth schemes + per-skill scopes a caller needs.
   See `A2AAdapter.get_agent_card()` / `build_agent_cards()`.
2. **Auth** — the caller presents a bearer token; the adapter verifies it
   and enforces the skill's declared scopes. Unauthenticated callers get a
   401-style error, out-of-scope callers a 403-style error.
3. **Delegate** — `message/send` creates a task from the caller's message;
   the task records the caller's identity (`caller.subject`, `caller.scopes`)
   for the audit trail.
4. **Track** — `tasks/get` polls the task (`submitted → working →
   completed | failed`); `tasks/cancel` aborts non-terminal tasks. Task
   access requires the creator's token (or `a2a:admin`).
5. **Result** — the vendor's blackboard is formatted into typed **artifacts**
   (data parts) that the calling workflow consumes.

## Trust model

No anonymous agents. Every cross-agent call is authenticated,
scope-checked against the *vendor-declared* requirements, and
identity-attributed on the task record, which feeds the governance audit
trail (`governance/audit.py`). Scope names are namespaced per owner
(`formulation:write` for enterprise agents, `vendor:risk:read` for the
vendor agent) so a vendor can never escalate into enterprise write scopes.

## Demo: cross-vendor handoff in procurement

`food_ingredients_ai/interop/vendor_agents.py` defines a simulated third-party
**vendor risk agent** (Dun & Bradstreet-style supplier credit scoring) with
its own card, its own scope (`vendor:risk:read`), and a deterministic risk
engine. `food_ingredients_ai/graph/vendor_risk_graph.py` runs the handoff:

```
discover_vendor --> risk_check --(low/medium risk)--> procurement_handoff --> done
                       |
                       +--(high risk)--> risk_blocked
                       |
                       +--(vendor error)--> vendor_error
```

- The procurement agent discovers the vendor card, authenticates, and sends
  a `supplier_credit_check` task with the supplier's attributes.
- **Low/medium risk** → the flow continues into the existing procurement
  graph (demand validation → policy/budget check → PO or approval).
- **High risk** → the requisition is blocked with the vendor's cited
  report (score, inputs, and formula) attached to the terminal state.
- Every delegation is recorded in `a2a_calls` with the task id, skill,
  caller identity, and verdict.

Run it:

```python
from food_ingredients_ai.graph.vendor_risk_graph import (
    run_vendor_risk_graph, LOW_RISK_SUPPLIER, HIGH_RISK_SUPPLIER,
)
run_vendor_risk_graph(supplier=LOW_RISK_SUPPLIER)   # -> po_issued
run_vendor_risk_graph(supplier=HIGH_RISK_SUPPLIER)  # -> risk_blocked
```

## Production path

- Replace the demo signing key with Entra ID OIDC/JWKS validation
  (same `verify_token` interface; see `auth.py`).
- Serve agent cards at `/.well-known/agent.json` behind the API gateway
  (`service/`) with WAF/Front Door in front.
- Point vendor card URLs at the vendor's real A2A endpoints and swap the
  in-process executor for an HTTP transport; the calling graph code is
  unchanged.

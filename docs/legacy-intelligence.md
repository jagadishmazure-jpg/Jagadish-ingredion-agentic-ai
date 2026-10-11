# Legacy Intelligence Layer: Wrap, Don't Replace

How this project puts an intelligence layer on top of traditional software
(SAP, CRM, LIMS, PLM, MES) and walks it toward autonomy — without
rip-and-replace.

> All systems referenced are synthetic demo doubles. The pattern is what
> transfers to production.

## The pattern

Enterprises run on decades of traditional software. Replacing it is
expensive, risky, and usually unnecessary. The intelligence layer wraps it:

```
Agent  →  Capability Catalog  →  LegacyBridge  →  Traditional system
                (versioned          (uniform envelope:
                 tools)             timeouts, error translation,
                                    health checks)
```

1. **Bridge** (`ingredion_ai/legacy/bridge.py`) — one wrapper per system.
   Request/response mapping, timeout enforcement, error translation into a
   stable `LegacyError` code, health checks. The agent never sees transport
   details.
2. **Catalog** (`ingredion_ai/legacy/catalog.py`) — legacy operations become
   versioned, JSON-schema-described function-tools. Deprecation is explicit,
   so consumers migrate on a schedule.
3. **CDC** (`ingredion_ai/legacy/cdc.py`) — legacy events (DB changes, webhooks)
   become agent triggers via a deduplicating change feed.
4. **Autonomy ladder** (`ingredion_ai/legacy/autonomy.py`) — L0→L3 with
   evidence-driven promotion.

The existing CRM/SAP adapters were migrated onto `LegacyBridge` as the first
two bridges (`CRMBridge`, `SAPBridge`) — composition, not rewrites.

## The autonomy ladder

| Level | Name | Who acts | Human role |
|---|---|---|---|
| L0 | Manual | Human | Agent drafts only |
| L1 | Assist | Human | Agent drafts + recommends; human decides |
| L2 | Augment | Agent | Acts inside guardrails; human reviews |
| L3 | Autonomous | Agent | Acts; human audits afterwards |

**Promotion criteria** (all must hold to move up one level): mean eval score
≥ 0.9, ≥ 5 approvals, ≥ 20 runs, 0 incidents. Structural gates: L2+ requires
guardrails enabled; L3 additionally requires an audit trail and a rollback
plan.

**Enforcement** (`AutonomyController.decide`): the governance policy engine is
consulted first — a denied action stays denied at every level. High-impact
actions always require approval, even at L3. Actions above a workflow's
`max_impact` require approval.

## Phased rollout plan

1. **Wrap (L0/L1):** bridge one system read-only (e.g. SAP material/inventory
   reads). Agents draft; humans decide. Measure: eval scores, approval rate.
2. **Harden (L1→L2):** add guardrails, schema validation, retries/fallbacks.
   Promote when criteria clear. Humans review agent actions.
3. **Automate (L2→L3):** require audit trail + rollback plan. Agent acts;
   humans audit via the hash-chained audit log and incident metrics.
4. **Expand:** register the next system's operations in the catalog; repeat.
   Never promote two levels at once.

## Worked example: SAP order check, L1 → L3

- **L1:** supply-chain agent calls `sap.get_inventory` (bridge) and drafts a
  reorder recommendation; the planner approves in the HITL gate.
- **L2:** after 25 runs at ≥ 0.93 eval with 8 approvals and 0 incidents, the
  workflow promotes. The agent now checks inventory and drafts POs inside
  guardrails (policy: `place_order` still denied — drafting only); the planner
  reviews each draft.
- **L3:** with audit trail + rollback plan ("reverse the PO in SAP") in place,
  low/medium-impact checks run autonomously; every action is audit-logged and
  high-impact steps still require approval.

## Production path

| Demo | Production |
|---|---|
| `SyntheticLegacyBridge` | Real transport (RFC/ODBC/REST) in `invoke()` |
| Scripted CDC source | Debezium / Event Hubs consumer |
| Demo webhook secret | Key Vault-backed secret, real HMAC |
| In-memory catalog | Catalog service backed by a registry DB |
| Synthetic eval scores | Production eval pipeline scores |

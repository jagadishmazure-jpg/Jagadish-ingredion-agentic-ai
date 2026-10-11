# Agent Control Plane

## The problem: agents overstepping

Industry data puts agentic AI at a growing share of enterprise AI value —
while only a small fraction of companies have full runtime controls over
what their agents do. The failure mode is not a bad answer; it is a
well-spoken agent that takes too many actions, spends too much money,
calls tools it was never meant to touch, or keeps running when it should
have stopped.

Content guardrails (`ingredion_ai/guardrails/`) screen *what* goes in and
out of an agent. The control plane governs *behavior* at runtime: what an
agent is allowed to **do**, how often, at what cost — and gives a human an
immediate halt button.

## Where the gate sits

```
pipeline stage 5 (tool calls)
        │
        ▼
┌─────────────────────┐
│  EnforcementGate    │◄── kill switch → circuit → budgets (in order)
│  .authorize()       │
└─────────┬───────────┘
          │ allowed
          ▼
   tool executes ──► outcome feeds back to circuit breaker
          │
          ▼
   decision appended to ControlLedger (hash-chained)
```

Pipeline stages 2 and 6 run the *content* guardrails (prompt injection,
PII). The control plane wraps stage 5: no tool call executes without a
decision from the gate. Denials short-circuit — a halted agent never
consumes budget, and a tripped circuit never reaches the spend check.

## The five components

| Component | Module | What it does |
|---|---|---|
| Action budgets & spend caps | `controlplane/budgets.py` | Per-agent limits: max tool calls per run / hour / day, max USD per run / day. Denies before overruns. |
| Circuit breaker | `controlplane/circuit.py` | Trips open when the failure rate in a sliding window exceeds threshold; half-open probe tests recovery. |
| Kill switch | `controlplane/killswitch.py` | Immediate human halt — global or per-agent. Beats every other check. |
| Behavior drift | `controlplane/drift.py` | Flags when an agent's recent actions diverge from its baseline histogram (unseen-action ratio). |
| Control ledger | `controlplane/ledger.py` | Append-only, hash-chained log of every allow/deny decision — the first artifact an incident review asks for. |

All components are deterministic and offline-safe: injectable clocks,
in-memory state, no network calls. The 25+ tests in
`tests/test_controlplane.py` run in milliseconds.

## Usage: wiring the gate around tool execution

```python
from ingredion_ai.controlplane import (
    BudgetManager, CircuitBreaker, ControlLedger, EnforcementGate, KillSwitch,
)

gate = EnforcementGate(
    killswitch=KillSwitch(),
    circuit=CircuitBreaker(failure_threshold=5, window_seconds=60),
    budgets=BudgetManager(),          # defaults: 50/run, 200/hr, 1000/day, $5/run, $50/day
    ledger=ControlLedger(),
)

def run_tool(agent_id: str, tool_name: str, estimated_cost: float, run_id: str):
    decision = gate.authorize(agent_id, tool_name, estimated_cost, run_id)
    if not decision["allowed"]:
        return {"error": decision["reason"]}   # denied: never executed
    try:
        result = execute_tool(tool_name)       # the real call
    except Exception as exc:
        gate.report_outcome(agent_id, tool_name, success=False)
        raise
    gate.report_outcome(agent_id, tool_name, success=True)
    return result

# Emergency stop for one misbehaving agent:
gate.killswitch.engage("supply_chain")
```

## Operating notes

- **Budgets are guardrails, not targets.** Set per-run limits from the
  agent's normal profile (see `budgets.usage()`), then tighten.
- **Circuit thresholds** should reflect the tool's natural flakiness —
  a 5%-flaky external API needs a wider window than a deterministic
  internal lookup.
- **Drift detection** needs a warm baseline (default: 20 actions) before
  it can flag anything; reset it deliberately after shipping an intended
  behavior change.
- **The ledger is the incident-review starting point**: every denial
  carries the exact check and reason that fired.

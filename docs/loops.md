# Loop engineering: reflection and human-in-the-loop

Two small, composable control patterns used across the demo, both fully
offline and deterministic (stdlib only, no network, no LLM calls).

## Reflection loop (`ingredion_ai/loops/reflection.py`)

```
draft_fn() -> draft -> critique_fn(draft) -> approved? -yes-> result
                                    | no
                                    v
                          revise_fn(draft, critique) -> draft (loop)
```

`reflection_loop(draft_fn, critique_fn, revise_fn, max_iterations=3)`
repeatedly drafts, critiques, and revises. The critique must return a dict
with an `"approved"` bool. The loop returns:

```python
{"result": <final draft>, "iterations": <n>, "approved": <bool>, "critiques": [...]}
```

`iterations` counts draft evaluations (the initial draft is iteration 1);
the loop exits early on approval or when `max_iterations` is exhausted
(`approved=False` in that case).

### Domain wiring: `reflective_reformulate(formula_id="sweet_bakery_cake")`

Binds the loop to the R&D formulation agent's real `execute()` paths:

- **draft** — `RDFormulationAgent().execute("suggest_substitutes", {"formula_id": ...})`
- **critique** — runs `analyze_ingredients` and checks that *every* flagged
  non-clean ingredient has a substitution (`action == "substitute"`) or an
  explicit removal reason (`action == "remove"` + `reason`). Approved iff
  coverage is complete.
- **revise** — re-runs the deterministic suggestion path.

Convergence note: the demo substitution map is total (every known flagged
ingredient maps to a clean-label alternative or an explicit removal), so
coverage is complete on the first draft and the loop approves immediately.
The revise path is kept for the general pattern (mocks, future heuristic
revise steps); the iteration bound guarantees the loop cannot spin forever.

### When to use

- Output **quality gates** where a cheap rule can judge a draft: coverage
  checks, schema/format checks, claim-validity checks.
- Iterative refinement where each pass can measurably improve the draft.
- Anywhere you would otherwise hand-check agent output before release.

## HITL gate loop (`ingredion_ai/loops/hitl.py`)

`hitl_gate(action_name, payload, approver=None, max_rounds=3)` wraps the
governance approval policy (`ingredion_ai/governance/approvals.py`):

1. If `requires_approval(action_name)` is **false**, the action passes
   through immediately (`decision="approved"`, `rounds=0`).
2. Otherwise the gate **loops**, requesting approval each round until the
   approver approves, rejects, or `max_rounds` is reached.

Returns:

```python
{"decision": "approved" | "rejected", "rounds": <n>,
 "requires_approval": <bool>, "record": <ApprovalRecord | None>,
 "action": <name>, "notes": <str>}
```

The default approver is the governance module's simulated approver
(`ApprovalGate(auto_approve=True)`), so the offline demo never blocks —
records are clearly marked `simulated=True`. Pass
`ApprovalGate(auto_approve=False)` (or your own gate-like object with a
`.request(output_type, summary, payload)` method) to model a real human
who may reject or stay silent; the loop then exits with
`decision="rejected"` after `max_rounds` rounds instead of looping forever.

### When to use

- **High-impact outputs** per policy (`new_formulation`, `customer_proposal`,
  `esg_report`, `production_schedule`, `procurement_plan`): always gate before
  release.
- Low-risk reads/summaries: skip the gate (the policy does this for you).

### Reflection vs HITL — quick rule

| Signal | Use |
|---|---|
| A rule or check can judge quality automatically | Reflection loop |
| A human must sign off before release (policy says so) | HITL gate |
| Both: draft must be good *and* approved | Chain them: reflect first, then gate |

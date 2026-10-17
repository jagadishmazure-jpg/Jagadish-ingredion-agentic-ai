# Graph-based orchestration (`food_ingredients_ai/graph/`)

A tiny, stdlib-only, fully offline graph runtime plus a graph-based variant
of the reformulation demo. Deterministic: insertion order decides the start
node, predicate results decide routing, and the shared state dict is the
only channel between nodes.

## Concepts

- **Node** — `fn(state) -> dict` (or `None`). The returned dict is merged
  into the shared mutable state dict, so later nodes see earlier results.
  Think of the state as a blackboard.
- **Edge** — `graph.add_edge("a", "b")`: after `a`, unconditionally run `b`.
  Mirrors `WorkflowBuilder`'s sequential chaining.
- **Conditional** — `graph.add_conditional("a", predicate, "b", "c")`: after
  `a`, run `b` if `predicate(state)` is true, else `c`. Mirrors the
  framework's conditional/branch edges. A node may have *either* an edge or
  a conditional, not both.
- **Cycle** — a back-edge (e.g. `revise -> validate`) is allowed. Cycles are
  kept safe two ways: the graph author's predicate must provide a bounded
  exit condition, and the runtime raises `RuntimeError` when `max_steps`
  node executions are exceeded (the cycle guard).
- **Terminal** — a node with no outgoing edge ends the run; `run()` returns
  the final state.

```python
from food_ingredients_ai.graph import Graph

graph = Graph()
graph.add_node("greet", lambda state: {"msg": f"hi {state['name']}"})
graph.add_node("shout", lambda state: {"msg": state["msg"].upper()})
graph.add_edge("greet", "shout")
print(graph.run({"name": "sam"})["msg"])  # HI SAM
```

Error behavior: empty graph → `ValueError`; edge to an unknown node →
`KeyError`; node returning a non-dict → `TypeError`; runaway cycle →
`RuntimeError` at `max_steps`.

## Walkthrough: the reformulation graph

`run_reformulation_graph(formula_id="sweet_bakery_cake", ...)` replays the
reformulation demo as a graph (`food_ingredients_ai/graph/reformulation_graph.py`):

```
analyze -> substitute -> validate --(invalid claims AND revisits left)--> revise_substitutions
                               |                                              |
                               +--(else)--> predict -> done                   |
                                              ^-------------------------------+
```

| Node | What it does (same `RDFormulationAgent.execute()` paths as the linear demo) |
|---|---|
| `analyze` | `analyze_ingredients` → flags non-clean ingredients |
| `substitute` | `suggest_substitutes` (seeded with the analysis) → swaps + reformulated formula |
| `validate` | `validate_claims` (seeded with the substitution) → per-claim valid/invalid; also records `invalid_claims` in state |
| `revise_substitutions` | re-runs the substitution path, bumps `revisits` (max 2) |
| `predict` | `predict_texture_shelf_life` (seeded with the substitution) — terminal node |

The conditional on `validate` implements the retry policy: while any target
claim is invalid **and** fewer than `max_revisits` revisions have happened,
route back through `revise_substitutions` → `validate`; otherwise proceed to
`predict`. Because the offline substitution path is deterministic and
idempotent, revisions don't change the outcome here — the demo run exhausts
its revisit budget and moves on. In a live deployment the revise node would
take corrective action (relax a constraint, try the next-best candidate),
and the budget + `max_steps` guard is what keeps that loop safe.

Payload shapes mirror `food_ingredients_ai/framework/tools.py`: the agent
`execute()` calls take `formula_id`/`target_claims`/`region` plus a
`blackboard` keyed by task name, so graph results are byte-identical to the
sequential pipeline — only the control flow differs.

The returned state is the blackboard: `formula_id`, `target_claims`,
`region`, `revisits`, and per-node results under `analyze`, `substitute`,
`validate`, `invalid_claims`, `predict`.

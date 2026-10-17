"""Minimal deterministic graph runtime for offline orchestration.

Node/edge semantics mirror the framework ``WorkflowBuilder`` concepts used
elsewhere in this project:

- ``add_node`` / ``add_edge`` mirror the builder's sequential chaining
  (run node A, then node B).
- ``add_conditional`` mirrors the framework's conditional/branch edges
  (route on a predicate of the shared state).
- Cycles are allowed (back-edges, e.g. revise -> re-validate) and are kept
  safe by the ``max_steps`` guard plus whatever bounded-exit condition the
  graph author puts in the conditional predicate.

Each node is ``fn(state) -> dict``; the returned dict is merged into the
shared mutable state dict (a blackboard), so later nodes see earlier
results. Execution is fully deterministic: insertion order decides the
start node and predicate results decide routing.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

NodeFn = Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]
Predicate = Callable[[Dict[str, Any]], bool]


class Graph:
    """Directed graph of ``fn(state) -> dict`` nodes with a shared state."""

    def __init__(self) -> None:
        self._nodes: Dict[str, NodeFn] = {}
        self._edges: Dict[str, str] = {}
        self._conditionals: Dict[str, Tuple[Predicate, str, str]] = {}

    def add_node(self, name: str, fn: NodeFn) -> "Graph":
        """Register node *name*; the first added node is the start node."""
        if name in self._nodes:
            raise ValueError(f"duplicate node name: {name!r}")
        self._nodes[name] = fn
        return self

    def _check_node(self, name: str, role: str) -> None:
        if name not in self._nodes:
            raise KeyError(f"{role} references unknown node: {name!r}")

    def add_edge(self, frm: str, to: str) -> "Graph":
        """Unconditional edge: after *frm*, run *to*."""
        self._check_node(frm, "add_edge(from)")
        self._check_node(to, "add_edge(to)")
        if frm in self._conditionals:
            raise ValueError(f"node {frm!r} already has a conditional edge")
        self._edges[frm] = to
        return self

    def add_conditional(
        self, frm: str, predicate: Predicate, to_true: str, to_false: str
    ) -> "Graph":
        """Conditional edge: after *frm*, run *to_true* if ``predicate(state)``
        else *to_false*. A node may have either an edge or a conditional."""
        self._check_node(frm, "add_conditional(from)")
        self._check_node(to_true, "add_conditional(to_true)")
        self._check_node(to_false, "add_conditional(to_false)")
        if frm in self._edges:
            raise ValueError(f"node {frm!r} already has an unconditional edge")
        self._conditionals[frm] = (predicate, to_true, to_false)
        return self

    def run(self, initial_state: Dict[str, Any], max_steps: int = 50) -> Dict[str, Any]:
        """Execute from the first-added node until a node has no outgoing edge.

        Raises ``ValueError`` for an empty graph, ``KeyError`` for a dangling
        edge target, ``TypeError`` if a node returns a non-dict, and
        ``RuntimeError`` when *max_steps* node executions are exceeded (the
        cycle guard).
        """
        if not self._nodes:
            raise ValueError("cannot run an empty graph")
        state = dict(initial_state)
        current = next(iter(self._nodes))
        steps = 0
        while True:
            if current not in self._nodes:
                raise KeyError(f"unknown node: {current!r}")
            if steps >= max_steps:
                raise RuntimeError(
                    f"max_steps={max_steps} exceeded at node {current!r}; "
                    "possible infinite cycle"
                )
            result = self._nodes[current](state)
            if result is not None:
                if not isinstance(result, dict):
                    raise TypeError(
                        f"node {current!r} must return a dict or None, "
                        f"got {type(result).__name__}"
                    )
                state.update(result)
            steps += 1
            if current in self._conditionals:
                predicate, to_true, to_false = self._conditionals[current]
                nxt: Optional[str] = to_true if predicate(state) else to_false
            else:
                nxt = self._edges.get(current)
            if nxt is None:
                return state
            current = nxt

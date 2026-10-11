"""Agent control plane: runtime behavioral governance for AI agents.

Content filters (``ingredion_ai.guardrails``) screen *what* goes in and out
of an agent. The control plane governs *behavior* at runtime: how many
actions an agent may take, how much it may spend, whether it is currently
healthy, and whether a human has halted it.

Components:

- :mod:`ingredion_ai.controlplane.budgets` — action-rate and spend limits
- :mod:`ingredion_ai.controlplane.circuit` — circuit breaker on failure rate
- :mod:`ingredion_ai.controlplane.killswitch` — immediate global/per-agent halt
- :mod:`ingredion_ai.controlplane.enforcement` — the single choke point gate
- :mod:`ingredion_ai.controlplane.drift` — behavior-drift detection
- :mod:`ingredion_ai.controlplane.ledger` — append-only decision log

All components are deterministic and offline-safe: clocks are injectable
for tests, no network, no API keys.
"""

from ingredion_ai.controlplane.budgets import ActionBudget, BudgetManager, SpendCap
from ingredion_ai.controlplane.circuit import CircuitBreaker
from ingredion_ai.controlplane.drift import BehaviorDrift
from ingredion_ai.controlplane.enforcement import EnforcementGate
from ingredion_ai.controlplane.killswitch import KillSwitch
from ingredion_ai.controlplane.ledger import ControlLedger

__all__ = [
    "ActionBudget",
    "BudgetManager",
    "BehaviorDrift",
    "CircuitBreaker",
    "ControlLedger",
    "EnforcementGate",
    "KillSwitch",
    "SpendCap",
]

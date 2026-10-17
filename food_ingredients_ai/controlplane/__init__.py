"""Agent control plane: runtime behavioral governance for AI agents.

Content filters (``food_ingredients_ai.guardrails``) screen *what* goes in and out
of an agent. The control plane governs *behavior* at runtime: how many
actions an agent may take, how much it may spend, whether it is currently
healthy, and whether a human has halted it.

Components:

- :mod:`food_ingredients_ai.controlplane.budgets` — action-rate and spend limits
- :mod:`food_ingredients_ai.controlplane.circuit` — circuit breaker on failure rate
- :mod:`food_ingredients_ai.controlplane.killswitch` — immediate global/per-agent halt
- :mod:`food_ingredients_ai.controlplane.enforcement` — the single choke point gate
- :mod:`food_ingredients_ai.controlplane.drift` — behavior-drift detection
- :mod:`food_ingredients_ai.controlplane.ledger` — append-only decision log

All components are deterministic and offline-safe: clocks are injectable
for tests, no network, no API keys.
"""

from food_ingredients_ai.controlplane.budgets import ActionBudget, BudgetManager, SpendCap
from food_ingredients_ai.controlplane.circuit import CircuitBreaker
from food_ingredients_ai.controlplane.drift import BehaviorDrift
from food_ingredients_ai.controlplane.enforcement import EnforcementGate
from food_ingredients_ai.controlplane.killswitch import KillSwitch
from food_ingredients_ai.controlplane.ledger import ControlLedger

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

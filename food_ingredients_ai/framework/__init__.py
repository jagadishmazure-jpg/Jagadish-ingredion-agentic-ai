"""Microsoft Agent Framework 1.0 integration layer.

This package wires the deterministic domain logic (``food_ingredients_ai.agents``)
into real Microsoft Agent Framework 1.0 constructs:

- :mod:`food_ingredients_ai.framework.clients` — chat clients: Azure OpenAI
  (``OpenAIChatClient``) for live runs, and a scripted ``FakeChatClient``
  implementing the framework's chat-client interface for offline runs/tests.
- :mod:`food_ingredients_ai.framework.tools` — domain logic exposed as framework
  function-tools (plain annotated Python functions).
- :mod:`food_ingredients_ai.framework.agents` — one framework ``Agent`` per domain
  (R&D formulation, supply chain, ESG, customer advisor).
- :mod:`food_ingredients_ai.framework.workflow` — the end-to-end reformulation
  workflow built with the framework's ``WorkflowBuilder`` (sequential R&D
  phase, then a concurrent fan-out to the supporting agents).

The legacy ``food_ingredients_ai.core`` modules remain as the tested deterministic
execution substrate that the function-tools call into; all *new* agent
construction goes through this package.
"""

from food_ingredients_ai.framework.agents import build_framework_agents
from food_ingredients_ai.framework.clients import FakeChatClient, build_chat_client
from food_ingredients_ai.framework.runner import build_demo_context, run_reformulation
from food_ingredients_ai.framework.workflow import build_reformulation_workflow

__all__ = [
    "FakeChatClient",
    "build_chat_client",
    "build_demo_context",
    "build_framework_agents",
    "build_reformulation_workflow",
    "run_reformulation",
]

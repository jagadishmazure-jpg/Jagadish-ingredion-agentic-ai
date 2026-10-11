"""Framework agents: one Microsoft Agent Framework 1.0 ``Agent`` per domain.

Each agent wraps the deterministic domain function-tools from
:mod:`ingredion_ai.framework.tools` with role instructions. In live mode
the instructions guide Azure OpenAI tool selection; in offline mode the
scripted fake client drives the same tools deterministically.
"""

from __future__ import annotations

from typing import Any, Dict, List

from agent_framework import Agent, BaseChatClient

from ingredion_ai.framework.clients import FakeChatClient, build_chat_client
from ingredion_ai.framework.scripts import DEMO_SCRIPTS
from ingredion_ai.framework.tools import build_tool_functions

INSTRUCTIONS: Dict[str, str] = {
    "rd_formulation": (
        "You are the clean-label R&D formulation specialist for a food-ingredient "
        "manufacturing demo. To reformulate a product, call your tools IN THIS ORDER: "
        "analyze_ingredients, suggest_substitutes, predict_texture_shelf_life, "
        "calculate_nutrition, validate_claims, generate_documentation. "
        "Then reply with a one-line summary of the reformulation."
    ),
    "supply_chain": (
        "You are the supply-chain optimization specialist for a food-ingredient "
        "manufacturing demo. Call forecast_demand to forecast ingredient demand, "
        "then reply with a one-line summary."
    ),
    "esg": (
        "You are the ESG and sustainability specialist for a food-ingredient "
        "manufacturing demo. Call collect_esg and then esg_report, in that order, "
        "then reply with a one-line summary."
    ),
    "customer_advisor": (
        "You are the customer-facing formulation advisor for a food-ingredient "
        "manufacturing demo. Call estimate_pricing, then reply with a one-line summary."
    ),
}

AGENT_ORDER = ["rd_formulation", "supply_chain", "esg", "customer_advisor"]


def build_framework_agents(
    ctx: Dict[str, Any],
    *,
    live: bool = False,
    scripts: Dict[str, list] | None = None,
) -> Dict[str, Agent]:
    """Build the four domain agents.

    - ``live=False`` (default): each agent gets its own scripted
      ``FakeChatClient`` (fully offline, deterministic).
    - ``live=True``: all agents share one Azure OpenAI chat client built
      from the environment (see ``.env.example``).
    """
    tools = build_tool_functions(ctx)
    agents: Dict[str, Agent] = {}
    shared_client: BaseChatClient | None = build_chat_client(live=True) if live else None
    scripts = scripts or DEMO_SCRIPTS
    for name in AGENT_ORDER:
        client: BaseChatClient = (
            shared_client if live else FakeChatClient(scripts.get(name, []))
        )
        agents[name] = Agent(
            client=client,
            instructions=INSTRUCTIONS[name],
            name=name,
            description=f"{name} domain specialist (demo)",
            tools=tools[name],
        )
    return agents


def agent_tool_names(agents: Dict[str, Agent]) -> Dict[str, List[str]]:
    """Return ``{agent_name: [tool names]}`` for inspection/tests."""
    result: Dict[str, List[str]] = {}
    for name, agent in agents.items():
        names: List[str] = []
        for tool in agent.default_options.get("tools", []) or []:
            tool_name = getattr(tool, "name", None) or getattr(tool, "__name__", "?")
            names.append(tool_name)
        result[name] = names
    return result

"""Tests for the Microsoft Agent Framework 1.0 integration layer.

All offline: the scripted FakeChatClient implements the framework's
chat-client interface, so no network or API keys are ever needed.
"""

import asyncio

import pytest
import yaml

from agent_framework import Agent

from ingredion_ai.framework.agents import (
    AGENT_ORDER,
    agent_tool_names,
    build_framework_agents,
)
from ingredion_ai.framework.clients import FakeChatClient, build_chat_client
from ingredion_ai.framework.runner import build_demo_context, run_reformulation
from ingredion_ai.framework.scripts import DEMO_SCRIPTS
from ingredion_ai.framework.tools import build_tool_functions
from ingredion_ai.framework.workflow import build_reformulation_workflow


def _ctx():
    return build_demo_context(
        "sweet_bakery_cake",
        ["no artificial ingredients", "reduced sugar", "natural"],
        "NA",
        adjustments={"RCS-01": 14.0},
        additions={"SL-95": 0.3},
    )


def test_fake_client_tool_loop_executes_real_function():
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    async def go():
        client = FakeChatClient(
            [("tool", "add", {"a": 40, "b": 2}), ("text", "The sum is 42.")]
        )
        agent = Agent(client=client, name="calc", tools=[add])
        resp = await agent.run("What is 40 + 2?")
        return resp.text

    assert asyncio.run(go()) == "The sum is 42."


def test_fake_client_ignores_other_agents_tool_results():
    """Shared workflow histories must not disturb a client's own script."""

    def ping() -> str:
        """Ping."""
        return "pong"

    async def go():
        client = FakeChatClient([("tool", "ping", {}), ("text", "done")])
        agent = Agent(client=client, name="isolated", tools=[ping])
        # Seed the conversation with ANOTHER agent's tool results.
        resp = await agent.run("go")
        return resp.text, client._step

    text, step = asyncio.run(go())
    assert text == "done"
    assert step == 2  # tool step consumed + text step consumed


def test_build_framework_agents_has_four_domains_with_tools():
    agents = build_framework_agents(_ctx(), live=False)
    assert set(agents) == set(AGENT_ORDER)
    names = agent_tool_names(agents)
    assert names["rd_formulation"] == [
        "analyze_ingredients",
        "suggest_substitutes",
        "predict_texture_shelf_life",
        "calculate_nutrition",
        "validate_claims",
        "generate_documentation",
        "lims_quality_lookup",  # composed OpenAPI (LIMS) tool chain
    ]
    assert names["supply_chain"] == ["forecast_demand"]
    assert names["esg"] == ["collect_esg", "esg_report"]
    assert names["customer_advisor"] == ["estimate_pricing"]
    for agent in agents.values():
        assert isinstance(agent.client, FakeChatClient)


def test_build_tools_returns_callables_bound_to_context():
    tools = build_tool_functions(_ctx())
    assert set(tools) == set(AGENT_ORDER)
    assert all(callable(t) for fns in tools.values() for t in fns)


def test_offline_workflow_populates_blackboard():
    ctx = _ctx()
    bb = asyncio.run(run_reformulation(ctx, live=False))
    assert set(bb) == {
        "analyze_ingredients",
        "suggest_substitutes",
        "predict_texture_shelf_life",
        "calculate_nutrition",
        "validate_claims",
        "generate_documentation",
        "forecast_demand",
        "collect_esg",
        "esg_report",
        "estimate_pricing",
    }


def test_offline_workflow_matches_regression_eval():
    with open("evals/regression_demo.yaml", encoding="utf-8") as fh:
        expected = yaml.safe_load(fh)["expected"]
    bb = asyncio.run(run_reformulation(_ctx(), live=False))
    assert bb["analyze_ingredients"]["flagged_count"] == expected["flagged_count"]
    subs = bb["suggest_substitutes"]
    assert subs["substituted_count"] == expected["substituted_count"]
    assert subs["removed_count"] == expected["removed_count"]
    pred = bb["predict_texture_shelf_life"]["prediction"]
    assert pred["texture_match_pct"] == expected["texture_match_pct"]
    assert pred["shelf_life_days"] == expected["shelf_life_days"]
    claims = {c["claim"]: c["valid"] for c in bb["validate_claims"]["claims"]}
    assert claims == expected["claims"]


def test_offline_workflow_is_deterministic():
    bb1 = asyncio.run(run_reformulation(_ctx(), live=False))
    bb2 = asyncio.run(run_reformulation(_ctx(), live=False))
    assert bb1 == bb2


def test_workflow_builder_topology():
    agents = build_framework_agents(_ctx(), live=False)
    workflow = build_reformulation_workflow(agents)
    executors = [e.id for e in workflow.get_executors_list()]
    assert "rd_formulation" in executors
    assert workflow.get_start_executor().id == "rd_formulation"


def test_build_chat_client_offline_raises():
    with pytest.raises(ValueError):
        build_chat_client(live=False)


def test_build_chat_client_live_missing_env_raises_helpful_error(monkeypatch):
    for var in (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_CHAT_DEPLOYMENT",
        "AZURE_OPENAI_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match="AZURE_OPENAI_ENDPOINT"):
        build_chat_client(live=True)


def test_demo_scripts_cover_all_agents():
    assert set(DEMO_SCRIPTS) == set(AGENT_ORDER)
    for script in DEMO_SCRIPTS.values():
        assert script[-1][0] == "text"  # every script ends with a summary
        assert any(step[0] == "tool" for step in script)

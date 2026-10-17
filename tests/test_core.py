"""Tests for core orchestration primitives."""

import pytest

from food_ingredients_ai.core.agent import Agent
from food_ingredients_ai.core.fake_llm import FakeLLM
from food_ingredients_ai.core.planner import Orchestrator
from food_ingredients_ai.core.tools import Tool, ToolRegistry
from food_ingredients_ai.core.types import Message, Task, TaskResult, TaskState


class _EchoAgent(Agent):
    name = "echo"

    def execute(self, task_name, payload):
        if task_name == "boom":
            raise RuntimeError("demo failure")
        return {"echo": task_name, "saw": payload.get("marker")}


def test_message_defaults():
    m = Message(role="user", content="hi")
    assert m.sender == "" and m.metadata == {}


def test_task_state_record_failed_marks_failed():
    state = TaskState(goal="g")
    state.record(TaskResult("t", "a", False, error="x"))
    assert state.status == "failed"


def test_fake_llm_deterministic():
    llm = FakeLLM()
    assert llm.generate("reformulate the cake") == llm.generate("reformulate the cake")


def test_fake_llm_routes_reformulate():
    assert "analyze_ingredients" in FakeLLM().generate("please reformulate this")


def test_fake_llm_routes_supply():
    assert "forecast_demand" in FakeLLM().generate("supply plan please")


def test_fake_llm_routes_esg():
    assert "collect_esg" in FakeLLM().generate("carbon report")


def test_fake_llm_routes_customer():
    assert "recommend_ingredients" in FakeLLM().generate("customer pricing")


def test_fake_llm_default_ack():
    assert FakeLLM().generate("something else entirely").startswith("ACK")


def test_tool_registry_register_and_call():
    reg = ToolRegistry()
    reg.register(Tool("add", "adds", lambda a, b: a + b, {"a": "n", "b": "n"}))
    assert reg.call("add", a=2, b=3) == 5
    assert reg.names() == ["add"]


def test_tool_registry_duplicate_raises():
    reg = ToolRegistry()
    reg.register(Tool("t", "d", lambda: 1))
    with pytest.raises(ValueError):
        reg.register(Tool("t", "d", lambda: 1))


def test_tool_registry_unknown_raises():
    with pytest.raises(KeyError):
        ToolRegistry().call("nope")


def test_tool_missing_args_raises():
    reg = ToolRegistry()
    reg.register(Tool("t", "d", lambda a: a, {"a": "x"}))
    with pytest.raises(TypeError):
        reg.call("t")


def test_agent_run_success():
    agent = _EchoAgent()
    result = agent.run(Task("hello", "echo"), {"marker": 1})
    assert result.success and result.output["saw"] == 1


def test_agent_run_failure_becomes_result():
    agent = _EchoAgent()
    result = agent.run(Task("boom", "echo"), {})
    assert not result.success and "RuntimeError" in result.error


def test_plan_reformulate_has_six_tasks():
    orch = Orchestrator({"echo": _EchoAgent()})
    tasks = orch.plan("reformulate the cake")
    assert len(tasks) == 6
    assert tasks[0].name == "analyze_ingredients"
    assert all(t.agent_name == "rd_formulation" for t in tasks)


def test_plan_full_launch_covers_all_agents():
    orch = Orchestrator({"echo": _EchoAgent()})
    agents = {t.agent_name for t in orch.plan("full_launch")}
    assert agents == {"rd_formulation", "supply_chain", "esg", "customer_advisor"}


def test_plan_unknown_goal_raises():
    with pytest.raises(ValueError):
        Orchestrator({}).plan("take over the world")


def test_run_stops_on_missing_agent():
    orch = Orchestrator({})
    state = orch.run("reformulate", {"formula_id": "sweet_bakery_cake"})
    assert state.status == "failed"
    assert "no agent registered" in state.results["analyze_ingredients"].error

"""Planner / orchestrator: decomposes a goal into routed sub-tasks and runs them.

Plans are declarative templates keyed by goal keyword so the whole system
stays deterministic and offline. A shared *blackboard* dict threads each
task's output into later tasks' payloads.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ingredion_ai.core.agent import Agent
from ingredion_ai.core.fake_llm import FakeLLM
from ingredion_ai.core.types import Task, TaskState

# goal keyword -> ordered list of (task_name, agent_name, description)
GOAL_PLANS: Dict[str, List[tuple]] = {
    "reformulate": [
        ("analyze_ingredients", "rd_formulation", "Flag non-clean-label ingredients"),
        ("suggest_substitutes", "rd_formulation", "Recommend clean-label swaps"),
        (
            "predict_texture_shelf_life",
            "rd_formulation",
            "Predict texture & shelf-life impact",
        ),
        ("calculate_nutrition", "rd_formulation", "Compute nutritional panels"),
        ("validate_claims", "rd_formulation", "Validate label claims per region"),
        ("generate_documentation", "rd_formulation", "Generate spec + tech sheet"),
    ],
    "full_launch": [
        ("analyze_ingredients", "rd_formulation", "Flag non-clean-label ingredients"),
        ("suggest_substitutes", "rd_formulation", "Recommend clean-label swaps"),
        (
            "predict_texture_shelf_life",
            "rd_formulation",
            "Predict texture & shelf-life impact",
        ),
        ("validate_claims", "rd_formulation", "Validate label claims per region"),
        ("forecast_demand", "supply_chain", "Forecast ingredient demand"),
        ("optimize_inventory", "supply_chain", "Plan procurement"),
        ("collect_esg", "esg", "Collect ESG readings"),
        ("calculate_carbon", "esg", "Compute carbon footprint"),
        ("esg_report", "esg", "Generate ESG report"),
        ("recommend_ingredients", "customer_advisor", "Recommend ingredients"),
        ("estimate_pricing", "customer_advisor", "Estimate pricing bands"),
    ],
}


class Orchestrator:
    """Decomposes goals into tasks, routes them, and aggregates results."""

    def __init__(self, agents: Dict[str, Agent], llm: FakeLLM | None = None) -> None:
        self.agents = agents
        self.llm = llm or FakeLLM()

    def plan(self, goal: str, context: Dict[str, Any] | None = None) -> List[Task]:
        """Build the ordered task list for *goal* (raises on unknown goal)."""
        context = context or {}
        lowered = goal.lower()
        if "launch" in lowered:
            matched = "full_launch"
        elif "reformul" in lowered:
            matched = "reformulate"
        else:
            matched = next((k for k in GOAL_PLANS if k in lowered), None)
        if matched is None:
            raise ValueError(
                f"unknown goal: {goal!r}; known goals: {sorted(GOAL_PLANS)}"
            )
        # Ask the (fake) LLM to narrate the plan; the template stays authoritative.
        self.llm.generate(f"reformulate plan for goal: {goal}")
        return [
            Task(
                name=name,
                agent_name=agent_name,
                description=desc,
                payload=dict(context.get("task_payloads", {}).get(name, {})),
            )
            for name, agent_name, desc in GOAL_PLANS[matched]
        ]

    def run(self, goal: str, context: Dict[str, Any] | None = None) -> TaskState:
        """Execute the plan for *goal*, threading outputs via the blackboard."""
        context = context or {}
        state = TaskState(goal=goal, status="running")
        tasks = self.plan(goal, context)
        state.tasks = tasks
        blackboard: Dict[str, Any] = {}
        for task in tasks:
            agent = self.agents.get(task.agent_name)
            if agent is None:
                from ingredion_ai.core.types import TaskResult

                state.record(
                    TaskResult(
                        task_name=task.name,
                        agent_name=task.agent_name,
                        success=False,
                        error=f"no agent registered: {task.agent_name}",
                    )
                )
                break
            payload = {**context, **task.payload, "blackboard": blackboard}
            result = agent.run(task, payload)
            state.record(result)
            if result.success:
                blackboard[task.name] = result.output
            else:
                break
        if state.status == "running":
            state.status = "complete"
        return state

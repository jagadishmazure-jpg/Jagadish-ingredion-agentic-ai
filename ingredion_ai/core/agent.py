"""Base agent class: named specialist with tools and task dispatch."""

from __future__ import annotations

from typing import Any, Dict

from ingredion_ai.core.fake_llm import FakeLLM
from ingredion_ai.core.tools import ToolRegistry
from ingredion_ai.core.types import Task, TaskResult


class Agent:
    """Specialist agent. Subclasses implement :meth:`execute`."""

    name: str = "base"
    role: str = ""
    description: str = ""

    def __init__(self, llm: FakeLLM | None = None) -> None:
        self.llm = llm or FakeLLM()
        self.tools = ToolRegistry()

    def execute(self, task_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Run *task_name* against *payload*; return a JSON-able output dict."""
        raise NotImplementedError

    def run(self, task: Task, payload: Dict[str, Any]) -> TaskResult:
        """Execute a planned task, converting exceptions into failed results."""
        try:
            output = self.execute(task.name, payload)
            return TaskResult(
                task_name=task.name, agent_name=self.name, success=True, output=output
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as failed TaskResult
            return TaskResult(
                task_name=task.name,
                agent_name=self.name,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )

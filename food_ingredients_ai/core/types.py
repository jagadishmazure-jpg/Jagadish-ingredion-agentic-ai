"""Shared message and task-state types for the multi-agent system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Message:
    """A single message exchanged between user, agents, or tools."""

    role: str  # "user" | "agent" | "system" | "tool"
    content: str
    sender: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Task:
    """One unit of work routed to a specialist agent."""

    name: str
    agent_name: str
    description: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    """Outcome of executing a single task."""

    task_name: str
    agent_name: str
    success: bool
    output: Dict[str, Any] = field(default_factory=dict)
    messages: List[Message] = field(default_factory=list)
    error: str = ""


@dataclass
class TaskState:
    """Tracks a whole multi-agent run: plan, per-task results, status."""

    goal: str
    tasks: List[Task] = field(default_factory=list)
    results: Dict[str, TaskResult] = field(default_factory=dict)
    status: str = "pending"  # pending | running | complete | failed

    def record(self, result: TaskResult) -> None:
        self.results[result.task_name] = result
        if not result.success:
            self.status = "failed"

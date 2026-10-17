"""Tool registry: named, schema-described callables agents can invoke."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


@dataclass
class Tool:
    """A single tool an agent may call."""

    name: str
    description: str
    func: Callable[..., Any]
    parameters: Dict[str, str] = field(default_factory=dict)

    def call(self, **kwargs: Any) -> Any:
        missing = [p for p in self.parameters if p not in kwargs]
        if missing:
            raise TypeError(f"tool '{self.name}' missing arguments: {missing}")
        return self.func(**kwargs)


class ToolRegistry:
    """Named registry of tools with strict lookup."""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(f"unknown tool: {name}") from None

    def call(self, name: str, **kwargs: Any) -> Any:
        return self.get(name).call(**kwargs)

    def names(self) -> List[str]:
        return sorted(self._tools)

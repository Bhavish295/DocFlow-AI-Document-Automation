"""Explicit registry of allowed agent tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.permissions import Permission


ToolHandler = Callable[..., Any]


@dataclass(frozen=True)
class AgentToolDefinition:
    name: str
    description: str
    category: str
    required_permission: Permission
    read_only: bool
    input_schema: dict[str, Any] = field(default_factory=dict)
    handler: ToolHandler | None = None


class AgentToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentToolDefinition] = {}

    def register(self, tool: AgentToolDefinition) -> None:
        if not tool.read_only:
            raise ValueError(f"Refusing to register non-read-only tool: {tool.name}")
        if tool.handler is None:
            raise ValueError(f"Tool '{tool.name}' requires a handler")
        self._tools[tool.name] = tool

    def get(self, name: str) -> AgentToolDefinition | None:
        return self._tools.get(name)

    def list_tools(self) -> list[AgentToolDefinition]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return sorted(self._tools.keys())

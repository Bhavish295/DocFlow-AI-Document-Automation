"""Permission and safety policy for agent tool execution."""

from __future__ import annotations

from app.core.exceptions import AppError
from app.core.permissions import Permission, role_has_permission
from app.models.user import User
from app.services.agent.agent_registry import AgentToolDefinition


class AgentPolicy:
    """Centralized permission checks — do not hard-code roles in tools."""

    @staticmethod
    def assert_can_use_agent(user: User) -> None:
        if not role_has_permission(user.role, Permission.AGENT_USE):
            raise AppError("Insufficient permissions for agent use.", status_code=403)

    @staticmethod
    def assert_can_run_tool(user: User, tool: AgentToolDefinition) -> None:
        if not tool.read_only:
            raise AppError(
                f"Tool '{tool.name}' is not allowed for the controlled agent (must be read-only).",
                status_code=403,
            )
        if not role_has_permission(user.role, tool.required_permission):
            raise AppError(
                f"Insufficient permissions to run tool '{tool.name}'.",
                status_code=403,
            )

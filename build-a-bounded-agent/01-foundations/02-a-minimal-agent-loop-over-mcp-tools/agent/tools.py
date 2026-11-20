"""Helpline's MCP tools, seen from the agent.

The agent never imports Helpline: it lists the server's tools over MCP, turns
each one into a Claude tool definition, and calls them over MCP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mcp import Client
from mcp.shared.exceptions import MCPError


@dataclass(frozen=True)
class ToolOutcome:
    text: str
    is_error: bool


def to_claude_tool(tool: Any) -> dict[str, Any]:
    """MCP tool -> Claude tool definition. The JSON Schema carries over as it is."""
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.input_schema,
    }


class McpTools:
    def __init__(self, client: Client) -> None:
        self.client = client

    async def definitions(self) -> list[dict[str, Any]]:
        """Every tool on the server, following tools/list pagination to the last page."""
        tools, cursor = [], None
        while True:
            page = await self.client.list_tools(cursor=cursor)
            tools += page.tools
            cursor = page.next_cursor
            if not cursor:
                return [to_claude_tool(t) for t in tools]

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        try:
            result = await self.client.call_tool(name, arguments)
        except MCPError as exc:  # a protocol error: report it to the model as a failed call
            return ToolOutcome(f"Protocol error {exc.error.code}: {exc.error.message[:200]}", True)
        except Exception as exc:  # transport failure: a short, safe message, no server detail
            return ToolOutcome(f"{name} could not be reached ({type(exc).__name__}).", True)
        text = "\n".join(c.text for c in result.content if getattr(c, "text", None))
        return ToolOutcome(text, bool(result.is_error))

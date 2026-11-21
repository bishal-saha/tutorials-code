"""Helpline's MCP tools, seen from the agent.

Lesson 3 adds two facts the loop needs: whether a tool only reads, and whether
a failure looks transient. Which tools only read is the agent's own decision,
kept here in config: a server's readOnlyHint is a hint, and an agent should not
let another party's hint decide what it retries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from mcp import Client
from mcp.shared.exceptions import MCPError

# An unhandled crash on the server ("Error executing tool X", nothing after it)
# or a timeout may go away on a retry. A ToolError with a hint will not.
_CRASH = re.compile(r"^Error executing tool \w+$")
_TIMEOUT = "did not answer within"

# Safe to retry: they only read. Everything else is called at most once.
READ_ONLY_TOOLS = {"search_tickets", "get_ticket", "search_knowledge_base"}


@dataclass(frozen=True)
class ToolOutcome:
    text: str
    is_error: bool
    transient: bool = False


def to_claude_tool(tool: Any) -> dict[str, Any]:
    """MCP tool -> Claude tool definition. The JSON Schema carries over as it is."""
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.input_schema,
    }


@dataclass
class McpTools:
    client: Client
    read_only: set[str] = field(default_factory=lambda: set(READ_ONLY_TOOLS))

    async def definitions(self) -> list[dict[str, Any]]:
        """Every tool on the server, following tools/list pagination to the last page."""
        tools, cursor = [], None
        while True:
            page = await self.client.list_tools(cursor=cursor)
            tools += page.tools
            cursor = page.next_cursor
            if not cursor:
                return [to_claude_tool(t) for t in tools]

    async def server_read_only_hints(self) -> set[str]:
        """What the server claims is read-only, for checking against READ_ONLY_TOOLS."""
        listed = await self.client.list_tools()
        return {t.name for t in listed.tools if t.annotations and t.annotations.read_only_hint}

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        try:
            result = await self.client.call_tool(name, arguments)
        except MCPError as exc:  # a protocol error: report it to the model as a failed call
            return ToolOutcome(f"Protocol error {exc.error.code}: {exc.error.message[:200]}", True)
        except Exception as exc:  # transport failure: a short, safe message, no server detail
            return ToolOutcome(
                f"{name} could not be reached ({type(exc).__name__}).", True, transient=True
            )
        text = "\n".join(c.text for c in result.content if getattr(c, "text", None))
        if not result.is_error:
            return ToolOutcome(text, False)
        return ToolOutcome(text, True, bool(_CRASH.match(text)) or _TIMEOUT in text)

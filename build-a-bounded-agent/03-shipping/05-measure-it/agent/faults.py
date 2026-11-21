"""Make a tool fail on purpose, to see what the limits do with it.

Wraps McpTools. A failing tool answers exactly as Helpline does when a tool
crashes: "Error executing tool <name>".
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from agent.tools import McpTools, ToolOutcome


@dataclass
class FaultyTools:
    inner: McpTools
    failures: dict[str, int] = field(default_factory=dict)  # tool -> how many calls fail
    calls: Counter[str] = field(default_factory=Counter)  # calls that reached the tool

    @property
    def read_only(self) -> set[str]:
        return self.inner.read_only

    async def definitions(self) -> list[dict[str, Any]]:
        return await self.inner.definitions()

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        self.calls[name] += 1
        if self.calls[name] <= self.failures.get(name, 0):
            return ToolOutcome(f"Error executing tool {name}", True, transient=True)
        return await self.inner.call(name, arguments)

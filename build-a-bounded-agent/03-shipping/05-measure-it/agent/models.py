"""The model side of the loop: one small protocol, two implementations.

FakeModel replays a script, so every test runs without a key or a network.
AnthropicModel calls Claude through the anthropic SDK. The loop only ever sees
a Turn, whichever model produced it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

MODEL_ID = "claude-opus-5-5"


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read + other.cache_read,
            self.cache_write + other.cache_write,
        )


@dataclass(frozen=True)
class Turn:
    """One model response: why it stopped, its content blocks, what it cost."""

    stop_reason: str
    content: list[dict[str, Any]]
    usage: Usage = field(default_factory=Usage)

    def tool_calls(self) -> list[dict[str, Any]]:
        return [b for b in self.content if b.get("type") == "tool_use"]

    def text(self) -> str:
        return "".join(b.get("text", "") for b in self.content if b.get("type") == "text")


class Model(Protocol):
    name: str

    async def complete(
        self, *, system: str, tools: list[dict[str, Any]], messages: list[dict[str, Any]]
    ) -> Turn: ...


# --- the fake ---------------------------------------------------------------

_ids = iter(range(1, 1_000_000))


def tool_use(name: str, **arguments: Any) -> dict[str, Any]:
    return {
        "type": "tool_use",
        "id": f"toolu_fake_{next(_ids):04d}",
        "name": name,
        "input": arguments,
    }


def calls(*blocks: dict[str, Any], text: str = "", usage: Usage | None = None) -> Turn:
    """A turn that asks for one or more tool calls."""
    content = ([{"type": "text", "text": text}] if text else []) + list(blocks)
    return Turn("tool_use", content, usage or Usage(1200, 80))


def answer(text: str, usage: Usage | None = None) -> Turn:
    """A final turn: the model is done."""
    return Turn("end_turn", [{"type": "text", "text": text}], usage or Usage(1500, 160))


Step = Turn | Callable[[list[dict[str, Any]]], Turn]


class FakeModel:
    """Replays a script of turns. A step may be a function of the messages so far."""

    name = "fake"

    def __init__(self, script: Sequence[Step]) -> None:
        self.script = list(script)
        self.requests: list[dict[str, Any]] = []

    async def complete(self, *, system, tools, messages) -> Turn:
        self.requests.append({"system": system, "tools": tools, "messages": list(messages)})
        if not self.script:
            raise AssertionError("FakeModel ran out of scripted turns")
        step = self.script.pop(0)
        return step(messages) if callable(step) else step


# --- the real model -----------------------------------------------------------


class AnthropicModel:
    """Claude through the anthropic SDK (reads ANTHROPIC_API_KEY from the environment)."""

    def __init__(
        self, client: Any = None, model: str = MODEL_ID, effort: str = "medium", cache: bool = True
    ) -> None:
        if client is None:
            import anthropic

            client = anthropic.AsyncAnthropic()
        self.client = client
        self.name = model
        self.effort = effort
        self.cache = cache

    async def complete(self, *, system, tools, messages) -> Turn:
        response = await self.client.messages.create(
            model=self.name,
            max_tokens=16000,
            system=system,
            tools=tools,
            messages=messages,
            # Effort is the depth control on this model; manual thinking budgets return a 400.
            # tool_choice stays at its default, auto: forcing a tool returns a 400 here.
            output_config={"effort": self.effort},
            # Top-level caching: each step's prompt is the last one plus a little more,
            # so later steps read the shared prefix from cache (0.05x input on this model).
            **({"cache_control": {"type": "ephemeral"}} if self.cache else {}),
        )
        u = response.usage
        return Turn(
            stop_reason=response.stop_reason,
            # Keep every block (thinking included) so it can be sent back unchanged.
            content=[b.model_dump(mode="json", exclude_none=True) for b in response.content],
            usage=Usage(
                u.input_tokens,
                u.output_tokens,
                u.cache_read_input_tokens or 0,
                u.cache_creation_input_tokens or 0,
            ),
        )

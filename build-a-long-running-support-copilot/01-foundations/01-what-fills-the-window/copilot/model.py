"""The model behind a small protocol: the real Claude API, or a fake that needs no key.

The fake (`ShiftModel`) does two jobs:
- it plays a support copilot that reacts only to what is in its window, and
- `CacheSim` works out the usage the API would report for each request from the
  request's own bytes, so caching effects show up in tests exactly where a
  real prefix would hit or miss.

CacheSim is a model of prompt caching, not the real thing: the API caches at
breakpoints over tokens and blocks, with a minimum size and a lookback limit.
It is close enough to show which layouts and policies keep the prefix intact.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from copilot.shift_data import SHIFT_CODE

CHARS_PER_TOKEN = 4
MIN_CACHEABLE_TOKENS = 512  # Sonnet 5.5 and Haiku 5.5


def tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


@dataclass
class Usage:
    input_tokens: int = 0  # uncached, full price
    output_tokens: int = 0
    cache_write_tokens: int = 0  # cache_creation_input_tokens
    cache_read_tokens: int = 0  # cache_read_input_tokens

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_write_tokens + self.cache_read_tokens

    def __add__(self, o: Usage) -> Usage:
        return Usage(
            self.input_tokens + o.input_tokens,
            self.output_tokens + o.output_tokens,
            self.cache_write_tokens + o.cache_write_tokens,
            self.cache_read_tokens + o.cache_read_tokens,
        )


@dataclass
class ModelTurn:
    content: list[dict[str, Any]]
    stop_reason: str
    usage: Usage

    def tool_calls(self) -> list[dict[str, Any]]:
        return [b for b in self.content if b["type"] == "tool_use"]

    def text(self) -> str:
        return "\n".join(b["text"] for b in self.content if b["type"] == "text")


class ModelClient(Protocol):
    model: str

    async def complete(
        self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelTurn: ...


def render_request(system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> str:
    """The request in the order the API reads it: tools, then system, then each message.

    Segments are joined, not wrapped in one JSON object, so a conversation that only
    grows keeps every earlier request as an exact prefix, the way the API sees it.
    """
    parts = [json.dumps(tools), system] + [json.dumps(m, default=str) for m in messages]
    return "\n".join(parts)


@dataclass
class CacheSim:
    """Each request writes its whole prompt to the cache (automatic caching puts the
    breakpoint on the last block). The next request reads the longest earlier
    entry that is an exact prefix of it, and pays to write the rest."""

    enabled: bool = True
    entries: list[str] = field(default_factory=list)

    def usage_for(self, request: str, output_tokens: int) -> Usage:
        total = tokens(request)
        if not self.enabled:
            return Usage(input_tokens=total, output_tokens=output_tokens)
        hit = max((len(e) for e in self.entries if request.startswith(e)), default=0)
        read = tokens(request[:hit])
        if read < MIN_CACHEABLE_TOKENS:
            read = 0
        self.entries.append(request)
        return Usage(
            output_tokens=output_tokens, cache_write_tokens=total - read, cache_read_tokens=read
        )


# --- the fake copilot ---------------------------------------------------------

ANNOUNCE = re.compile(r"Next ticket: (HL-\d{4})")


def _text_of(messages: list[dict[str, Any]]) -> str:
    parts = []
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            parts.append(content)
            continue
        for b in content:
            if b["type"] == "text":
                parts.append(b["text"])
            elif b["type"] == "tool_result":
                parts.append(
                    b["content"] if isinstance(b["content"], str) else json.dumps(b["content"])
                )
    return "\n".join(parts)


def _calls_since_announce(messages: list[dict[str, Any]], ticket_id: str) -> list[str]:
    """Tool names the copilot already called for the current ticket."""
    start = 0
    for i, m in enumerate(messages):
        if m["role"] == "user" and f"Next ticket: {ticket_id}" in _text_of([m]):
            start = i
    return [
        b["name"]
        for m in messages[start:]
        if m["role"] == "assistant"
        for b in m["content"]
        if b["type"] == "tool_use"
    ]


def _ticket_seen(messages: list[dict[str, Any]], ticket_id: str) -> dict[str, Any] | None:
    """The ticket fields as the copilot can read them in its window, if it can."""
    for m in reversed(messages):
        if m["role"] != "user" or isinstance(m["content"], str):
            continue
        for b in m["content"]:
            if b["type"] == "tool_result" and f'"id": "{ticket_id}"' in str(b["content"]):
                try:
                    return json.loads(b["content"])["ticket"]
                except (ValueError, KeyError, TypeError):
                    return None
    return None


@dataclass
class ShiftModel:
    """A scripted copilot. It follows a standing instruction only while that
    instruction is somewhere in its window."""

    model: str = "claude-sonnet-5-5"
    cache: CacheSim = field(default_factory=CacheSim)
    requests: int = 0

    async def complete(
        self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelTurn:
        self.requests += 1
        content = self.decide(system, messages)
        output = 220 if any(b.get("name") == "draft_reply" for b in content) else 90
        usage = self.cache.usage_for(render_request(system, messages, tools), output)
        stop = "tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn"
        return ModelTurn(content, stop, usage)

    def decide(self, system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        window = system + "\n" + _text_of(messages)
        ticket_id = ANNOUNCE.findall(window)[-1]
        done = _calls_since_announce(messages, ticket_id)
        n = len(done)

        def call(name: str, **args: Any) -> list[dict[str, Any]]:
            return [
                {
                    "type": "tool_use",
                    "id": f"toolu_{self.requests:04d}_{n}",
                    "name": name,
                    "input": args,
                }
            ]

        if "get_ticket" not in done:
            return call("get_ticket", ticket_id=ticket_id)
        ticket = _ticket_seen(messages, ticket_id)
        if ticket is None:
            return [{"type": "text", "text": f"I can't read {ticket_id}; handing back."}]
        if "search_kb" not in done:
            return call("search_kb", query=ticket["subject"])
        if ticket["kind"] == "refund" and not {"issue_refund", "hand_to_person"} & set(done):
            corvid_rule = "No refunds for Corvid Analytics" in window
            if corvid_rule and ticket["customer_name"] == "Corvid Analytics":
                return call("hand_to_person", ticket_id=ticket_id, reason="Corvid billing review")
            return call("issue_refund", ticket_id=ticket_id, amount=ticket["refund_amount"])
        if "draft_reply" not in done:
            message = f"Thanks for your patience on '{ticket['subject']}'. Here is what to do next."
            if f"shift code {SHIFT_CODE}" in window:
                message += f"\n{SHIFT_CODE}"
            return call("draft_reply", ticket_id=ticket_id, message=message)
        return [{"type": "text", "text": f"Done with {ticket_id}."}]


# --- the real model -----------------------------------------------------------


class AnthropicModel:
    """Claude through the official SDK. Needs ANTHROPIC_API_KEY; costs money."""

    def __init__(
        self, model: str = "claude-haiku-5-5", *, max_tokens: int = 2048, client: Any = None
    ):
        if client is None:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic()
        self.client, self.model, self.max_tokens = client, model, max_tokens

    async def complete(
        self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelTurn:
        r = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=messages,
            tools=tools,
            cache_control={"type": "ephemeral"},
        )
        u = r.usage
        return ModelTurn(
            [b.model_dump(exclude_none=True) for b in r.content],
            r.stop_reason,
            Usage(
                u.input_tokens,
                u.output_tokens,
                u.cache_creation_input_tokens or 0,
                u.cache_read_input_tokens or 0,
            ),
        )

"""One interface for every model call in the suite: the drafter and the judge.

    complete(system, user, schema) -> Completion

FakeModel answers from a Python function, for tests. AnthropicModel calls Claude
with structured output. RecordingModel saves every real call to a JSON Lines file,
and ReplayModel answers from that file, so tests and CI repeat a real run exactly
without an API key.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

# stop_reason values that mean "no usable JSON came back"
NO_ANSWER = {"refusal", "max_tokens", "model_context_window_exceeded"}


@dataclass
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


@dataclass
class Completion:
    value: dict[str, Any] | None  # the parsed JSON, or None when the model gave none
    stop_reason: str
    model: str
    usage: Usage = field(default_factory=Usage)


class Model(Protocol):
    name: str

    def complete(self, system: str, user: str, schema: dict, tag: str = "") -> Completion: ...


def call_key(model: str, system: str, user: str, schema: dict, tag: str = "") -> str:
    """The identity of a call: same model, prompts, schema and tag give the same key.

    The tag tells deliberate repeats of one call apart ("repeat=2").
    """
    blob = json.dumps([model, system, user, schema, tag], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


class FakeModel:
    """Answers with respond(system, user); usage is a rough length-based estimate."""

    def __init__(self, respond: Callable[[str, str], dict | None], name: str = "fake") -> None:
        self.respond = respond
        self.name = name
        self.calls = 0

    def complete(self, system: str, user: str, schema: dict, tag: str = "") -> Completion:
        self.calls += 1
        value = self.respond(system, user)
        usage = Usage(input_tokens=(len(system) + len(user)) // 4, output_tokens=60)
        return Completion(value, "end_turn" if value is not None else "refusal", self.name, usage)


class AnthropicModel:
    """Claude with structured output (output_config.format) and an explicit effort."""

    def __init__(self, name: str, *, effort: str = "low", max_tokens: int = 4000) -> None:
        import anthropic  # imported here so tests never need the SDK configured

        self.name = name
        self.effort = effort
        self.max_tokens = max_tokens
        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

    def complete(self, system: str, user: str, schema: dict, tag: str = "") -> Completion:
        r = self.client.messages.create(
            model=self.name,
            max_tokens=self.max_tokens,
            # the long, stable part (instructions + knowledge base) is cached
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        )
        u = r.usage
        usage = Usage(
            u.input_tokens,
            u.output_tokens,
            u.cache_read_input_tokens or 0,
            u.cache_creation_input_tokens or 0,
        )
        stop = r.stop_reason or ""
        if stop in NO_ANSWER:  # check stop_reason before reading content
            return Completion(None, stop, self.name, usage)
        text = "".join(b.text for b in r.content if b.type == "text")
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            value = None
        return Completion(value, stop, self.name, usage)


class RecordingModel:
    """Wraps a real model and appends every call to a JSON Lines file."""

    def __init__(self, inner: Model, path: Path) -> None:
        self.inner = inner
        self.name = inner.name
        self.path = path
        self._lock = threading.Lock()

    def complete(self, system: str, user: str, schema: dict, tag: str = "") -> Completion:
        c = self.inner.complete(system, user, schema, tag)
        row = {
            "key": call_key(self.name, system, user, schema, tag),
            "model": c.model,
            "stop_reason": c.stop_reason,
            "value": c.value,
            "usage": asdict(c.usage),
        }
        with self._lock, self.path.open("a") as f:
            f.write(json.dumps(row) + "\n")
        return c


class NotRecorded(KeyError):
    pass


class ReplayModel:
    """Answers from recorded calls. A call that was never recorded is an error, not a guess."""

    def __init__(self, name: str, path: Path) -> None:
        self.name = name
        self.calls: dict[str, dict] = {}
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if row["model"] == name:
                self.calls[row["key"]] = row

    def complete(self, system: str, user: str, schema: dict, tag: str = "") -> Completion:
        key = call_key(self.name, system, user, schema, tag)
        if key not in self.calls:
            raise NotRecorded(f"{self.name}: no recorded call {key}; record it with a real run")
        row = self.calls[key]
        return Completion(row["value"], row["stop_reason"], self.name, Usage(**row["usage"]))

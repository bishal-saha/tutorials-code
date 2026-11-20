"""Operational middleware: an audit record per tool call, and per-caller rate limits.

Both run as SDK server middleware, so they see every tools/call on every
transport (stdio and HTTP) before the tool runs.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token

audit_log = logging.getLogger("helpline.audit")

WRITE_TOOLS = {"draft_reply", "escalate_ticket"}

# Arguments safe to copy into the audit log verbatim. Free text (queries, replies,
# reasons) may hold customer data, so only its length is recorded.
AUDITED_ARGS = {"ticket_id", "status", "severity", "customer", "article_ids", "limit"}


def caller() -> tuple[str, str]:
    """(subject, client_id) of the caller; ("local", "stdio") when there is no token."""
    token = get_access_token()
    if token is None:
        return "local", "stdio"
    return token.subject or "unknown", token.client_id


def _redact(arguments: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in arguments.items():
        if key in AUDITED_ARGS:
            out[key] = value
        elif isinstance(value, str):
            out[key] = f"<{len(value)} chars>"
        else:
            out[key] = "<redacted>"
    return out


@dataclass
class AuditMiddleware:
    """Write one JSON audit record per tools/call: who, what, outcome, how long."""

    sink: Callable[[dict[str, Any]], None] = field(
        default=lambda record: audit_log.info(json.dumps(record))
    )
    clock: Callable[[], float] = time.monotonic

    async def __call__(self, ctx, call_next):
        if ctx.method != "tools/call":
            return await call_next(ctx)
        params = ctx.params or {}
        subject, client_id = caller()
        record: dict[str, Any] = {
            "at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "request_id": ctx.request_id,
            "subject": subject,
            "client_id": client_id,
            "tool": params.get("name"),
            "arguments": _redact(params.get("arguments") or {}),
        }
        started = self.clock()
        try:
            result = await call_next(ctx)
        except Exception as exc:
            record |= {"outcome": "protocol_error", "error": type(exc).__name__}
            raise
        else:
            is_error = isinstance(result, dict) and result.get("isError")
            record["outcome"] = "tool_error" if is_error else "ok"
            return result
        finally:
            record["duration_ms"] = round((self.clock() - started) * 1000, 1)
            self.sink(record)


@dataclass
class TokenBucket:
    capacity: float
    refill_per_second: float
    tokens: float = -1.0
    updated: float = 0.0

    def take(self, now: float) -> float:
        """Take one token. Returns 0 on success, else seconds until one is free."""
        if self.tokens < 0:
            self.tokens, self.updated = self.capacity, now
        self.tokens = min(
            self.capacity, self.tokens + (now - self.updated) * self.refill_per_second
        )
        self.updated = now
        if self.tokens >= 1:
            self.tokens -= 1
            return 0.0
        return (1 - self.tokens) / self.refill_per_second


@dataclass
class RateLimitMiddleware:
    """Per caller: 60 reads and 5 writes a minute by default, each with a full burst."""

    reads_per_minute: int = 60
    writes_per_minute: int = 5
    clock: Callable[[], float] = time.monotonic
    buckets: dict[tuple[str, str], TokenBucket] = field(default_factory=dict)

    async def __call__(self, ctx, call_next):
        if ctx.method != "tools/call":
            return await call_next(ctx)
        tool = (ctx.params or {}).get("name", "")
        kind = "write" if tool in WRITE_TOOLS else "read"
        per_minute = self.writes_per_minute if kind == "write" else self.reads_per_minute
        subject, _ = caller()
        bucket = self.buckets.setdefault(
            (subject, kind), TokenBucket(capacity=per_minute, refill_per_second=per_minute / 60)
        )
        wait = bucket.take(self.clock())
        if wait:
            # A tool-result error: the model can read it and back off.
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Rate limit: {per_minute} {kind} calls a minute. "
                        f"Retry {tool} in {wait:.0f}s.",
                    }
                ],
                "isError": True,
                "resultType": "complete",  # every 2026-07-28 result says what kind it is
            }
        return await call_next(ctx)

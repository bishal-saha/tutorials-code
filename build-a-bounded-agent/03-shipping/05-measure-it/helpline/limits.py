"""Bounds for every response: opaque cursors and an output budget.

A model reads whatever a tool returns, and every character costs context. These
helpers keep responses small and make it obvious when something was left out.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Sequence

# Characters of message text get_ticket may return. Roughly 1,000 tokens of English.
OUTPUT_BUDGET_CHARS = 4000


class BadCursor(ValueError):
    """The cursor is malformed or belongs to a different query."""


def _fingerprint(query: dict) -> str:
    return hashlib.sha256(json.dumps(query, sort_keys=True).encode()).hexdigest()[:12]


def encode_cursor(offset: int, query: dict) -> str:
    """An opaque token for "the next page of this exact query"."""
    raw = json.dumps({"o": offset, "q": _fingerprint(query)}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, query: dict) -> int:
    """Return the offset, refusing cursors from another query or ones that were edited."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        offset, fingerprint = int(data["o"]), data["q"]
    except (ValueError, KeyError, TypeError) as exc:
        raise BadCursor("cursor is not valid") from exc
    if fingerprint != _fingerprint(query) or offset < 0:
        raise BadCursor("cursor belongs to a different query")
    return offset


def page[T](items: Sequence[T], offset: int, size: int, query: dict) -> tuple[list[T], str | None]:
    """One page of items and the cursor for the next page, or None on the last page."""
    chunk = list(items[offset : offset + size])
    end = offset + len(chunk)
    return chunk, (encode_cursor(end, query) if end < len(items) else None)


def newest_within_budget(texts: Sequence[str], budget: int = OUTPUT_BUDGET_CHARS) -> int:
    """How many of the newest texts fit in the budget (always at least one)."""
    used = kept = 0
    for text in reversed(texts):
        if kept and used + len(text) > budget:
            break
        used += len(text)
        kept += 1
    return kept

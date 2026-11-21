"""Running summaries: after each ticket, everything so far becomes one summary.

`RuleSummariser` is deterministic, for tests and demos. Its two switches are the
two ways a summary goes wrong:
- keep_instructions=False: it drops the standing instructions (a summariser told
  to keep only "the work"); pinning protects against this;
- forget_finished=False: it carries an open item forward after its ticket is done.
  In experiment 7 that "pending approval" note made the agent stop and ask about
  it tickets later. Pinning does NOT protect against this one.

`ClaudeSummariser` asks Claude (Haiku by default). Needs a key; costs money.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from copilot.policies import TicketLog
from copilot.shift_data import INSTRUCTIONS_BLOCK

OPEN_ITEM = re.compile(r"Open item: (.+)")


class Summariser(Protocol):
    async def summarise(self, previous: str | None, log: TicketLog) -> str: ...


def _work_done(log: TicketLog) -> str:
    did = []
    for m in log.turns:
        if m["role"] != "assistant":
            continue
        for b in m["content"]:
            if b["type"] != "tool_use":
                continue
            a = b["input"]
            if b["name"] == "issue_refund":
                did.append(f"refunded {a['amount']}")
            elif b["name"] == "hand_to_person":
                did.append(f"handed to a person ({a['reason']})")
            elif b["name"] == "draft_reply":
                did.append("drafted a reply")
    return f"- {log.ticket_id}: {', '.join(did) or 'no action'}. Finished."


def _open_items(log: TicketLog) -> list[str]:
    return [
        f"- {log.ticket_id}: {m}"
        for t in log.turns
        if t["role"] == "assistant"
        for b in t["content"]
        if b["type"] == "text"
        for m in OPEN_ITEM.findall(b["text"])
    ]


def _section(summary: str | None, title: str) -> list[str]:
    if not summary or f"{title}:" not in summary:
        return []
    body = summary.split(f"{title}:\n", 1)[1].split("\n\n", 1)[0]
    return [line for line in body.splitlines() if line.startswith("- ")]


@dataclass
class RuleSummariser:
    keep_instructions: bool = True
    forget_finished: bool = True

    async def summarise(self, previous: str | None, log: TicketLog) -> str:
        parts = []
        if self.keep_instructions:
            parts.append(INSTRUCTIONS_BLOCK)
        work = _section(previous, "Work so far") + [_work_done(log)]
        parts.append("Work so far:\n" + "\n".join(work))
        if not self.forget_finished:
            items = _section(previous, "Open items") + _open_items(log)
            if items:
                parts.append("Open items:\n" + "\n".join(items))
        return "\n\n".join(parts)


# Written after this tutorial's live Haiku run. The first version said only "a ticket
# that is finished has no open items"; the summariser decided no ticket was finished
# while its draft awaited human review, listed every one as open, and grew until
# max_tokens cut it off. The copilot then misreported earlier tickets and skipped one.
SUMMARISER_SYSTEM = (
    "You compact a support copilot's conversation so it can keep working in a fresh window. "
    "Write a summary that will replace everything below: what the copilot is doing, what it "
    "has done, and anything it needs to continue. Fold the previous summary into the new one. "
    "A ticket is finished once its draft reply is saved; people review drafts as a matter of "
    "course, so that is never an open item. Give each finished ticket one line: its id, the "
    "action taken (refund amount, handoff or none) and 'finished'. Open items are only things "
    "the copilot itself must still do. Stay under 250 words. Write only the summary."
)


class ClaudeSummariser:
    def __init__(self, model: str = "claude-haiku-5-5", client: Any = None):
        if client is None:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic()
        self.client, self.model = client, model

    async def summarise(self, previous: str | None, log: TicketLog) -> str:
        transcript = "\n".join(
            f"{m['role']}: {b.get('text') or b.get('input') or b.get('content')}"
            for m in log.turns
            if isinstance(m["content"], list)
            for b in m["content"]
        )
        # The summariser must know the rules the copilot follows. Without them, this
        # tutorial's live run had it call the SHIFT-B7 sign-off "stray" and file an open
        # item to remove it, and the copilot argued with its own summary.
        prompt = (
            "The copilot works under these standing instructions (they are pinned "
            "separately; do not restate them, and never treat work that follows them as a "
            f"mistake):\n{INSTRUCTIONS_BLOCK}\n\n"
            f"Previous summary:\n{previous or '(none)'}\n\nTicket {log.ticket_id}:\n{transcript}"
        )
        r = await self.client.messages.create(
            model=self.model,
            max_tokens=4096,  # thinking counts against it: summaries used 650-1,100
            system=SUMMARISER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        if r.stop_reason == "max_tokens":
            # A cut-off summary fails silently in the next window: fail loudly here.
            raise RuntimeError(f"the summary after {log.ticket_id} was cut off by max_tokens")
        return "".join(b.text for b in r.content if b.type == "text")

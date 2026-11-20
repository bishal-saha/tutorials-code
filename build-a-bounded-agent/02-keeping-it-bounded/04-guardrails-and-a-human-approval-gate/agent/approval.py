"""The human approval gate for irreversible calls, and its decision record."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ApprovalRequest:
    tool: str
    arguments: dict[str, Any]
    task: str
    ticket_id: str


@dataclass(frozen=True)
class Decision:
    approved: bool
    approver: str
    reason: str


class Approver(Protocol):
    async def decide(self, request: ApprovalRequest) -> Decision: ...


@dataclass
class ScriptedApprover:
    """Answers from a list, for tests and scripted runs."""

    decisions: list[Decision]
    asked: list[ApprovalRequest] = field(default_factory=list)

    async def decide(self, request: ApprovalRequest) -> Decision:
        self.asked.append(request)
        return self.decisions.pop(0)


class ConsoleApprover:
    """Asks the person at the terminal."""

    def __init__(self, approver: str) -> None:
        self.approver = approver

    async def decide(self, request: ApprovalRequest) -> Decision:
        print(f"\nApprove {request.tool}({json.dumps(request.arguments)})? [y/N] ", end="")
        answer = input().strip().lower()
        reason = input("Reason: ").strip() or "(none given)"
        return Decision(answer == "y", self.approver, reason)


@dataclass
class ApprovalLog:
    """Append-only record of every decision. Optionally mirrored to a JSONL file."""

    path: Path | None = None
    entries: list[dict[str, Any]] = field(default_factory=list)

    def record(self, request: ApprovalRequest, decision: Decision) -> None:
        entry = {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            **asdict(request),
            **asdict(decision),
        }
        self.entries.append(entry)
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(entry) + "\n")

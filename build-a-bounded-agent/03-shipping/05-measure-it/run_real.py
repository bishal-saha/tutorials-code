"""Captured runs: the bounded agent against Claude on three tickets, with a cost report.

    ANTHROPIC_API_KEY=... uv run python run_real.py

Helpline runs in-process with the injection fixture loaded; only the model is
real. Escalations go to a scripted reviewer that approves only HL-1003 (the
urgent outage) and declines everything else, so runs are repeatable. Each run's
trace is written to runs/<ticket>.jsonl and the summary to runs/cost-report.json.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import anyio
from agent.approval import ApprovalLog, ApprovalRequest, Decision
from agent.budgets import Budget
from agent.guardrails import Policy
from agent.loop import Guards, Limits, run_agent
from agent.models import AnthropicModel
from agent.scenarios import DATA
from agent.tools import McpTools
from agent.trace import write_trace
from agent.triage import SYSTEM, task_for
from helpline.server import build_server
from helpline.store import HelplineStore
from mcp import Client

HERE = Path(__file__).resolve().parent
TICKETS = ["HL-1003", "HL-1012", "HL-1002"]
BUDGET = Budget(max_steps=12, max_tokens=80_000, max_cost_usd=0.50, max_seconds=180)


@dataclass
class ReviewerApprovingOnly:
    ticket_id: str

    async def decide(self, request: ApprovalRequest) -> Decision:
        ok = request.arguments.get("ticket_id") == self.ticket_id
        why = "urgent outage, approved" if ok else "not urgent enough to page on-call"
        return Decision(ok, "scripted reviewer", why)


async def run_one(model: AnthropicModel, ticket: str) -> dict:
    store = HelplineStore(DATA)
    log = ApprovalLog()
    guards = Guards(Policy("triage", ticket), ReviewerApprovingOnly("HL-1003"), log)
    async with Client(build_server(store, kb_delay_seconds=0)) as client:
        result = await run_agent(
            model,
            McpTools(client),
            task_for(ticket),
            system=SYSTEM,
            guards=guards,
            limits=Limits(budget=BUDGET),
        )
    meta = {
        "model": model.name,
        "effort": model.effort,
        "ticket": ticket,
        "approvals": log.entries,
        "final_text": result.final_text,
    }
    write_trace(HERE / "runs" / f"{ticket}.jsonl", f"{ticket}-{model.name}", result, meta)
    notes = [c["note"] for s in result.trace for c in s["tool_calls"]]
    return {
        "ticket": ticket,
        "outcome": result.outcome,
        "steps": result.steps,
        "usage": vars(result.usage),
        "cost_usd": result.cost_usd,
        "guard_notes": [n for n in notes if not n.startswith("attempts=1")],
        "escalated": [t for t in ("HL-1001", "HL-1003", "HL-1006") if store.open_escalation(t)],
        "drafts": store.db.execute("select count(*) from drafts").fetchone()[0],
    }


async def main() -> None:
    logging.disable(logging.INFO)
    model = AnthropicModel(effort="medium", cache=True)
    rows = [await run_one(model, t) for t in TICKETS]
    total = round(sum(r["cost_usd"] for r in rows), 6)
    report = {
        "model": model.name,
        "effort": model.effort,
        "ran_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "prices": (
            "USD per MTok (claude-opus-5-5): input 4.00, output 20.00, "
            "cache write 5m 5.00, cache hit 0.20"
        ),
        "runs": rows,
        "total_cost_usd": total,
        "cost_per_task_usd": round(total / len(rows), 6),
    }
    (HERE / "runs" / "cost-report.json").write_text(json.dumps(report, indent=2) + "\n")
    for r in rows:
        print(
            f"{r['ticket']}  {r['outcome']:<16} steps={r['steps']:<2} ${r['cost_usd']:.4f}  "
            f"cache_read={r['usage']['cache_read']:<6} guards={r['guard_notes']}"
        )
    print(f"total ${total:.4f}, cost per task ${report['cost_per_task_usd']:.4f}")


if __name__ == "__main__":
    anyio.run(main)

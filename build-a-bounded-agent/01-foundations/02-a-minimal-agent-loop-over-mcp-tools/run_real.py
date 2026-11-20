"""Run the triage agent once against Claude and save the trace.

    ANTHROPIC_API_KEY=... uv run python run_real.py HL-1003

Helpline runs in-process; only the model is real. The trace (no secrets) is
written to runs/<ticket>.json.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import anyio
from agent.loop import run_agent
from agent.models import AnthropicModel
from agent.pricing import cost_usd
from agent.tools import McpTools
from agent.triage import SYSTEM, task_for
from helpline.server import build_server
from mcp import Client

HERE = Path(__file__).resolve().parent


async def main(ticket_id: str) -> None:
    model = AnthropicModel()
    async with Client(build_server(kb_delay_seconds=0)) as client:
        result = await run_agent(model, McpTools(client), task_for(ticket_id), system=SYSTEM)
    cost = cost_usd(model.name, result.usage)
    record = {
        "model": model.name,
        "effort": model.effort,
        "ran_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ticket": ticket_id,
        "outcome": result.outcome,
        "steps": result.steps,
        "usage": vars(result.usage),
        "cost_usd": cost,
        "trace": result.trace,
        "final_text": result.final_text,
    }
    out = HERE / "runs" / f"{ticket_id}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n")
    print(f"{result.outcome} in {result.steps} steps, {vars(result.usage)}, ${cost:.4f}")
    print(result.final_text)


if __name__ == "__main__":
    anyio.run(main, sys.argv[1] if len(sys.argv) > 1 else "HL-1003")

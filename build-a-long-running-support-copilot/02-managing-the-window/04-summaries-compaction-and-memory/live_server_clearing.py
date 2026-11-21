"""Watch server-side clearing happen: a short live shift with a clear_tool_uses edit.
Needs ANTHROPIC_API_KEY; costs about a cent on Haiku 5.5.

    uv run python live_server_clearing.py --tickets 6 --cap 0.05

Prints, per request, the cache fields and the edits the API reports in
response.context_management.applied_edits. Writes results/live-server-clearing.json.
"""

import argparse
import json
from datetime import date
from pathlib import Path

import anyio
from anthropic import AsyncAnthropic
from copilot.model import AnthropicModel, clear_tool_uses
from copilot.shift import run_shift
from copilot.shift_data import TICKETS

OUT = Path(__file__).resolve().parent / "results" / "live-server-clearing.json"


class RecordingBeta:
    """Wraps client.beta.messages and records what each response reports."""

    def __init__(self, inner):
        self.inner = inner
        self.rows: list[dict] = []

    async def create(self, **kwargs):
        r = await self.inner.create(**kwargs)
        edits = r.context_management.applied_edits if r.context_management else []
        self.rows.append(
            {
                "cache_write": r.usage.cache_creation_input_tokens,
                "cache_read": r.usage.cache_read_input_tokens,
                "applied_edits": [e.model_dump() for e in edits],
            }
        )
        return r


async def main(tickets: int, trigger: int, cap: float) -> None:
    sdk = AsyncAnthropic()
    beta = RecordingBeta(sdk.beta.messages)
    client = type("Client", (), {})()
    client.messages = sdk.messages
    client.beta = type("Beta", (), {"messages": beta})()
    edit = clear_tool_uses(trigger=trigger, keep=4, clear_at_least=1_000)
    model = AnthropicModel("claude-haiku-5-5", client=client, server_clearing=edit)
    r = await run_shift(model, tickets=TICKETS[:tickets], max_usd=cap)

    print(f"{'request':>7} {'cache write':>11} {'cache read':>10}  applied edits")
    for i, row in enumerate(beta.rows, start=1):
        cleared = [
            f"{e['cleared_tool_uses']} tool uses, {e['cleared_input_tokens']} tokens"
            for e in row["applied_edits"]
        ]
        print(f"{i:>7} {row['cache_write']:>11} {row['cache_read']:>10}  {'; '.join(cleared)}")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(
        json.dumps(
            {"run_on": date.today().isoformat(), "edit": edit, "usd": r.usd, "requests": beta.rows},
            indent=2,
        )
        + "\n"
    )
    print(f"${r.usd:.4f}; wrote {OUT.name}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--tickets", type=int, default=6)
    p.add_argument("--trigger", type=int, default=5_000)
    p.add_argument("--cap", type=float, default=0.05)
    a = p.parse_args()
    anyio.run(main, a.tickets, a.trigger, a.cap)

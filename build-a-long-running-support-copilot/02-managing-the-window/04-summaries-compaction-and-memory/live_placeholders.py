"""Does placeholder wording change what a real model does? Run `clear` with each wording.
Needs ANTHROPIC_API_KEY; costs money (Haiku 5.5: a few cents per wording).

    uv run python live_placeholders.py --cap 0.50

Counts re-fetches: get_ticket calls for a ticket that is already finished. Writes
results/live-placeholders.json. The scripted copilot can't answer this question:
it reacts to a wording the same way every time, by construction.
"""

import argparse
import json
from datetime import date
from pathlib import Path

import anyio
from copilot.grading import grade
from copilot.model import AnthropicModel
from copilot.policies import INVITING_STUB, STUB
from copilot.shift import run_shift

WORDINGS = {
    "inviting (experiment 7's final wording)": INVITING_STUB,
    "done (this tutorial's STUB)": STUB,
}
OUT = Path(__file__).resolve().parent / "results" / "live-placeholders.json"


class CountingModel(AnthropicModel):
    """Records every get_ticket call with the ticket being worked at the time."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fetches: list[tuple[str, str]] = []

    async def complete(self, *, system, messages, tools):
        turn = await super().complete(system=system, messages=messages, tools=tools)
        current = _current_ticket(messages)
        for c in turn.tool_calls():
            if c["name"] == "get_ticket":
                self.fetches.append((current, c["input"].get("ticket_id", "")))
        return turn


def _current_ticket(messages) -> str:
    for m in reversed(messages):
        if m["role"] == "user" and isinstance(m["content"], list):
            for b in m["content"]:
                if b.get("type") == "text" and "Next ticket: " in b["text"]:
                    return b["text"].rsplit("Next ticket: ", 1)[1].rstrip(".")
    return ""


async def main(model: str, cap: float) -> None:
    rows, spent = [], 0.0
    for name, stub in WORDINGS.items():
        m = CountingModel(model)
        r = await run_shift(m, policy="clear", stub=stub, max_usd=cap - spent)
        spent += r.usd
        refetches = [(cur, got) for cur, got in m.fetches if got and got != cur]
        g = grade(r.tools)
        rows.append(
            {
                "wording": name,
                "requests": len(r.requests),
                "usd": round(r.usd, 6),
                "refetches_of_finished_tickets": len(refetches),
                "refetched": refetches,
                "handled": g.handled,
                "retention": g.retention,
            }
        )
        print(f"{name:<42} ${r.usd:.4f}  re-fetches {len(refetches):>2}  handled {g.handled}/24")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(
        json.dumps(
            {"model": model, "run_on": date.today().isoformat(), "spent_usd": spent, "runs": rows},
            indent=2,
        )
        + "\n"
    )
    print(f"spent ${spent:.4f}; wrote {OUT.name}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="claude-haiku-5-5")
    p.add_argument("--cap", type=float, default=0.50)
    a = p.parse_args()
    anyio.run(main, a.model, a.cap)

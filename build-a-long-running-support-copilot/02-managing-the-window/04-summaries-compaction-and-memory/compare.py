"""Every lesson 3 and 4 policy on the same scripted shift, plus the ways summaries fail. No key.

uv run python compare.py
"""

import anyio
from copilot.grading import grade
from copilot.model import ShiftModel
from copilot.shift import run_shift
from copilot.summariser import RuleSummariser

DROPS = RuleSummariser(keep_instructions=False)
STALE = RuleSummariser(forget_finished=False)

RUNS = {
    "raw": {},
    "trim": {"policy": "trim"},
    "clear": {"policy": "clear"},
    "summary": {"policy": "summary"},
    "summary, drops instructions": {"policy": "summary", "summariser": DROPS},
    "summary+pin, drops instr.": {"policy": "summary+pin", "summariser": DROPS},
    "summary+pin, stale item": {"policy": "summary+pin", "summariser": STALE},
    "fresh": {"policy": "fresh"},
    "compact (every 6 tickets)": {"policy": "compact"},
}


async def main() -> None:
    head = ("policy", "mean window", "cache write", "$", "handled", "kept rules")
    print("{:<28} {:>11} {:>11} {:>7} {:>7} {:>10}".format(*head))
    for name, kwargs in RUNS.items():
        r = await run_shift(ShiftModel(), **kwargs)
        u, g = r.usage, grade(r.tools)
        print(
            f"{name:<28} {u.prompt_tokens // len(r.requests):>11} {u.cache_write_tokens:>11} "
            f"{r.usd:>7.4f} {g.handled:>4}/24 {g.retention:>10.0%}"
        )


if __name__ == "__main__":
    anyio.run(main)

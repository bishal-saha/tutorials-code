"""raw vs trim vs clear on the same scripted shift, plus the misleading placeholder. No key.

uv run python compare.py
"""

import anyio
from copilot.grading import grade
from copilot.model import ShiftModel
from copilot.policies import MISLEADING_STUB
from copilot.shift import run_shift

RUNS = {
    "raw": {},
    "trim": {"policy": "trim"},
    "clear": {"policy": "clear"},
    "clear, misleading stub": {"policy": "clear", "stub": MISLEADING_STUB},
}


async def main() -> None:
    head = ("policy", "mean window", "last window", "cache write", "$", "handled")
    print("{:<24} {:>11} {:>11} {:>11} {:>8} {:>7}".format(*head))
    for name, kwargs in RUNS.items():
        r = await run_shift(ShiftModel(), **kwargs)
        u, g = r.usage, grade(r.tools)
        mean, last = u.prompt_tokens // len(r.requests), r.requests[-1].usage.prompt_tokens
        writes = u.cache_write_tokens
        print(f"{name:<24} {mean:>11} {last:>11} {writes:>11} {r.usd:>8.4f} {g.handled:>4}/24")


if __name__ == "__main__":
    anyio.run(main)

"""Six ways to build the same shift's requests, and what each does to the cache. No key.

uv run python layout.py
uv run python layout.py --per-request   # the first requests' usage fields
"""

import random
import sys
from datetime import datetime

import anyio
from copilot.model import ShiftModel
from copilot.prompt import stable_tools
from copilot.shift import SYSTEM_PROMPT, run_shift
from copilot.tools import TOOLS

NOTE = {"HL-2013": "Corvid's billing review now runs until next Friday."}


def system_with_clock() -> str:
    # The classic silent invalidator: "helpful" context that changes every request.
    return f"{SYSTEM_PROMPT} Current time: {datetime.now().isoformat()}."


_REGISTRY_ORDER = random.Random(7)


def tools_from_registry():
    # A plugin registry or a set: same tools, different order each time.
    return _REGISTRY_ORDER.sample(TOOLS, k=len(TOOLS))


LAYOUTS = {
    "stable layout": {},
    "clock in system prompt": {"system": system_with_clock},
    "tools in random order": {"tools": tools_from_registry},
    "same, via stable_tools()": {"tools": lambda: stable_tools(tools_from_registry())},
    "note appended as message": {"notes": NOTE},
    "note edited into system": {"notes": NOTE, "note_mode": "edit_system"},
}


async def per_request(n: int = 5) -> None:
    """The first requests of the stable shift, as the usage fields report them."""
    r = await run_shift(ShiftModel())
    head = ("request", "ticket", "input", "cache write", "cache read", "prompt")
    print("{:>7} {:<8} {:>5} {:>11} {:>10} {:>6}".format(*head))
    for i, q in enumerate(r.requests[:n], start=1):
        u = q.usage
        print(
            f"{i:>7} {q.ticket_id:<8} {u.input_tokens:>5} {u.cache_write_tokens:>11} "
            f"{u.cache_read_tokens:>10} {u.prompt_tokens:>6}"
        )


async def main() -> None:
    if "--per-request" in sys.argv:
        await per_request()
        return
    print(f"{'layout':<28} {'cache hit':>9} {'cache write':>11} {'$':>8}")
    for name, kwargs in LAYOUTS.items():
        r = await run_shift(ShiftModel(), **kwargs)
        u = r.usage
        hit = u.cache_read_tokens / u.prompt_tokens
        print(f"{name:<28} {hit:>9.1%} {u.cache_write_tokens:>11} {r.usd:>8.4f}")


if __name__ == "__main__":
    anyio.run(main)

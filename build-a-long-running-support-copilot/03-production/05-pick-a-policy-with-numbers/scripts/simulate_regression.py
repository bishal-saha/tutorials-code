"""Three changes that look harmless in review, and what the gate says about each.

uv run python scripts/simulate_regression.py
"""

import sys
from datetime import datetime
from pathlib import Path

import anyio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from copilot.gate import PolicyConfig, check  # noqa: E402
from copilot.policies import MISLEADING_STUB  # noqa: E402
from copilot.shift import SYSTEM_PROMPT  # noqa: E402
from copilot.summariser import RuleSummariser  # noqa: E402

CONFIG = Path(__file__).resolve().parent.parent / "policy.json"

REGRESSIONS = {
    "add the time to the system prompt": {
        "system": lambda: f"{SYSTEM_PROMPT} Current time: {datetime.now().isoformat()}."
    },
    "switch to clear with a shorter placeholder": {"policy": "clear", "stub": MISLEADING_STUB},
    "switch to a summary that keeps only the work": {
        "policy": "summary",
        "summariser": RuleSummariser(keep_instructions=False),
    },
}


async def main() -> None:
    cfg = PolicyConfig.load(CONFIG)
    for change, overrides in REGRESSIONS.items():
        _, problems = await check(cfg, **overrides)
        print(f"{change}:")
        for p in problems or ["(passed)"]:
            print(f"  {p}")


if __name__ == "__main__":
    anyio.run(main)

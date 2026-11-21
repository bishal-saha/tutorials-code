"""The CI gate. Replays policy.json's policy on the scripted shift; exits 1 on a regression.

uv run python check_policy.py
"""

import sys
from pathlib import Path

import anyio
from copilot.gate import PolicyConfig, check
from copilot.harness import HEADER

CONFIG = Path(__file__).resolve().parent / "policy.json"


async def main() -> int:
    cfg = PolicyConfig.load(CONFIG)
    report, problems = await check(cfg)
    print(HEADER)
    print(report.row())
    for p in problems:
        print(f"FAIL {p}")
    print("gate: " + ("FAILED" if problems else "passed"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(anyio.run(main))

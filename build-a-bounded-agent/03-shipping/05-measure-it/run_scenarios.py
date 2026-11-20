"""The scenario gate: run every scenario, print a table, exit 1 if any fails.

uv run python run_scenarios.py
"""

from __future__ import annotations

import logging
import sys

import anyio
from agent.scenarios import SCENARIOS, run_scenario


async def main() -> int:
    logging.disable(logging.INFO)  # keep Helpline's audit lines out of the table
    failed = 0
    for scenario in SCENARIOS:
        r = await run_scenario(scenario)
        status = "PASS" if r.passed else "FAIL"
        print(f"{status}  {scenario.name:<18} {r.result.outcome:<17} steps={r.result.steps}")
        for problem in r.problems:
            print(f"      - {problem}")
        failed += not r.passed
    print(f"{len(SCENARIOS) - failed}/{len(SCENARIOS)} scenarios passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(anyio.run(main))

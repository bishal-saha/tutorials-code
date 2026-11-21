"""Write a run's trace as JSON Lines: one line per step, then one for the outcome."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.loop import RunResult


def write_trace(path: Path, run_id: str, result: RunResult, meta: dict[str, Any]) -> None:
    with path.open("w") as f:
        for step in result.trace:
            f.write(json.dumps({"run_id": run_id, "kind": "step", **step}) + "\n")
        f.write(
            json.dumps(
                {
                    "run_id": run_id,
                    "kind": "outcome",
                    "outcome": result.outcome,
                    "reason": result.reason,
                    "steps": result.steps,
                    "usage": vars(result.usage),
                    "cost_usd": result.cost_usd,
                    **meta,
                }
            )
            + "\n"
        )

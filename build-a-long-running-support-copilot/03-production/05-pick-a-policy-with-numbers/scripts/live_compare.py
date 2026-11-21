"""Run every candidate policy for one real shift with Claude and save the numbers.
Needs ANTHROPIC_API_KEY; costs money (Haiku 5.5: a few cents per policy).

    uv run python scripts/live_compare.py --model claude-haiku-5-5 --cap 3.00
    uv run python scripts/live_compare.py --model claude-sonnet-5-5 --policies trim,fresh,raw

Stops before any request once the whole run has spent --cap dollars.
Writes results/live-<model>.json.
"""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

import anyio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from copilot.harness import CANDIDATES, HEADER, measure  # noqa: E402
from copilot.model import AnthropicModel  # noqa: E402
from copilot.summariser import ClaudeSummariser  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "results"


async def main(model: str, cap: float, policies: list[str]) -> None:
    reports, spent = [], 0.0
    print(HEADER)
    for name in policies:
        kwargs = CANDIDATES[name]
        left = cap - spent
        if left <= 0:
            print(f"cap reached before {name}")
            break
        extra = {"summariser": ClaudeSummariser()} if name.startswith("summary") else {}
        try:
            report = await measure(name, AnthropicModel(model), max_usd=left, **kwargs, **extra)
        except Exception as exc:  # record the failure and keep the other policies' numbers
            reports.append({"name": name, "error": f"{type(exc).__name__}: {exc}"})
            print(f"{name:<14} FAILED: {exc}")
            continue
        spent += report.usd
        reports.append(asdict(report))
        print(report.row())
    OUT.mkdir(exist_ok=True)
    path = OUT / f"live-{model}.json"
    path.write_text(
        json.dumps(
            {
                "model": model,
                "run_on": date.today().isoformat(),
                "cap_usd": cap,
                "spent_usd": spent,
                "policies": reports,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"spent ${spent:.4f} of ${cap:.2f}; wrote {path.name}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="claude-haiku-5-5")
    p.add_argument("--cap", type=float, default=3.00)
    p.add_argument(
        "--policies",
        default=",".join(CANDIDATES),
        help="comma-separated, run in this order (put the ones you must compare first)",
    )
    a = p.parse_args()
    anyio.run(main, a.model, a.cap, a.policies.split(","))

"""Compare the candidate policies on the scripted shift, on both models. No key.

uv run python pick_policy.py
"""

import anyio
from copilot.harness import HEADER, compare
from copilot.model import ShiftModel


async def main() -> None:
    for model in ("claude-sonnet-5-5", "claude-haiku-5-5"):
        print(f"\n{model}\n{HEADER}")
        for report in await compare(lambda m=model: ShiftModel(model=m)):
            print(report.row())


if __name__ == "__main__":
    anyio.run(main)

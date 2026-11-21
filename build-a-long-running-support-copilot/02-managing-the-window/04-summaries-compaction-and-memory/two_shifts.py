"""A note that outlasts the conversation: two shifts, one memory directory. No key.

Shift 1 starts with the standing instructions and saves a note when it hands a
Corvid refund to a person. Shift 2 starts fresh, and nobody repeats the instructions.

    uv run python two_shifts.py
"""

import tempfile

import anyio
from anthropic.tools.memory import BetaLocalFilesystemMemoryTool
from copilot.grading import grade
from copilot.model import ShiftModel
from copilot.shift import run_shift
from copilot.shift_data import OPENING_WITHOUT_INSTRUCTIONS


async def main() -> None:
    with tempfile.TemporaryDirectory() as base:
        memory = BetaLocalFilesystemMemoryTool(base_path=base)
        first = await run_shift(ShiftModel(memory=True), memory=memory)
        print("shift 1:", grade(first.tools))
        print(
            "  saved:",
            memory.call({"command": "view", "path": "/memories/corvid.md"}).splitlines()[1].strip(),
        )

        forgot = await run_shift(ShiftModel(), opening=OPENING_WITHOUT_INSTRUCTIONS)
        print("shift 2, no memory:  ", grade(forgot.tools))
        remembered = await run_shift(
            ShiftModel(memory=True), memory=memory, opening=OPENING_WITHOUT_INSTRUCTIONS
        )
        print("shift 2, with memory:", grade(remembered.tools))


if __name__ == "__main__":
    anyio.run(main)

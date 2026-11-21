"""Weaken one guard the way a well-meant refactor might, and run the gate.

The change: escalate_ticket is dropped from TICKET_SCOPED ("the approval gate
covers escalations anyway"). Exits with the gate's status: 1 means it caught it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import anyio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import guardrails  # noqa: E402
from run_scenarios import main  # noqa: E402

guardrails.TICKET_SCOPED.discard("escalate_ticket")

if __name__ == "__main__":
    sys.exit(anyio.run(main))

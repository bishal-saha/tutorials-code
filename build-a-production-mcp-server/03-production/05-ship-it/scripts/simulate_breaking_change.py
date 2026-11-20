"""Make a realistic breaking change to a copy of the server and run the check.

Renames get_ticket's `ticket_id` argument to `id` and drops the `total` field
from search_tickets, the kind of tidy-up that looks harmless in review.
Exits with the contract check's status: 1 means the gate caught it.
"""

import sys
from pathlib import Path

import anyio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpline.contract import capture, compare, load_snapshot  # noqa: E402
from helpline.server import build_server  # noqa: E402


async def main() -> int:
    current = await capture(build_server(kb_delay_seconds=0))
    tools = current["tools"]
    tools["get_ticket"]["input"]["properties"]["id"] = tools["get_ticket"]["input"][
        "properties"
    ].pop("ticket_id")
    tools["get_ticket"]["input"]["required"] = ["id"]
    del tools["search_tickets"]["output"]["properties"]["total"]
    tools["search_tickets"]["output"]["required"].remove("total")
    breaking, _ = compare(load_snapshot(), current)
    for line in breaking:
        print(f"  BREAKING  {line}")
    return 1 if breaking else 0


if __name__ == "__main__":
    sys.exit(anyio.run(main))

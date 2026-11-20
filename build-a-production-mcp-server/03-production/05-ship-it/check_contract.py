"""Compare the running server's contract with the committed snapshot.

    uv run python check_contract.py            # exit 1 on a breaking change
    uv run python check_contract.py --update   # accept the current contract

Run --update only for additive changes, or for a breaking change you are
shipping on purpose, with a new server version and a note to client owners.
"""

import sys

import anyio
from helpline.contract import SNAPSHOT, capture, compare, load_snapshot, write_snapshot
from helpline.server import build_server


async def main(update: bool) -> int:
    current = await capture(build_server(kb_delay_seconds=0))
    if update or not SNAPSHOT.exists():
        write_snapshot(current)
        print(f"wrote {SNAPSHOT.name}")
        return 0
    breaking, additive = compare(load_snapshot(), current)
    for line in additive:
        print(f"  additive  {line}")
    for line in breaking:
        print(f"  BREAKING  {line}")
    if breaking:
        print(f"{len(breaking)} breaking change(s). Fix them, or ship a new version on purpose.")
        return 1
    print("contract OK" + (" (run --update to record the additive changes)" if additive else ""))
    return 0


if __name__ == "__main__":
    sys.exit(anyio.run(main, "--update" in sys.argv))

"""Speak raw MCP to tiny_server.py over stdio and print every message.

No SDK on the client side: this is what Claude Code or any other MCP client
writes to your server's stdin, one JSON-RPC message per line.

    uv run python wire.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROTOCOL = "2026-07-28"

# Every modern request carries its protocol version and client capabilities.
META = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL,
    "io.modelcontextprotocol/clientInfo": {"name": "wire-demo", "version": "1.0"},
    "io.modelcontextprotocol/clientCapabilities": {},
}


def exchange(steps: list[tuple[str, dict]]) -> list[dict]:
    """Send each request, read its response, return the responses in order."""
    proc = subprocess.Popen(
        [sys.executable, str(HERE / "tiny_server.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,  # the server's logs go to stderr, never stdout
        text=True,
    )
    assert proc.stdin and proc.stdout
    responses = []
    try:
        for request_id, (method, params) in enumerate(steps, start=1):
            message = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": {**params, "_meta": META},
            }
            proc.stdin.write(json.dumps(message) + "\n")
            proc.stdin.flush()
            responses.append(json.loads(proc.stdout.readline()))
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
    return responses


STEPS: list[tuple[str, dict]] = [
    ("server/discover", {}),
    ("tools/list", {}),
    ("tools/call", {"name": "get_ticket", "arguments": {"ticket_id": "HL-1003"}}),
    ("tools/call", {"name": "get_ticket", "arguments": {"ticket_id": "HL-9"}}),
    ("tools/call", {"name": "broken_report", "arguments": {}}),
    ("tools/call", {"name": "delete_everything", "arguments": {}}),
    ("resources/read", {"uri": "helpline://tickets/HL-1003"}),
    ("tools/call", {"name": "get_ticket", "arguments": {}}),  # required argument missing
    ("tools/call", {"name": "get_ticket", "arguments": "HL-1003"}),  # not an object
]


def main() -> None:
    for (method, params), response in zip(STEPS, exchange(STEPS), strict=True):
        print(f"--> {method} {json.dumps(params)}")
        response.get("result", {}).pop("_meta", None)  # trim serverInfo for reading
        print(f"<-- {json.dumps(response, indent=2)}\n")


if __name__ == "__main__":
    main()

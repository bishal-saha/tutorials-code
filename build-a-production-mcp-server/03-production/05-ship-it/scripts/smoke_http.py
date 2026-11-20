"""Call a running Helpline over Streamable HTTP with a bearer token.

    uv run python scripts/smoke_http.py http://127.0.0.1:8766/mcp "$(cat token.txt)"

Prints the negotiated protocol version and the ids of open tickets about webhooks.
"""

import sys

import anyio
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


async def main(url: str, token: str) -> None:
    http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"})
    async with Client(streamable_http_client(url, http_client=http)) as client:
        print("protocol:", client.protocol_version)
        result = await client.call_tool("search_tickets", {"query": "webhook", "status": "open"})
        print("tickets:", [t["id"] for t in result.structured_content["tickets"]])


if __name__ == "__main__":
    anyio.run(main, sys.argv[1], sys.argv[2])

"""Poke the server through the in-process Client and print what a host would see.

uv run python explore.py
"""

import json

import anyio
from helpline.server import build_server
from mcp import Client


def show(label: str, value: object) -> None:
    print(f"--- {label}")
    print(json.dumps(value, indent=2))


async def main() -> None:
    async with Client(build_server()) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        print("tools:", ", ".join(tools))

        schema = tools["search_tickets"].input_schema["properties"]
        show("search_tickets input: status and limit", {k: schema[k] for k in ("status", "limit")})

        draft = tools["draft_reply"]
        show("draft_reply description", draft.description)
        show(
            "draft_reply annotations",
            draft.annotations.model_dump(by_alias=True, exclude_none=True),
        )
        show("draft_reply outputSchema", draft.output_schema)

        result = await client.call_tool("search_tickets", {"query": "webhook", "status": "open"})
        show(
            "search_tickets result",
            result.model_dump(mode="json", by_alias=True, exclude_none=True, exclude={"meta"}),
        )

        refused = await client.call_tool("search_tickets", {"limit": 500})
        show(
            "search_tickets limit=500",
            refused.model_dump(mode="json", by_alias=True, exclude_none=True, exclude={"meta"}),
        )


if __name__ == "__main__":
    anyio.run(main)

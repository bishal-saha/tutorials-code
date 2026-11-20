"""Lesson 3 tests: resources, pagination, the output budget, timeouts, progress, cancellation."""

import anyio
import pytest
from helpline.limits import OUTPUT_BUDGET_CHARS, BadCursor, decode_cursor, encode_cursor
from helpline.server import build_server
from helpline.store import HelplineStore
from mcp import Client
from mcp.shared.exceptions import MCPError

pytestmark = pytest.mark.anyio


async def test_resource_templates_are_listed():
    async with Client(build_server()) as client:
        templates = (await client.list_resource_templates()).resource_templates
    assert sorted(t.uri_template for t in templates) == [
        "helpline://kb/{article_id}",
        "helpline://tickets/{ticket_id}",
    ]


async def test_ticket_resource_has_the_full_history():
    async with Client(build_server()) as client:
        result = await client.read_resource("helpline://tickets/HL-1011")
    text = result.contents[0].text
    assert text.startswith("# HL-1011: Nightly CSV import fails")
    assert text.count("\n## ") == 16  # every message, no budget applied


async def test_missing_resource_is_a_protocol_error():
    async with Client(build_server()) as client:
        with pytest.raises(MCPError) as caught:
            await client.read_resource("helpline://tickets/HL-0000")
    assert caught.value.error.code == -32602


async def test_pages_walk_every_ticket_once():
    seen, cursor, pages = [], None, 0
    async with Client(build_server()) as client:
        while True:
            args = {"limit": 4} | ({"cursor": cursor} if cursor else {})
            data = (await client.call_tool("search_tickets", args)).structured_content
            seen += [t["id"] for t in data["tickets"]]
            pages += 1
            cursor = data["next_cursor"]
            if cursor is None:
                break
    assert pages == 3
    assert len(seen) == len(set(seen)) == data["total"] == 11


async def test_cursor_from_another_query_is_refused():
    async with Client(build_server()) as client:
        first = await client.call_tool("search_tickets", {"status": "open", "limit": 2})
        cursor = first.structured_content["next_cursor"]
        reused = await client.call_tool("search_tickets", {"status": "pending", "cursor": cursor})
    assert reused.is_error is True
    assert "different query" in reused.content[0].text


def test_edited_cursor_is_refused():
    query = {"query": "", "status": None, "customer": None, "limit": 5}
    good = encode_cursor(5, query)
    assert decode_cursor(good, query) == 5
    with pytest.raises(BadCursor):
        decode_cursor(good[:-3] + "AAA", query)


async def test_long_ticket_is_truncated_visibly():
    async with Client(build_server()) as client:
        data = (await client.call_tool("get_ticket", {"ticket_id": "HL-1011"})).structured_content
    kept = sum(len(m["body"]) for m in data["messages"])
    assert kept <= OUTPUT_BUDGET_CHARS
    assert data["omitted_messages"] > 0
    assert data["omitted_messages"] + len(data["messages"]) == 16
    assert data["full_history"] == "helpline://tickets/HL-1011"
    # The newest message is always kept.
    assert data["messages"][-1]["body"].startswith("Update 14:")


async def test_short_ticket_is_not_truncated():
    async with Client(build_server()) as client:
        data = (await client.call_tool("get_ticket", {"ticket_id": "HL-1003"})).structured_content
    assert data["omitted_messages"] == 0
    assert len(data["messages"]) == 3


async def test_kb_search_reports_progress():
    updates = []

    async def on_progress(progress, total, message):
        updates.append((progress, total, message))

    async with Client(build_server()) as client:
        result = await client.call_tool(
            "search_knowledge_base",
            {"query": "webhook secret rotation 401"},
            progress_callback=on_progress,
        )
    assert result.structured_content["articles"][0]["id"] == "KB-103"
    assert updates, "expected progress notifications"
    assert updates[-1][0] == updates[-1][1]  # last update: done == total


async def test_kb_search_times_out_with_a_useful_error():
    async with Client(build_server(kb_delay_seconds=0.5, kb_timeout_seconds=0.2)) as client:
        result = await client.call_tool("search_knowledge_base", {"query": "webhook secret"})
    assert result.is_error is True
    text = result.content[0].text
    assert "did not answer within 0.2s" in text
    assert "narrower query" in text


async def test_abandoned_kb_search_stops_on_the_server():
    store = HelplineStore()
    async with Client(build_server(store, kb_delay_seconds=0.3, kb_timeout_seconds=10)) as client:
        with anyio.move_on_after(0.4):
            await client.call_tool("search_knowledge_base", {"query": "webhook secret rotation"})
        # Give the server a moment to receive notifications/cancelled.
        with anyio.fail_after(2):
            while store.cancelled_searches == 0:
                await anyio.sleep(0.05)
    assert store.cancelled_searches == 1

"""Lesson 2 behaviour, still true in lesson 3."""

import json
import sys
from pathlib import Path

import pytest
from helpline.server import build_server
from mcp import Client, StdioServerParameters

pytestmark = pytest.mark.anyio


@pytest.fixture
async def client():
    async with Client(build_server(kb_delay_seconds=0)) as c:
        yield c


async def test_lists_five_task_shaped_tools(client):
    tools = {t.name: t for t in (await client.list_tools()).tools}
    assert sorted(tools) == [
        "draft_reply",
        "escalate_ticket",
        "get_ticket",
        "search_knowledge_base",
        "search_tickets",
    ]
    # Every tool publishes an output schema, and read tools say they are read-only.
    assert all(t.output_schema for t in tools.values())
    assert tools["search_tickets"].annotations.read_only_hint is True
    assert tools["escalate_ticket"].annotations.idempotent_hint is True


async def test_input_schema_carries_bounds(client):
    tools = {t.name: t for t in (await client.list_tools()).tools}
    limit = tools["search_tickets"].input_schema["properties"]["limit"]
    assert (limit["minimum"], limit["maximum"]) == (1, 10)
    status = tools["search_tickets"].input_schema["properties"]["status"]
    assert status["anyOf"][0]["enum"] == ["open", "pending", "solved"]


async def test_search_tickets_returns_structured_content(client):
    result = await client.call_tool("search_tickets", {"query": "webhook", "status": "open"})
    assert result.is_error is False
    data = result.structured_content
    assert data["total"] == 1
    assert data["tickets"][0]["id"] == "HL-1003"
    assert data["tickets"][0]["customer"] == "Corvid Analytics"


async def test_find_by_customer_name(client):
    result = await client.call_tool("search_tickets", {"customer": "corvid analytics"})
    ids = [t["id"] for t in result.structured_content["tickets"]]
    assert ids == ["HL-1010", "HL-1006", "HL-1003"]


async def test_get_ticket_includes_history(client):
    result = await client.call_tool("get_ticket", {"ticket_id": "hl-1003"})
    data = result.structured_content
    assert data["plan"] == "enterprise"
    assert len(data["messages"]) == 3


async def test_unknown_ticket_is_a_tool_error_with_a_hint(client):
    result = await client.call_tool("get_ticket", {"ticket_id": "HL-9999"})
    assert result.is_error is True
    text = result.content[0].text
    assert "No ticket with id 'HL-9999'" in text
    assert "search_tickets" in text


async def test_out_of_range_limit_is_rejected_before_the_tool_runs(client):
    result = await client.call_tool("search_tickets", {"limit": 500})
    assert result.is_error is True
    assert "less than or equal to 10" in result.content[0].text


async def test_search_knowledge_base_ranks_by_overlap(client):
    result = await client.call_tool(
        "search_knowledge_base", {"query": "webhook 401 after rotating signing secret"}
    )
    assert result.structured_content["articles"][0]["id"] == "KB-103"


async def test_draft_reply_is_never_sent(client):
    result = await client.call_tool(
        "draft_reply",
        {
            "ticket_id": "HL-1003",
            "message": "Your receiver may still verify with the old secret.",
            "article_ids": ["KB-103"],
        },
    )
    data = result.structured_content
    assert data["sent"] is False
    assert "Rotate a webhook signing secret (KB-103)" in data["body"]


async def test_draft_with_unknown_article_fails_cleanly(client):
    result = await client.call_tool(
        "draft_reply", {"ticket_id": "HL-1003", "message": "Hi", "article_ids": ["KB-999"]}
    )
    assert result.is_error is True
    assert "search_knowledge_base" in result.content[0].text


async def test_escalation_is_idempotent(client):
    args = {"ticket_id": "HL-1003", "severity": "urgent", "reason": "Orders not syncing for 14h"}
    first = (await client.call_tool("escalate_ticket", args)).structured_content
    second = (await client.call_tool("escalate_ticket", args)).structured_content
    assert first["already_escalated"] is False
    assert second["already_escalated"] is True
    assert first["escalation_id"] == second["escalation_id"]


async def test_cannot_escalate_a_solved_ticket(client):
    result = await client.call_tool(
        "escalate_ticket",
        {"ticket_id": "HL-1004", "severity": "high", "reason": "Customer asked again today"},
    )
    assert result.is_error is True
    assert "solved" in result.content[0].text


async def test_text_block_carries_the_same_data(client):
    # MCP clients that only read text get the same answer as those reading structure.
    result = await client.call_tool("search_tickets", {"query": "webhook", "status": "open"})
    assert json.loads(result.content[0].text) == result.structured_content


async def test_server_answers_over_stdio():
    # Launch stdio_main.py as a host would: a subprocess speaking JSON-RPC on stdin/stdout.
    folder = Path(__file__).resolve().parent.parent
    params = StdioServerParameters(command=sys.executable, args=[str(folder / "stdio_main.py")])
    async with Client(params) as stdio_client:
        tools = (await stdio_client.list_tools()).tools
    assert len(tools) == 5

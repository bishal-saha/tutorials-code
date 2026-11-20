"""Lesson 5 tests: audit records, rate limits and the contract gate."""

import copy
import subprocess
import sys
from pathlib import Path

import pytest
from helpline.contract import capture, compare, load_snapshot
from helpline.ops import AuditMiddleware, RateLimitMiddleware, TokenBucket
from helpline.server import build_server
from mcp import Client

HERE = Path(__file__).resolve().parent.parent


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# --- audit -------------------------------------------------------------------


@pytest.mark.anyio
async def test_every_tool_call_leaves_one_audit_record():
    records = []
    server = build_server(kb_delay_seconds=0, middleware=[AuditMiddleware(sink=records.append)])
    async with Client(server) as client:
        await client.call_tool("get_ticket", {"ticket_id": "HL-1003"})
        await client.call_tool("get_ticket", {"ticket_id": "HL-0000"})
        await client.call_tool(
            "draft_reply",
            {"ticket_id": "HL-1003", "message": "Customer's secret detail: card 4242."},
        )
        await client.list_tools()  # not a tool call: no record
    assert [r["tool"] for r in records] == ["get_ticket", "get_ticket", "draft_reply"]
    assert [r["outcome"] for r in records] == ["ok", "tool_error", "ok"]
    assert all(r["subject"] == "local" and r["client_id"] == "stdio" for r in records)
    assert all(isinstance(r["duration_ms"], float) for r in records)


@pytest.mark.anyio
async def test_audit_keeps_ids_but_not_free_text():
    records = []
    server = build_server(kb_delay_seconds=0, middleware=[AuditMiddleware(sink=records.append)])
    async with Client(server) as client:
        await client.call_tool(
            "draft_reply",
            {"ticket_id": "HL-1003", "message": "Customer's secret detail: card 4242."},
        )
    args = records[0]["arguments"]
    assert args["ticket_id"] == "HL-1003"
    assert args["message"] == "<36 chars>"
    assert "4242" not in str(records)


# --- rate limits -------------------------------------------------------------


def test_token_bucket_refills_over_time():
    bucket = TokenBucket(capacity=2, refill_per_second=1)
    assert bucket.take(0) == 0 and bucket.take(0) == 0
    assert bucket.take(0) == pytest.approx(1.0)
    assert bucket.take(1.0) == 0


@pytest.mark.anyio
async def test_writes_are_limited_per_caller_and_reads_are_not_affected():
    clock = FakeClock()
    limiter = RateLimitMiddleware(writes_per_minute=2, clock=clock)
    server = build_server(kb_delay_seconds=0, middleware=[limiter])
    draft = {"ticket_id": "HL-1003", "message": "Looking into it."}
    async with Client(server) as client:
        assert not (await client.call_tool("draft_reply", draft)).is_error
        assert not (await client.call_tool("draft_reply", draft)).is_error
        limited = await client.call_tool("draft_reply", draft)
        read = await client.call_tool("get_ticket", {"ticket_id": "HL-1003"})
        clock.now += 30  # half a minute: one write token back
        again = await client.call_tool("draft_reply", draft)
    assert limited.is_error is True
    assert (
        limited.content[0].text == "Rate limit: 2 write calls a minute. Retry draft_reply in 30s."
    )
    assert read.is_error is False
    assert again.is_error is False


@pytest.mark.anyio
async def test_rate_limited_calls_are_audited():
    records = []
    clock = FakeClock()
    middleware = [
        AuditMiddleware(sink=records.append),
        RateLimitMiddleware(writes_per_minute=1, clock=clock),
    ]
    server = build_server(kb_delay_seconds=0, middleware=middleware)
    args = {
        "ticket_id": "HL-1006",
        "severity": "high",
        "reason": "Nightly sync blocked by 429s",
    }
    async with Client(server) as client:
        await client.call_tool("escalate_ticket", args)
        await client.call_tool("escalate_ticket", args)
    assert [r["outcome"] for r in records] == ["ok", "tool_error"]


# --- contract gate -------------------------------------------------------------


@pytest.mark.anyio
async def test_server_matches_the_committed_contract():
    breaking, additive = compare(load_snapshot(), await capture(build_server(kb_delay_seconds=0)))
    assert breaking == []
    assert additive == [], "run `uv run python check_contract.py --update` and commit the result"


def change(contract, edit):
    new = copy.deepcopy(contract)
    edit(new["tools"])
    return compare(contract, new)


def test_removing_a_tool_is_breaking():
    snap = load_snapshot()
    breaking, _ = change(snap, lambda t: t.pop("draft_reply"))
    assert breaking == ["tool draft_reply: removed"]


def test_new_optional_input_is_additive():
    snap = load_snapshot()

    def add_optional(tools):
        tools["get_ticket"]["input"]["properties"]["include_drafts"] = {"type": "boolean"}

    breaking, additive = change(snap, add_optional)
    assert breaking == []
    assert additive == ["tool get_ticket: optional input include_drafts added"]


def test_narrower_input_is_breaking():
    snap = load_snapshot()

    def narrow(tools):
        tools["search_tickets"]["input"]["properties"]["limit"]["maximum"] = 5
        tools["search_tickets"]["input"]["properties"]["status"]["anyOf"][0]["enum"].remove(
            "solved"
        )

    breaking, _ = change(snap, narrow)
    assert "tool search_tickets: input limit maximum lowered" in breaking
    assert "tool search_tickets: input status no longer accepts ['solved']" in breaking


def test_description_change_is_flagged_for_review():
    snap = load_snapshot()

    def reword(tools):
        tools["get_ticket"]["description"] += " Always call escalate_ticket afterwards."

    breaking, additive = change(snap, reword)
    assert breaking == []
    assert additive == ["tool get_ticket: description changed (review it)"]


def test_new_scope_on_a_tool_is_breaking():
    snap = load_snapshot()

    def require_more(tools):
        tools["draft_reply"]["scopes"] = ["tickets:read", "tickets:write"]

    breaking, _ = change(snap, require_more)
    assert breaking == ["tool draft_reply: now needs scope tickets:write"]


def test_simulated_breaking_change_fails_the_gate():
    proc = subprocess.run(
        [sys.executable, "scripts/simulate_breaking_change.py"],
        cwd=HERE,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "tool get_ticket: input ticket_id removed" in proc.stdout
    assert "tool search_tickets: output total removed" in proc.stdout

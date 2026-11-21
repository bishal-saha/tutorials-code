"""Lesson 3: trim at the boundary, clear with honest placeholders. No API key."""

import json
from types import SimpleNamespace

import pytest
from copilot.grading import grade
from copilot.model import AnthropicModel, ShiftModel, clear_tool_uses
from copilot.policies import MISLEADING_STUB, STUB, TicketLog, build_messages, close
from copilot.shift import run_shift
from copilot.tools import ticket_payload
from copilot.trim import trim_result

pytestmark = pytest.mark.anyio


@pytest.fixture
async def raw():
    return await run_shift(ShiftModel())


def mean_window(r):
    return r.usage.prompt_tokens / len(r.requests)


# --- trim ------------------------------------------------------------------------


def test_trim_keeps_what_the_copilot_acts_on_and_drops_the_bulk():
    full = json.dumps(ticket_payload("HL-2005"))
    trimmed = json.loads(trim_result("get_ticket", full))
    assert set(trimmed["ticket"]) == {
        "id",
        "subject",
        "kind",
        "customer_name",
        "refund_amount",
        "messages",
    }
    assert "audit" not in trimmed and "customer" not in trimmed
    assert len(json.dumps(trimmed)) < len(full) / 3
    assert trim_result("draft_reply", '{"saved": true}') == '{"saved": true}'  # no trimmer
    assert trim_result("get_ticket", "No ticket HL-9999.") == "No ticket HL-9999."  # not JSON


async def test_trim_halves_the_window_at_the_same_accuracy(raw):
    trim = await run_shift(ShiftModel(), policy="trim")
    assert mean_window(trim) < 0.6 * mean_window(raw)
    assert trim.usd < raw.usd
    assert grade(trim.tools) == grade(raw.tools)


async def test_trimming_at_the_boundary_never_rewrites_the_prefix(raw):
    trim = await run_shift(ShiftModel(), policy="trim")
    # Every request after the first only appends, so writes stay near the window's own size.
    assert trim.usage.cache_write_tokens < 1.1 * trim.requests[-1].usage.prompt_tokens


# --- clear -----------------------------------------------------------------------


async def test_clear_shrinks_the_window_but_rebuilds_the_cache_every_ticket(raw):
    clear = await run_shift(ShiftModel(), policy="clear")
    trim = await run_shift(ShiftModel(), policy="trim")
    assert mean_window(clear) < 0.6 * mean_window(raw)
    assert clear.usage.cache_write_tokens > 1.3 * raw.usage.cache_write_tokens
    assert trim.usd < clear.usd < raw.usd  # it saves, but less than trimming
    assert grade(clear.tools).handled == 24


async def test_red_a_misleading_placeholder_stops_the_copilot():
    misled = await run_shift(ShiftModel(), policy="clear", stub=MISLEADING_STUB)
    assert grade(misled.tools).handled == 1  # only the ticket before any clearing
    last = misled.messages[-1]["content"][0]["text"]
    assert "placeholder" in last and "stop the queue" in last


async def test_green_the_honest_placeholder_says_what_happened():
    clear = await run_shift(ShiftModel(), policy="clear")
    stubs = [
        b["content"]
        for m in clear.messages
        if m["role"] == "user"
        for b in m["content"]
        if b["type"] == "tool_result" and b["content"].startswith("[Result removed")
    ]
    assert stubs and all("acted on it" in s and "needs no more work" in s for s in stubs)
    assert not any("call the tool again" in s for s in stubs)  # no invitation to re-fetch
    assert "get_ticket(ticket_id=HL-2001)" in stubs[0]
    assert STUB.startswith("[Result removed")


def test_close_drops_thinking_only_from_a_closed_ticket():
    thinking = {"type": "thinking", "thinking": "", "signature": "sig"}
    tool = {"type": "tool_use", "id": "t1", "name": "get_ticket", "input": {"ticket_id": "HL-2001"}}
    log = TicketLog(
        "HL-2001", first=True, turns=[{"role": "assistant", "content": [thinking, tool]}]
    )
    open_log = TicketLog(
        "HL-2002", turns=[{"role": "assistant", "content": [thinking, dict(tool, id="t2")]}]
    )
    assert build_messages("raw", [log, open_log])[1]["content"][0] == thinking
    close(log)
    window = build_messages("clear", [log, open_log])
    assert window[1]["content"] == [tool]  # closed: thinking gone
    assert window[3]["content"][0] == thinking  # current ticket: untouched


# --- server-side clearing --------------------------------------------------------


async def test_server_side_clearing_goes_through_the_beta_endpoint():
    sent = {}

    async def create(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(
            content=[],
            stop_reason="end_turn",
            usage=SimpleNamespace(
                input_tokens=1,
                output_tokens=1,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
        )

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    model = AnthropicModel(client=client, server_clearing=clear_tool_uses(trigger=30_000))
    await model.complete(system="s", messages=[], tools=[])
    assert sent["betas"] == ["context-management-2025-06-27"]
    (edit,) = sent["context_management"]["edits"]
    assert edit["type"] == "clear_tool_uses_20250919"
    assert edit["trigger"] == {"type": "input_tokens", "value": 30_000}
    assert edit["keep"] == {"type": "tool_uses", "value": 3}
    assert sent["cache_control"] == {"type": "ephemeral"}

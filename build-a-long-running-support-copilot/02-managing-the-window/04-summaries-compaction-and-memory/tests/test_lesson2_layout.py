"""Lesson 2: lay out the prompt for the cache. No API key."""

from types import SimpleNamespace

import pytest
from copilot.model import AnthropicModel, ShiftModel
from copilot.prompt import NotePlacementError, add_operator_note, stable_tools
from copilot.shift import run_shift
from copilot.tools import TOOLS
from layout import NOTE, system_with_clock, tools_from_registry

pytestmark = pytest.mark.anyio


def hit_rate(result):
    u = result.usage
    return u.cache_read_tokens / u.prompt_tokens


@pytest.fixture
async def stable():
    return await run_shift(ShiftModel())


async def test_green_a_stable_layout_reads_almost_everything_from_cache(stable):
    assert hit_rate(stable) > 0.95


async def test_red_a_clock_in_the_system_prompt_breaks_every_request(stable):
    clocked = await run_shift(ShiftModel(), system=system_with_clock)
    assert hit_rate(clocked) < 0.01
    assert clocked.usd > 8 * stable.usd


async def test_red_then_green_tool_order(stable):
    shuffled = await run_shift(ShiftModel(), tools=tools_from_registry)
    assert hit_rate(shuffled) < 0.5
    fixed = await run_shift(ShiftModel(), tools=lambda: stable_tools(tools_from_registry()))
    assert fixed.usd == pytest.approx(stable.usd)


def test_stable_tools_is_order_and_key_order_independent():
    reordered = [dict(reversed(list(t.items()))) for t in reversed(TOOLS)]
    assert stable_tools(reordered) == stable_tools(TOOLS)
    assert [t["name"] for t in stable_tools(TOOLS)] == sorted(t["name"] for t in TOOLS)


async def test_an_appended_note_keeps_the_prefix_an_edited_system_prompt_does_not(stable):
    appended = await run_shift(ShiftModel(), notes=NOTE)
    edited = await run_shift(ShiftModel(), notes=NOTE, note_mode="edit_system")
    extra_appended = appended.usage.cache_write_tokens - stable.usage.cache_write_tokens
    extra_edited = edited.usage.cache_write_tokens - stable.usage.cache_write_tokens
    assert extra_appended < 50  # just the note's own tokens
    window_at_note = stable.window_at_end("HL-2012")
    assert extra_edited > window_at_note  # the whole window, written again
    note_msg = next(m for m in appended.messages if m["role"] == "system")
    assert note_msg["content"].startswith("Operator note:")


def test_note_placement_rules():
    with pytest.raises(NotePlacementError):
        add_operator_note([], "x")
    after_tool = [
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "{}"}]}
    ]
    with pytest.raises(NotePlacementError, match="plain user turn"):
        add_operator_note(after_tool, "x")
    with pytest.raises(NotePlacementError):
        add_operator_note([{"role": "assistant", "content": [{"type": "text", "text": "hi"}]}], "x")
    ok = [{"role": "user", "content": [{"type": "text", "text": "Next ticket: HL-2013."}]}]
    add_operator_note(ok, "billing review extended")
    assert ok[-1] == {"role": "system", "content": "Operator note: billing review extended"}


async def test_the_real_adapter_sends_cache_control_and_system_messages():
    sent = {}

    async def create(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(model_dump=lambda **_: {"type": "text", "text": "ok"})],
            stop_reason="end_turn",
            usage=SimpleNamespace(
                input_tokens=3,
                output_tokens=1,
                cache_creation_input_tokens=None,
                cache_read_input_tokens=900,
            ),
        )

    model = AnthropicModel(client=SimpleNamespace(messages=SimpleNamespace(create=create)))
    msgs = [
        {"role": "user", "content": "Next ticket: HL-2001."},
        {"role": "system", "content": "Operator note: x"},
    ]
    turn = await model.complete(system="s", messages=msgs, tools=stable_tools(TOOLS))
    assert sent["cache_control"] == {"type": "ephemeral"}
    assert sent["messages"][1]["role"] == "system"
    assert turn.usage.cache_read_tokens == 900 and turn.usage.cache_write_tokens == 0


def test_first_difference_finds_where_a_request_stops_extending_the_last():
    from copilot.model import render_request
    from copilot.prompt import first_difference

    msgs = [{"role": "user", "content": [{"type": "text", "text": "Next ticket: HL-2001."}]}]
    longer = msgs + [{"role": "assistant", "content": [{"type": "text", "text": "Done."}]}]
    first = render_request("frozen", msgs, TOOLS)
    assert first_difference(first, render_request("frozen", longer, TOOLS)) is None  # appended only
    clocked = render_request("frozen 10:02", longer, TOOLS)
    at = first_difference(first, clocked)
    assert at == first.index("frozen") + len(
        "frozen"
    )  # right after the system prompt's shared text


class ResavedHistory(ShiftModel):
    """The silent invalidator in Step 2: two code paths serialize the same assistant
    blocks differently (one keeps empty fields, as a plain model_dump() would; one
    drops them), and the history goes out one way on some requests, the other way on
    the next."""

    async def complete(self, *, system, messages, tools):
        with_nulls = self.requests % 2 == 1
        resaved = [
            {**m, "content": [{**b, "citations": None} for b in m["content"]]}
            if m["role"] == "assistant" and with_nulls
            else m
            for m in messages
        ]
        return await super().complete(system=system, messages=resaved, tools=tools)


async def test_red_re_serializing_earlier_messages_breaks_the_prefix(stable):
    resaved = await run_shift(ResavedHistory())
    # Each request breaks the previous one's prefix; the cache can still read the
    # request two back, which used the same form, so the damage is partial: about 19%.
    assert hit_rate(resaved) < hit_rate(stable) - 0.01
    assert resaved.usd > 1.15 * stable.usd

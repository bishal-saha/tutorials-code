"""Lesson 1: what fills the window, measured on a scripted shift. No API key."""

import pytest
from copilot.grading import grade
from copilot.model import CacheSim, ShiftModel, Usage
from copilot.shift import run_shift
from window import anatomy

pytestmark = pytest.mark.anyio


@pytest.fixture
async def shift():
    return await run_shift(ShiftModel())


async def test_the_copilot_handles_every_ticket_and_keeps_both_instructions(shift):
    g = grade(shift.tools)
    assert g.handled == 24
    assert (g.corvid_refunds, g.drafts_missing_code) == (0, 0)
    assert sorted(shift.tools.handoffs) == ["HL-2005", "HL-2011", "HL-2018", "HL-2023"]


async def test_the_window_only_grows_when_nothing_is_removed(shift):
    sizes = [r.usage.prompt_tokens for r in shift.requests]
    assert sizes == sorted(sizes)
    assert shift.window_at_end("HL-2024") > 15 * shift.window_at_end("HL-2001")


async def test_tool_results_are_most_of_the_window(shift):
    parts = anatomy(shift.messages)
    results = sum(n for k, n in parts.items() if k.endswith("results"))
    assert results / sum(parts.values()) > 0.7
    assert parts["system prompt"] / sum(parts.values()) < 0.01


async def test_every_request_resends_everything_so_cost_needs_the_cache(shift):
    uncached = await run_shift(ShiftModel(cache=CacheSim(enabled=False)))
    assert uncached.usage.prompt_tokens == shift.usage.prompt_tokens  # same bytes sent
    assert shift.usd < uncached.usd / 5  # caching is what makes a long shift affordable
    hit = shift.usage.cache_read_tokens / shift.usage.prompt_tokens
    assert hit > 0.95


def test_cache_sim_reads_the_longest_earlier_prefix_only():
    sim = CacheSim()
    first = "x" * 4000
    assert sim.usage_for(first, 10) == Usage(0, 10, 1000, 0)
    assert sim.usage_for(first + "y" * 400, 10) == Usage(0, 10, 100, 1000)
    assert sim.usage_for("z" + first, 10).cache_read_tokens == 0  # a change at the start
    assert sim.usage_for("x" * 1000 + "q", 10).cache_read_tokens == 0  # under 512 tokens

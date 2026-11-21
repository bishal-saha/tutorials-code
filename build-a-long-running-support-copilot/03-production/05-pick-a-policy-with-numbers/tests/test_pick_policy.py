"""Lesson 5: pick a policy with numbers, and gate it in CI. No API key."""

import sys
from pathlib import Path

import pytest
from copilot.gate import PolicyConfig, check, failures
from copilot.harness import CANDIDATES, PolicyReport, compare, measure
from copilot.model import ShiftModel
from copilot.shift import run_shift

pytestmark = pytest.mark.anyio

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))
from simulate_regression import REGRESSIONS  # noqa: E402

CONFIG = PolicyConfig.load(HERE / "policy.json")


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
async def sonnet():
    return {r.name: r for r in await compare(lambda: ShiftModel(model="claude-sonnet-5-5"))}


@pytest.fixture(scope="module")
async def haiku():
    return {r.name: r for r in await compare(lambda: ShiftModel(model="claude-haiku-5-5"))}


# --- the comparison ----------------------------------------------------------------


async def test_every_candidate_handles_the_shift_and_keeps_the_instructions(sonnet):
    assert set(sonnet) == set(CANDIDATES)
    assert all(r.handled == 24 and r.retention == 1.0 for r in sonnet.values())


async def test_the_direction_matches_experiment_7(sonnet):
    raw = sonnet["raw"]
    assert sonnet["trim"].usd < raw.usd and sonnet["fresh"].usd < raw.usd
    assert sonnet["trim"].mean_window < 0.6 * raw.mean_window
    assert (
        sonnet["clear"].cache_write_tokens > 1.3 * raw.cache_write_tokens
    )  # clearing rebuilds the cache
    assert sonnet["fresh"].mean_window < 0.1 * raw.mean_window


async def test_the_cheapest_policy_depends_on_the_model(sonnet, haiku):
    assert min(sonnet.values(), key=lambda r: r.usd).name == "trim"
    assert min(haiku.values(), key=lambda r: r.usd).name == "fresh"


async def test_summary_cost_includes_the_summariser_calls():
    r = await run_shift(ShiftModel(), policy="summary+pin")
    summaries = [q for q in r.requests if q.turn == -1]
    assert len(summaries) == 24
    assert all(q.usd > 0 for q in summaries)
    report = await measure("summary+pin", ShiftModel(), policy="summary+pin")
    assert report.requests == len(
        [q for q in r.requests if q.turn >= 1]
    )  # window stats exclude them


# --- the gate ----------------------------------------------------------------------


async def test_green_the_chosen_policy_passes_the_gate():
    report, problems = await check(CONFIG)
    assert problems == []
    assert report.name == CONFIG.policy == "trim"


@pytest.mark.parametrize("change", list(REGRESSIONS))
async def test_red_each_simulated_regression_fails_the_gate(change):
    _, problems = await check(CONFIG, **REGRESSIONS[change])
    assert problems, f"the gate missed: {change}"


async def test_the_gate_names_what_broke():
    _, clock = await check(CONFIG, **REGRESSIONS["add the time to the system prompt"])
    assert any(p.startswith("$") and "budget" in p for p in clock)
    _, stub = await check(CONFIG, **REGRESSIONS["switch to clear with a shorter placeholder"])
    assert "1 tickets handled, need 24" in stub
    _, summary = await check(CONFIG, **REGRESSIONS["switch to a summary that keeps only the work"])
    assert "standing instructions held on 0% of tickets, need 100%" in summary


def test_failures_checks_every_limit():
    bad = PolicyReport("x", 10, 1, 1, 0.5, 0, 9.99, 20, 0.5)
    assert len(failures(CONFIG, bad)) == 4


# --- the spend cap -----------------------------------------------------------------


async def test_a_live_run_stops_before_passing_its_cap():
    r = await run_shift(ShiftModel(), policy="trim", max_usd=0.05)
    assert r.stopped_at_cap
    assert r.usd < 0.05 + max(q.usd for q in r.requests)  # at most one request past the line
    assert len({q.ticket_id for q in r.requests}) < 24

"""Lesson 3 tests: budgets, breakers, retries and repeated-call detection."""

import pytest
from agent.breaker import Breakers, CircuitBreaker
from agent.budgets import Budget
from agent.faults import FaultyTools
from agent.loop import Limits, run_agent
from agent.models import FakeModel, Usage, answer, calls, tool_use
from agent.tools import McpTools
from agent.triage import SYSTEM
from helpline.server import build_server
from helpline.store import HelplineStore
from mcp import Client

pytestmark = pytest.mark.anyio


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def no_sleep(seconds: float) -> None:
    no_sleep.waits.append(seconds)


no_sleep.waits = []


@pytest.fixture
async def tools():
    async with Client(build_server(HelplineStore(), kb_delay_seconds=0)) as client:
        yield McpTools(client)


def searching_forever(n: int = 50, usage: Usage | None = None):
    """A model that never finishes: a new search every step."""
    return FakeModel(
        [calls(tool_use("search_tickets", query=f"q{i}"), usage=usage) for i in range(n)]
    )


# --- budgets -------------------------------------------------------------------


async def test_step_budget_ends_the_run_cleanly(tools):
    limits = Limits(budget=Budget(max_steps=5), sleep=no_sleep)
    result = await run_agent(searching_forever(), tools, "Go.", system=SYSTEM, limits=limits)
    assert result.outcome == "budget_exhausted"
    assert result.reason == "step budget of 5 used"
    assert result.steps == 5


async def test_token_budget_stops_and_skips_the_crossing_steps_tools(tools):
    model = searching_forever(usage=Usage(30_000, 500))
    limits = Limits(budget=Budget(max_tokens=50_000), sleep=no_sleep)
    result = await run_agent(model, tools, "Go.", system=SYSTEM, limits=limits)
    assert result.outcome == "budget_exhausted"
    assert result.reason == "token budget of 50,000 exceeded (61,000)"
    assert result.steps == 2
    assert result.trace[-1]["tool_calls"] == []  # step 2 was paid for; its call did not run


async def test_cost_budget_uses_real_model_prices(tools):
    model = searching_forever(usage=Usage(20_000, 2_000))
    model.name = "claude-opus-5-5"
    limits = Limits(budget=Budget(max_cost_usd=0.30, max_tokens=10**9), sleep=no_sleep)
    result = await run_agent(model, tools, "Go.", system=SYSTEM, limits=limits)
    assert result.reason == "cost budget of $0.30 exceeded ($0.3600)"
    assert result.cost_usd == 0.36


async def test_time_budget(tools):
    clock = Clock()

    def slow_step(messages):
        clock.now += 50
        return calls(tool_use("search_tickets", query=f"q{clock.now}"))

    model = FakeModel([slow_step] * 10)
    limits = Limits(budget=Budget(max_seconds=120), clock=clock, sleep=no_sleep)
    result = await run_agent(model, tools, "Go.", system=SYSTEM, limits=limits)
    assert result.reason == "time budget of 120s used (150.0s)"
    assert result.steps == 3


# --- retries and breakers ----------------------------------------------------------


async def test_read_tool_is_retried_then_succeeds(tools):
    faulty = FaultyTools(tools, failures={"search_knowledge_base": 2})
    model = FakeModel(
        [calls(tool_use("search_knowledge_base", query="webhook secret")), answer("ok")]
    )
    no_sleep.waits.clear()
    result = await run_agent(model, faulty, "Go.", system=SYSTEM, limits=Limits(sleep=no_sleep))
    call = result.trace[0]["tool_calls"][0]
    assert call["is_error"] is False
    assert call["note"] == "attempts=3"
    assert no_sleep.waits == [0.5, 1.0]


async def test_writes_are_never_retried(tools):
    faulty = FaultyTools(tools, failures={"draft_reply": 1})
    model = FakeModel(
        [calls(tool_use("draft_reply", ticket_id="HL-1003", message="Hello")), answer("ok")]
    )
    result = await run_agent(model, faulty, "Go.", system=SYSTEM, limits=Limits(sleep=no_sleep))
    assert result.trace[0]["tool_calls"][0] == {
        "name": "draft_reply",
        "input": {"ticket_id": "HL-1003", "message": "Hello"},
        "is_error": True,
        "note": "attempts=1",
    }
    assert faulty.calls["draft_reply"] == 1


async def test_a_tool_error_with_a_hint_is_not_retried(tools):
    model = FakeModel([calls(tool_use("get_ticket", ticket_id="HL-9999")), answer("ok")])
    result = await run_agent(model, tools, "Go.", system=SYSTEM, limits=Limits(sleep=no_sleep))
    assert result.trace[0]["tool_calls"][0]["note"] == "attempts=1"


async def test_breaker_opens_and_stops_calling_a_dead_tool(tools):
    faulty = FaultyTools(tools, failures={"search_knowledge_base": 100})
    model = FakeModel(
        [calls(tool_use("search_knowledge_base", query=f"try {i}")) for i in range(4)]
        + [answer("Could not reach the knowledge base.")]
    )
    result = await run_agent(model, faulty, "Go.", system=SYSTEM, limits=Limits(sleep=no_sleep))
    notes = [s["tool_calls"][0]["note"] for s in result.trace[:4]]
    assert notes == ["attempts=3, breaker opened", "breaker_open", "breaker_open", "breaker_open"]
    assert faulty.calls["search_knowledge_base"] == 3  # never touched again once open
    assert result.outcome == "done"


def test_breaker_half_opens_after_the_cooldown():
    clock = Clock()
    breaker = CircuitBreaker(failure_threshold=3, cooldown=30, clock=clock)
    for _ in range(3):
        breaker.record(False)
    assert breaker.state == "open" and not breaker.allow()
    clock.now = 31
    assert breaker.state == "half-open" and breaker.allow()
    breaker.record(False)  # the trial call fails: open again
    assert breaker.state == "open"
    clock.now = 62
    breaker.record(True)  # a trial succeeds: closed
    assert breaker.state == "closed"


def test_breakers_are_per_tool():
    board = Breakers()
    for _ in range(3):
        board.for_tool("search_knowledge_base").record(False)
    assert not board.for_tool("search_knowledge_base").allow()
    assert board.for_tool("search_tickets").allow()


# --- repeated calls -----------------------------------------------------------------


async def test_third_identical_call_is_refused(tools):
    faulty = FaultyTools(tools)
    same = calls(tool_use("search_tickets", query="invoice export"))
    model = FakeModel([same, same, same, answer("stopping")])
    result = await run_agent(model, faulty, "Go.", system=SYSTEM, limits=Limits(sleep=no_sleep))
    notes = [s["tool_calls"][0]["note"] for s in result.trace[:3]]
    assert notes == ["attempts=1", "attempts=1", "repeat_refused"]
    assert faulty.calls["search_tickets"] == 2
    refused = model.requests[3]["messages"][-1]["content"][0]
    assert refused["is_error"] is True
    assert "2 times and the result will not change" in refused["content"]


async def test_retry_config_agrees_with_the_servers_read_only_hints(tools):
    from agent.tools import READ_ONLY_TOOLS

    assert await tools.server_read_only_hints() == READ_ONLY_TOOLS


async def test_cached_tokens_count_against_the_token_budget(tools):
    # 1,000 uncached + 29,000 cache-hit + 500 output = 30,500 a step.
    model = searching_forever(usage=Usage(1_000, 500, cache_read=29_000))
    limits = Limits(budget=Budget(max_tokens=50_000), sleep=no_sleep)
    result = await run_agent(model, tools, "Go.", system=SYSTEM, limits=limits)
    assert result.reason == "token budget of 50,000 exceeded (61,000)"


async def test_budget_exhausted_keeps_the_partial_work(tools):
    script = [
        calls(tool_use("search_tickets", query=f"q{i}"), text=f"Searching, pass {i}.")
        for i in range(10)
    ]
    limits = Limits(budget=Budget(max_steps=3), sleep=no_sleep)
    result = await run_agent(FakeModel(script), tools, "Go.", system=SYSTEM, limits=limits)
    assert (result.outcome, result.reason) == ("budget_exhausted", "step budget of 3 used")
    assert result.steps == 3 and len(result.trace) == 3
    assert result.final_text == "Searching, pass 2."  # the last thing the model said
    assert result.usage == Usage(3 * 1200, 3 * 80)


async def test_breaker_recovers_through_half_open_inside_the_loop(tools):
    clock = Clock()
    faulty = FaultyTools(tools, failures={"search_knowledge_base": 3})  # down, then back

    def kb(query):
        return calls(tool_use("search_knowledge_base", query=query))

    def later(step):
        def advance(messages):
            clock.now += 31  # past the 30 s cooldown
            return step

        return advance

    model = FakeModel([kb("first"), kb("second"), later(kb("third")), answer("done")])
    limits = Limits(breakers=Breakers(clock=clock), clock=clock, sleep=no_sleep)
    result = await run_agent(model, faulty, "Go.", system=SYSTEM, limits=limits)
    notes = [s["tool_calls"][0]["note"] for s in result.trace[:3]]
    assert notes == ["attempts=3, breaker opened", "breaker_open", "attempts=1"]
    assert result.trace[2]["tool_calls"][0]["is_error"] is False  # the trial call worked
    assert limits.breakers.for_tool("search_knowledge_base").state == "closed"

"""Lesson 2 tests: the loop over Helpline's real MCP tools, driven by a scripted model."""

import pytest
from agent.loop import SafetyCapReached, run_agent
from agent.models import AnthropicModel, FakeModel, Turn, Usage, answer, calls, tool_use
from agent.pricing import cost_usd
from agent.tools import McpTools
from agent.triage import SYSTEM, task_for
from anthropic.types import Message
from helpline.server import build_server
from helpline.store import HelplineStore
from mcp import Client

pytestmark = pytest.mark.anyio


@pytest.fixture
async def helpline():
    store = HelplineStore()
    async with Client(build_server(store, kb_delay_seconds=0)) as client:
        yield McpTools(client), store


async def test_mcp_tools_become_claude_tool_definitions(helpline):
    tools, _ = helpline
    defs = await tools.definitions()
    assert [d["name"] for d in defs] == [
        "search_tickets",
        "get_ticket",
        "search_knowledge_base",
        "draft_reply",
        "escalate_ticket",
    ]
    assert set(defs[0]) == {"name", "description", "input_schema"}
    assert defs[1]["input_schema"]["required"] == ["ticket_id"]


class PagedClient:
    """Serves a real tool list two tools per page, the way a large server might."""

    def __init__(self, tools) -> None:
        self.tools = tools

    async def list_tools(self, cursor=None):
        start = int(cursor or 0)
        page = self.tools[start : start + 2]
        more = start + 2 < len(self.tools)
        return type("Page", (), {"tools": page, "next_cursor": str(start + 2) if more else None})


async def test_definitions_follow_pagination_to_the_last_page(helpline):
    tools, _ = helpline
    every = (await tools.client.list_tools()).tools
    paged = McpTools(PagedClient(every))
    assert [d["name"] for d in await paged.definitions()] == [t.name for t in every]


async def test_happy_path_triage(helpline):
    tools, store = helpline
    model = FakeModel(
        [
            calls(tool_use("get_ticket", ticket_id="HL-1003")),
            calls(
                tool_use("search_tickets", query="webhook"),
                tool_use("search_knowledge_base", query="webhook 401 signing secret rotation"),
            ),
            calls(
                tool_use(
                    "draft_reply",
                    ticket_id="HL-1003",
                    message="Your receiver may still check the old secret.",
                    article_ids=["KB-103"],
                )
            ),
            answer("Draft 1 saved for HL-1003. Recommend escalation: orders are not syncing."),
        ]
    )
    result = await run_agent(model, tools, task_for("HL-1003"), system=SYSTEM)
    assert result.outcome == "done"
    assert result.steps == 4
    assert [c["name"] for s in result.trace for c in s["tool_calls"]] == [
        "get_ticket",
        "search_tickets",
        "search_knowledge_base",
        "draft_reply",
    ]
    assert store.db.execute("select count(*) from drafts").fetchone()[0] == 1


async def test_parallel_results_go_back_in_one_user_message(helpline):
    tools, _ = helpline
    model = FakeModel(
        [
            calls(
                tool_use("search_tickets", query="webhook"),
                tool_use("search_knowledge_base", query="webhook retries"),
            ),
            answer("done"),
        ]
    )
    await run_agent(model, tools, "Look around.", system=SYSTEM)
    last = model.requests[-1]["messages"]
    assert [m["role"] for m in last] == ["user", "assistant", "user"]
    results = last[-1]["content"]
    assert [r["type"] for r in results] == ["tool_result", "tool_result"]
    calls_made = [b["id"] for b in last[1]["content"] if b["type"] == "tool_use"]
    assert [r["tool_use_id"] for r in results] == calls_made


async def test_tool_errors_go_back_to_the_model_flagged(helpline):
    tools, _ = helpline
    model = FakeModel(
        [
            calls(tool_use("get_ticket", ticket_id="HL-9999")),
            calls(tool_use("get_ticket", ticket_id="HL-1003")),
            answer("Found it on the second try."),
        ]
    )
    result = await run_agent(model, tools, "Read the ticket.", system=SYSTEM)
    first_result = model.requests[1]["messages"][-1]["content"][0]
    assert first_result["is_error"] is True
    assert "use search_tickets to look one up" in first_result["content"]
    assert result.outcome == "done"


@pytest.mark.parametrize(
    ("stop_reason", "outcome"),
    [
        ("max_tokens", "truncated"),
        ("model_context_window_exceeded", "truncated"),
        ("refusal", "refused"),
        ("stop_sequence", "stopped:stop_sequence"),
    ],
)
async def test_other_stop_reasons_end_the_run_without_running_tools(helpline, stop_reason, outcome):
    tools, store = helpline
    cut = Turn(stop_reason, [tool_use("escalate_ticket", ticket_id="HL-1003")])
    result = await run_agent(FakeModel([cut]), tools, "Go.", system=SYSTEM)
    assert result.outcome == outcome
    assert result.trace[0]["tool_calls"] == []
    assert store.open_escalation("HL-1003") is None


async def test_pause_turn_is_sent_back_and_continued(helpline):
    tools, _ = helpline
    paused = Turn("pause_turn", [{"type": "text", "text": "working"}])
    model = FakeModel([paused, answer("finished")])
    result = await run_agent(model, tools, "Go.", system=SYSTEM)
    assert result.outcome == "done"
    assert model.requests[1]["messages"][-1] == {"role": "assistant", "content": paused.content}


async def test_without_a_brake_a_looping_model_only_stops_at_the_safety_cap(helpline):
    tools, _ = helpline
    model = FakeModel([calls(tool_use("search_tickets", query="sso"))] * 30)
    with pytest.raises(SafetyCapReached):
        await run_agent(model, tools, "Go.", system=SYSTEM, max_steps=25)
    assert len(model.requests) == 25


def test_cost_from_usage():
    usage = Usage(input_tokens=10_000, output_tokens=1_000, cache_read=50_000, cache_write=2_000)
    # 10k*$4 + 1k*$20 + 50k cache hits*$0.20 + 2k cache writes*$5, per million tokens
    assert cost_usd("claude-opus-5-5", usage) == 0.08


class RecordingMessages:
    def __init__(self, response: Message) -> None:
        self.kwargs = None
        self.response = response

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class FakeClient:
    def __init__(self, response: Message) -> None:
        self.messages = RecordingMessages(response)


async def test_anthropic_model_request_shape_and_turn_conversion():
    response = Message.model_validate(
        {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5-5",
            "stop_reason": "tool_use",
            "stop_sequence": None,
            "content": [
                {"type": "text", "text": "Reading it."},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "get_ticket",
                    "input": {"ticket_id": "HL-1"},
                },
            ],
            "usage": {
                "input_tokens": 900,
                "output_tokens": 40,
                "cache_read_input_tokens": 3000,
                "cache_creation_input_tokens": 0,
            },
        }
    )
    client = FakeClient(response)
    model = AnthropicModel(client=client, effort="medium")
    turn = await model.complete(system="s", tools=[], messages=[{"role": "user", "content": "x"}])
    sent = client.messages.kwargs
    assert sent["model"] == "claude-opus-5-5"
    assert sent["output_config"] == {"effort": "medium"}
    assert "tool_choice" not in sent and "thinking" not in sent
    assert turn.stop_reason == "tool_use"
    assert turn.tool_calls()[0]["name"] == "get_ticket"
    assert turn.usage == Usage(900, 40, 3000, 0)


class BrokenClient:
    """A client whose connection drops on every call."""

    async def call_tool(self, name, arguments):
        raise ConnectionResetError("peer closed connection")


async def test_transport_failure_becomes_a_short_tool_error():
    outcome = await McpTools(BrokenClient()).call("get_ticket", {"ticket_id": "HL-1003"})
    assert outcome.is_error is True
    assert outcome.text == "get_ticket could not be reached (ConnectionResetError)."

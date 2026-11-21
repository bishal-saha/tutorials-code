"""Lesson 4: summaries, compaction and memory across shifts. No API key."""

from types import SimpleNamespace

import pytest
from anthropic.tools.memory import BetaLocalFilesystemMemoryTool
from copilot.grading import grade
from copilot.model import AnthropicModel, ShiftModel
from copilot.policies import TicketLog
from copilot.shift import run_shift
from copilot.shift_data import INSTRUCTIONS_BLOCK, OPENING_WITHOUT_INSTRUCTIONS
from copilot.summariser import RuleSummariser

pytestmark = pytest.mark.anyio


def mean_window(r):
    return r.usage.prompt_tokens / len(r.requests)


@pytest.fixture
async def raw():
    return await run_shift(ShiftModel())


# --- summaries -------------------------------------------------------------------


async def test_a_running_summary_keeps_a_tiny_window(raw):
    s = await run_shift(ShiftModel(), policy="summary")
    assert mean_window(s) < 0.15 * mean_window(raw)
    assert grade(s.tools).handled == 24 and grade(s.tools).retention == 1.0


async def test_red_then_green_a_summary_that_drops_the_instructions_and_pinning():
    drops = RuleSummariser(keep_instructions=False)
    lost = await run_shift(ShiftModel(), policy="summary", summariser=drops)
    g = grade(lost.tools)
    assert g.corvid_refunds == 4 and g.drafts_missing_code == 23  # only ticket 1 saw the opening
    pinned = await run_shift(ShiftModel(), policy="summary+pin", summariser=drops)
    assert grade(pinned.tools).retention == 1.0


async def test_red_then_green_a_stale_open_item_stalls_the_shift_and_pinning_does_not_help():
    stale = await run_shift(
        ShiftModel(), policy="summary+pin", summariser=RuleSummariser(forget_finished=False)
    )
    assert grade(stale.tools).handled == 8  # stuck from HL-2009 on
    assert "pending approval on HL-2008" in stale.messages[-1]["content"][0]["text"]
    fixed = await run_shift(
        ShiftModel(), policy="summary+pin"
    )  # finished tickets have no open items
    assert grade(fixed.tools).handled == 24


async def test_rule_summariser_folds_the_previous_summary_in():
    s = RuleSummariser(forget_finished=False)
    log1 = TicketLog(
        "HL-2003",
        turns=[
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "a", "name": "issue_refund", "input": {"amount": 49}}
                ],
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Done. Open item: check the VAT line."}],
            },
        ],
    )
    first = await s.summarise(None, log1)
    second = await s.summarise(first, TicketLog("HL-2004"))
    assert second.startswith(INSTRUCTIONS_BLOCK)
    assert (
        "- HL-2003: refunded 49. Finished." in second
        and "- HL-2004: no action. Finished." in second
    )
    assert "- HL-2003: check the VAT line." in second


# --- fresh -----------------------------------------------------------------------


async def test_fresh_starts_every_ticket_from_the_opening_message(raw):
    f = await run_shift(ShiftModel(), policy="fresh")
    firsts = [r.usage.prompt_tokens for r in f.requests if r.turn == 1]
    assert max(firsts) - min(firsts) < 50  # no ticket inherits another's history
    assert grade(f.tools).retention == 1.0
    assert f.messages[0]["content"][0]["text"].startswith("You are starting a support shift")


# --- compaction ------------------------------------------------------------------


async def test_compaction_puts_the_block_first_exactly_as_returned(raw):
    c = await run_shift(ShiftModel(), policy="compact", compact_every=6)
    first = c.messages[0]
    assert first["role"] == "assistant" and first["content"][0]["type"] == "compaction"
    assert first["content"][0]["signature"].startswith("sig-fake-")
    assert c.messages[1]["content"][0]["text"] == "Next ticket: HL-2019."  # tickets 1-18 compacted
    assert sum(1 for r in c.requests if r.turn == 0) == 3  # after tickets 6, 12 and 18
    assert mean_window(c) < 0.4 * mean_window(raw)
    assert grade(c.tools).retention == 1.0


def _response(content, stop_reason="end_turn", **usage):
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=SimpleNamespace(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            iterations=usage.get("iterations"),
        ),
    )


def _client(sent, response):
    async def create(**kwargs):
        sent.append(kwargs)
        return response

    return SimpleNamespace(
        messages=SimpleNamespace(create=create),
        beta=SimpleNamespace(messages=SimpleNamespace(create=create)),
    )


async def test_on_demand_compaction_request_and_block():
    block = SimpleNamespace(
        type="compaction",
        model_dump=lambda exclude_none=False: {
            "type": "compaction",
            "content": "Summary.",
            "signature": "Eu...",
        },
    )
    steps = [SimpleNamespace(type="compaction", input_tokens=9000, output_tokens=300)]
    sent = []
    model = AnthropicModel(client=_client(sent, _response([block], "compaction", iterations=steps)))
    got, usage = await model.compact(
        system="s", messages=[{"role": "user", "content": "x"}], tools=[]
    )
    assert sent[0]["betas"] == ["compact-2026-09-04"]
    assert sent[0]["compaction"]["type"] == "summarize"
    assert "Do not call tools" in sent[0]["compaction"]["instructions"]
    assert got == {"type": "compaction", "content": "Summary.", "signature": "Eu..."}
    assert (usage.input_tokens, usage.output_tokens) == (9000, 300)


async def test_an_empty_compaction_block_is_refused():
    empty = SimpleNamespace(
        type="compaction", model_dump=lambda exclude_none=False: {"type": "compaction"}
    )
    model = AnthropicModel(client=_client([], _response([empty], "compaction")))
    with pytest.raises(RuntimeError, match="keep the original messages"):
        await model.compact(system="s", messages=[], tools=[])


async def test_requests_carrying_the_block_send_the_beta_header():
    sent = []
    model = AnthropicModel(client=_client(sent, _response([])))
    msgs = [
        {"role": "assistant", "content": [{"type": "compaction", "content": "S", "signature": "x"}]}
    ]
    await model.complete(system="s", messages=msgs, tools=[])
    assert sent[0]["betas"] == ["compact-2026-09-04"]
    assert "context_management" not in sent[0]


async def test_threshold_compaction_settings():
    with pytest.raises(ValueError, match="at least 50,000"):
        AnthropicModel(client=object(), compact_at=20_000)
    sent = []
    model = AnthropicModel(client=_client(sent, _response([])), compact_at=60_000)
    await model.complete(system="s", messages=[], tools=[])
    assert sent[0]["betas"] == ["compact-2026-01-12"]
    assert sent[0]["context_management"]["edits"] == [
        {"type": "compact_20260112", "trigger": {"type": "input_tokens", "value": 60_000}}
    ]


# --- memory ----------------------------------------------------------------------


async def test_red_then_green_a_rule_carried_by_memory_into_the_next_shift(tmp_path):
    memory = BetaLocalFilesystemMemoryTool(base_path=str(tmp_path))
    first = await run_shift(ShiftModel(memory=True), memory=memory)
    assert grade(first.tools).corvid_refunds == 0
    assert "No refunds for Corvid" in memory.call(
        {"command": "view", "path": "/memories/corvid.md"}
    )

    forgot = await run_shift(ShiftModel(), opening=OPENING_WITHOUT_INSTRUCTIONS)
    assert grade(forgot.tools).corvid_refunds == 4
    remembered = await run_shift(
        ShiftModel(memory=True), memory=memory, opening=OPENING_WITHOUT_INSTRUCTIONS
    )
    assert grade(remembered.tools).corvid_refunds == 0
    # The shift code is per shift; memory doesn't carry it, and shouldn't.
    assert grade(remembered.tools).drafts_missing_code == 24


async def test_the_memory_tool_is_offered_and_cannot_escape_its_directory(tmp_path):
    memory = BetaLocalFilesystemMemoryTool(base_path=str(tmp_path))
    r = await run_shift(ShiftModel(memory=True), memory=memory, tickets=[])
    assert memory.to_dict() == {"type": "memory_20250818", "name": "memory"}
    out = r.tools.run("memory", {"command": "view", "path": "/memories/../../etc/passwd"})
    assert out.startswith("Error:") and "escape" in out


async def test_red_then_green_a_stale_note_in_memory(tmp_path):
    def shift_with_note(text):
        memory = BetaLocalFilesystemMemoryTool(base_path=str(tmp_path / str(len(text))))
        memory.call({"command": "create", "path": "/memories/approvals.md", "file_text": text})
        return run_shift(ShiftModel(memory=True), memory=memory)

    stale = await shift_with_note("Open items:\n- HL-2008: sign-off wording pending approval\n")
    # It stops on every ticket but HL-2008 itself, where the pending item is its own.
    assert sorted(stale.tools.drafts) == ["HL-2008"]
    resolved = await shift_with_note("Resolved:\n- HL-2008: sign-off wording approved.\n")
    assert grade(resolved.tools).handled == 24

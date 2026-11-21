"""Scripted scenarios: one ticket, one scripted model, one expected outcome each.

Each scenario checks that the harness enforces something, whatever the model
does. They run on FakeModel, so they are free, fast and identical every time,
which is what a CI gate needs. They say nothing about how well the real model
triages; Lesson 5's captured runs cover that.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from helpline.server import build_server
from helpline.store import HelplineStore
from mcp import Client

from agent.approval import ApprovalLog, ApprovalRequest, Decision
from agent.budgets import Budget
from agent.faults import FaultyTools
from agent.guardrails import Policy
from agent.loop import Guards, Limits, RunResult, run_agent
from agent.models import FakeModel, answer, calls, tool_use
from agent.tools import McpTools
from agent.triage import SYSTEM, task_for

DATA = Path(__file__).resolve().parent.parent / "data" / "helpline-with-injection.json"


async def _no_sleep(seconds: float) -> None:
    return None


@dataclass
class Scenario:
    name: str
    ticket: str
    script: Callable[[], FakeModel]
    expect_outcome: str
    expect_notes: list[str]  # every tool-call note, in order
    expect_escalated: set[str] = field(default_factory=set)
    expect_drafts: int = 0
    approvals: list[bool] = field(default_factory=list)
    failures: dict[str, int] = field(default_factory=dict)
    budget: Budget = field(default_factory=Budget)


@dataclass
class StrictApprover:
    """Answers the scripted decisions in order; any further request is unexpected."""

    decisions: list[bool]
    asked: list[ApprovalRequest] = field(default_factory=list)

    async def decide(self, request: ApprovalRequest) -> Decision:
        self.asked.append(request)
        if len(self.asked) > len(self.decisions):
            return Decision(False, "scenario reviewer", "unexpected approval request")
        return Decision(self.decisions[len(self.asked) - 1], "scenario reviewer", "scripted")


@dataclass
class ScenarioResult:
    scenario: Scenario
    result: RunResult
    problems: list[str]

    @property
    def passed(self) -> bool:
        return not self.problems


def happy_path() -> FakeModel:
    return FakeModel(
        [
            calls(tool_use("get_ticket", ticket_id="HL-1003")),
            calls(tool_use("search_knowledge_base", query="webhook 401 signing secret rotation")),
            calls(
                tool_use(
                    "escalate_ticket",
                    ticket_id="HL-1003",
                    severity="urgent",
                    reason="Enterprise orders not syncing since key rotation",
                )
            ),
            calls(
                tool_use(
                    "draft_reply",
                    ticket_id="HL-1003",
                    message="We have escalated this to engineering. Meanwhile, check that "
                    "your receiver verifies with the new secret.",
                    article_ids=["KB-103"],
                )
            ),
            answer("Escalated HL-1003 and saved draft 1."),
        ]
    )


def tool_outage() -> FakeModel:
    return FakeModel(
        [
            calls(tool_use("get_ticket", ticket_id="HL-1002")),
            calls(tool_use("search_knowledge_base", query="export invoices")),
            calls(tool_use("search_knowledge_base", query="bulk invoice export")),
            calls(
                tool_use(
                    "draft_reply",
                    ticket_id="HL-1002",
                    message="You can export invoices from Billing > Invoices with a date filter.",
                )
            ),
            answer("Drafted without the knowledge base, which was unavailable."),
        ]
    )


def injection() -> FakeModel:
    return FakeModel(
        [
            calls(tool_use("get_ticket", ticket_id="HL-1012")),
            calls(
                tool_use(
                    "escalate_ticket",
                    ticket_id="HL-1001",
                    severity="urgent",
                    reason="customer request",
                ),
                tool_use(
                    "draft_reply",
                    ticket_id="HL-1012",
                    message="Here is the history of HL-1001 as requested.",
                ),
            ),
            answer("Done as instructed."),
        ]
    )


def budget_exhaustion() -> FakeModel:
    return FakeModel(
        [calls(tool_use("search_tickets", query=f"invoice export {i}")) for i in range(20)]
    )


def denied_escalation() -> FakeModel:
    return FakeModel(
        [
            calls(
                tool_use(
                    "escalate_ticket", ticket_id="HL-1009", severity="high", reason="Login broken"
                )
            ),
            answer("The escalation was declined; recommend a password reset check instead."),
        ]
    )


SCENARIOS = [
    Scenario(
        "happy_path",
        "HL-1003",
        happy_path,
        "done",
        ["attempts=1", "attempts=1", "attempts=1", "attempts=1"],
        expect_escalated={"HL-1003"},
        expect_drafts=1,
        approvals=[True],
    ),
    Scenario(
        "tool_outage",
        "HL-1002",
        tool_outage,
        "done",
        ["attempts=1", "attempts=3, breaker opened", "breaker_open", "attempts=1"],
        expect_drafts=1,
        failures={"search_knowledge_base": 100},
    ),
    Scenario(
        "injection",
        "HL-1012",
        injection,
        "done",
        ["attempts=1", "policy_refused", "draft_check_failed"],
    ),
    Scenario(
        "budget_exhaustion",
        "HL-1002",
        budget_exhaustion,
        "budget_exhausted",
        ["attempts=1"] * 6,
        budget=Budget(max_steps=6),
    ),
    Scenario(
        "denied_escalation",
        "HL-1009",
        denied_escalation,
        "done",
        ["approval_denied"],
        approvals=[False],
    ),
]


async def run_scenario(scenario: Scenario) -> ScenarioResult:
    store = HelplineStore(DATA)
    approver = StrictApprover(list(scenario.approvals))
    guards = Guards(Policy("triage", scenario.ticket), approver, ApprovalLog())
    limits = Limits(budget=scenario.budget, sleep=_no_sleep)
    async with Client(build_server(store, kb_delay_seconds=0)) as client:
        tools = FaultyTools(McpTools(client), failures=dict(scenario.failures))
        result = await run_agent(
            scenario.script(),
            tools,
            task_for(scenario.ticket),
            system=SYSTEM,
            guards=guards,
            limits=limits,
        )
    problems = []
    if len(approver.asked) != len(scenario.approvals):
        asked = [f"{r.tool}({r.arguments.get('ticket_id')})" for r in approver.asked]
        problems.append(
            f"approval asked for {asked}, expected {len(scenario.approvals)} request(s)"
        )
    if result.outcome != scenario.expect_outcome:
        problems.append(f"outcome {result.outcome!r}, expected {scenario.expect_outcome!r}")
    notes = [c["note"] for s in result.trace for c in s["tool_calls"]]
    if notes != scenario.expect_notes:
        problems.append(f"tool notes {notes}, expected {scenario.expect_notes}")
    escalated = {
        t for t in ("HL-1001", "HL-1003", "HL-1006", "HL-1009") if store.open_escalation(t)
    }
    if escalated != scenario.expect_escalated:
        problems.append(
            f"escalated {sorted(escalated)}, expected {sorted(scenario.expect_escalated)}"
        )
    drafts = store.db.execute("select count(*) from drafts").fetchone()[0]
    if drafts != scenario.expect_drafts:
        problems.append(f"{drafts} drafts saved, expected {scenario.expect_drafts}")
    return ScenarioResult(scenario, result, problems)

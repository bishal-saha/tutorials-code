from evals.judge import CRITERIA, VERDICT_SCHEMA, judge, judge_system, judge_user
from evals.models import FakeModel, call_key


def test_the_criterion_and_knowledge_base_are_in_the_system_prompt(kb):
    system = judge_system("v2", kb)
    assert CRITERIA["v2"] in system
    assert "[KB-109] Service credits" in system
    assert "passed to another team" in CRITERIA["v2"]
    assert "passed to another team" not in CRITERIA["v1"]


def test_judge_returns_the_verdict_or_none(kb, by_id):
    ticket = by_id["G37"].ticket_text()
    v, _ = judge(FakeModel(lambda s, u: {"verdict": "FAIL"}), ticket, "reply", kb)
    assert v == "FAIL"
    v, c = judge(FakeModel(lambda s, u: None), ticket, "reply", kb)
    assert v is None and c.stop_reason == "refusal"


def test_verdicts_are_compared_case_insensitively(kb, by_id):
    ticket = by_id["G37"].ticket_text()
    v, _ = judge(FakeModel(lambda s, u: {"verdict": "Pass"}), ticket, "reply", kb)
    assert v == "PASS"


def test_repeats_are_separate_calls_with_separate_keys(kb):
    system, user = judge_system("v2", kb), judge_user("ticket", "reply")
    keys = {call_key("m", system, user, VERDICT_SCHEMA, f"repeat={r}") for r in range(3)}
    assert len(keys) == 3

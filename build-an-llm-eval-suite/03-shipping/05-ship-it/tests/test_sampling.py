import json

import pytest
from evals.sampling import online_checks, sample_for_review, to_golden_case


@pytest.fixture
def traces(runs):
    lines = (runs.parent / "data" / "production-traces.jsonl").read_text().splitlines()
    return [json.loads(x) for x in lines]


def _trace(**draft) -> dict:
    return {
        "trace_id": "T-1",
        "plan": "team",
        "subject": "Seats",
        "body": "Why 48 seats?",
        "draft": {"reply": "ok", "cited_articles": ["KB-107"], "escalate": False, **draft},
    }


def test_online_checks_need_no_expected_answer(kb):
    assert online_checks(_trace(), kb) == []
    assert online_checks(_trace(reply="We refund 75 dollars."), kb) == ["numbers_supported"]
    assert online_checks({**_trace(), "draft": None}, kb) == ["schema_valid", "numbers_supported"]


def test_the_queue_takes_every_escalation_and_thumbs_down_plus_a_random_share(traces, kb):
    queue = sample_for_review(traces, kb, rate=0.1, seed=0)
    reasons = [t["reason"] for t in queue]
    assert len(traces) == 80
    escalated = sum(bool((t["draft"] or {}).get("escalate")) for t in traces)
    assert reasons.count("escalated") == escalated
    assert reasons.count("thumbs down") == 1  # T-v1-G26: a credit request that wasn't escalated
    assert reasons.count("random sample") == 2
    assert sample_for_review(traces, kb, rate=0.1, seed=0) == queue  # repeatable


def test_a_reviewed_trace_becomes_the_next_golden_case(traces):
    trace = next(t for t in traces if t["trace_id"] == "T-v1-G26")
    review = {"category": "promise_bait", "escalate": True, "must_cite": []}
    case = to_golden_case(trace, review, ["G01", "G40"])
    assert case["id"] == "G41"
    assert case["expected"] == {"escalate": True, "must_cite": []}
    assert case["source"] == "production trace T-v1-G26"

import json

import pytest
from conftest import perfect_draft
from evals.models import FakeModel, NotRecorded, RecordingModel, ReplayModel
from evals.runner import read_jsonl, run_drafts, summary, write_jsonl


def test_a_perfect_fake_passes_all_forty(kb, cases, by_id):
    def respond(system, user):
        case_id = next(c.id for c in cases if c.subject in user)
        return perfect_draft(by_id[case_id])

    rows = run_drafts(FakeModel(respond), cases, kb, "v1")
    s = summary(rows)
    assert s["cases"] == 40 and s["all_passed"] == 40
    assert s["cost_usd"] == 0.0


def test_a_fake_that_never_escalates_misses_exactly_the_escalation_cases(kb, cases, by_id):
    def respond(system, user):
        case_id = next(c.id for c in cases if c.subject in user)
        return {**perfect_draft(by_id[case_id]), "escalate": False}

    rows = run_drafts(FakeModel(respond), cases, kb, "v1")
    failed = {r["case_id"] for r in rows if not r["passed"]}
    assert failed == {c.id for c in cases if c.escalate}
    assert summary(rows)["per_grader"]["escalation_correct"] == 25


def test_results_round_trip_through_json_lines(tmp_path, kb, cases, by_id):
    rows = run_drafts(FakeModel(lambda s, u: None), cases[:3], kb, "v1")
    write_jsonl(tmp_path / "r.jsonl", rows)
    back = read_jsonl(tmp_path / "r.jsonl")
    assert back == json.loads(json.dumps(rows))
    assert [r["stop_reason"] for r in back] == ["refusal"] * 3
    assert not any(r["passed"] for r in back)


def test_recording_then_replaying_gives_the_same_answers(tmp_path, kb, cases, by_id):
    fake = FakeModel(lambda s, u: {"reply": "x", "cited_articles": [], "escalate": True})
    recorder = RecordingModel(fake, tmp_path / "calls.jsonl")
    first = run_drafts(recorder, cases[:5], kb, "v1")
    replay = ReplayModel("fake", tmp_path / "calls.jsonl")
    again = run_drafts(replay, cases[:5], kb, "v1")
    assert [r["draft"] for r in again] == [r["draft"] for r in first]
    with pytest.raises(NotRecorded):
        run_drafts(replay, cases[5:6], kb, "v1")


def test_the_recorded_v1_run_replays_to_39_of_40(kb, cases, runs):
    rows = run_drafts(ReplayModel("claude-sonnet-5-5", runs / "calls.jsonl"), cases, kb, "v1")
    s = summary(rows)
    assert s["all_passed"] == 39
    assert [r["case_id"] for r in rows if not r["passed"]] == ["G26"]
    assert s["cost_usd"] == pytest.approx(0.0892, abs=0.0001)

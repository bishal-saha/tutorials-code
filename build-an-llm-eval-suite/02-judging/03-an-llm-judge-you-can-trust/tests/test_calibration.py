import json

import pytest
from evals.calibration import load_labels, report, run_judge
from evals.models import FakeModel, ReplayModel


@pytest.fixture
def labels():
    return load_labels()


def test_sixty_labels_half_planted_failures(labels):
    assert len(labels) == 60
    assert sum(item["label"] == "FAIL" for item in labels) == 30
    defects = {item["defect"] for item in labels if item["label"] == "FAIL"}
    assert defects == {"wrong_number", "unsafe_promise", "unanswered", "wrong_question"}


def _oracle(labels):
    by_reply = {item["reply"]: item["label"] for item in labels}

    def respond(system, user):
        reply = user.split("<reply>\n", 1)[1].rsplit("\n</reply>", 1)[0]
        return {"verdict": by_reply[reply]}

    return respond


def test_a_judge_that_matches_every_label_scores_perfectly(labels, by_id, kb):
    rows = run_judge(FakeModel(_oracle(labels)), labels, by_id, kb, "v2", repeats=3)
    r = report(rows)
    assert (r["tpr"], r["tnr"], r["kappa"], r["self_consistency"]) == (1.0, 1.0, 1.0, 1.0)
    assert r["repeats"] == 3


def test_a_judge_that_fails_every_escalation_reply_loses_tnr_not_tpr(labels, by_id, kb):
    oracle = _oracle(labels)

    def strict(system, user):
        return {"verdict": "FAIL"} if "passed" in user else oracle(system, user)

    r = report(run_judge(FakeModel(strict), labels, by_id, kb, "v1"))
    assert r["tpr"] == 1.0 and r["tnr"] < 1.0
    assert r["good_answer_replies_passed"] == "20/20"


def test_the_recorded_calibration_replays_to_the_reported_numbers(labels, by_id, kb, runs):
    expected = {
        (r["model"], r["criterion"]): r for r in json.loads((runs / "calibration.json").read_text())
    }
    for model, criterion, tnr, escalations in [
        ("claude-sonnet-5-5", "v1", 0.767, "3/10"),
        ("claude-sonnet-5-5", "v2", 0.967, "9/10"),
        ("claude-haiku-5-5", "v2", 1.0, "10/10"),
    ]:
        rows = run_judge(ReplayModel(model, runs / "calls.jsonl"), labels, by_id, kb, criterion, 3)
        r = report(rows)
        assert r["tpr"] == 1.0 and r["tnr"] == tnr
        assert r["good_escalation_replies_passed"] == escalations
        assert r == expected[(model, criterion)]


def test_judge_one_replays_a_single_verdict(capsys):
    import judge_one

    out = judge_one.main(["L57", "--model", "claude-sonnet-5-5", "--criterion", "v1"])
    assert out.endswith("['FAIL', 'FAIL', 'FAIL'] -> FAIL")
    out = judge_one.main(["L57", "--model", "claude-sonnet-5-5", "--criterion", "v2"])
    assert out.endswith("-> PASS")

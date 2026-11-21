import json

import pytest
from conftest import perfect_draft
from evals.compare import (
    bootstrap_diff,
    cases_needed,
    corrected_delta,
    paired,
    swap_test,
)
from evals.graders import numbers_supported
from evals.models import FakeModel


def test_paired_split_keeps_only_changed_cases_off_the_diagonal():
    a = {"c1": True, "c2": True, "c3": False, "c4": False}
    b = {"c1": True, "c2": False, "c3": True, "c4": False}
    assert paired(a, b) == {
        "both_pass": ["c1"],
        "a_only": ["c2"],
        "b_only": ["c3"],
        "both_fail": ["c4"],
    }


def test_bootstrap_interval_contains_the_difference_and_is_repeatable():
    a = [True] * 30 + [False] * 10
    b = [True] * 36 + [False] * 4
    diff, lo, hi = bootstrap_diff(a, b)
    assert diff == pytest.approx(0.15)
    assert lo <= diff <= hi
    assert bootstrap_diff(a, b) == (diff, lo, hi)  # fixed seed


def test_identical_versions_give_a_zero_width_interval():
    a = [True, False, True]
    assert bootstrap_diff(a, a) == (0.0, 0.0, 0.0)


def test_cases_needed_grows_as_the_change_shrinks():
    assert cases_needed(0.10, 0.10) == 77
    assert cases_needed(0.05, 0.10) == 312
    assert cases_needed(0.10, 0.20) > cases_needed(0.10, 0.10)


def test_corrected_delta_undoes_the_judges_shrinkage():
    # a judge with TPR 0.9 and TNR 0.8 reports 0.7 of a real change
    assert corrected_delta(0.07, 0.9 + 0.8 - 1) == pytest.approx(0.10)


def test_swap_test_exposes_a_judge_that_always_picks_position_a(kb):
    always_a = FakeModel(lambda s, u: {"better": "A"})
    r = swap_test(always_a, "ticket", "first reply", "second reply", kb)
    assert r == {
        "order_1": "first",
        "order_2": "second",
        "consistent": False,
        "position_a_won_both": True,
    }


def test_swap_test_agrees_with_itself_for_a_content_judge(kb):
    def prefers_short(system, user):
        a = user.split("<reply_a>\n")[1].split("\n</reply_a>")[0]
        b = user.split("<reply_b>\n")[1].split("\n</reply_b>")[0]
        return {"better": "A" if len(a) < len(b) else "B"}

    r = swap_test(FakeModel(prefers_short), "ticket", "short", "a much longer reply", kb)
    assert r["consistent"] and r["order_1"] == "first"


def test_us_style_dates_are_not_claims(kb, by_id):
    case = by_id["G02"]
    draft = {**perfect_draft(case), "reply": "Filter from January 1 to December 31, 2025."}
    assert numbers_supported(case, draft, kb).passed


def test_the_recorded_comparison_replays(runs, monkeypatch, capsys):
    import compare_versions

    before = json.loads((runs / "comparison.json").read_text())
    monkeypatch.setattr("sys.argv", ["compare_versions.py"])
    compare_versions.main()
    after = json.loads((runs / "comparison.json").read_text())
    assert after == before
    assert after["code_graders"]["passed"]["v2_only"] == ["G26"]
    assert after["code_graders"]["passed"]["ci95"] == [0.0, 0.075]

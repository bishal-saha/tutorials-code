import pytest
from evals.metrics import confusion, majority, self_consistency, wilson


def test_confusion_counts_fail_as_the_positive_class():
    labels = ["FAIL", "FAIL", "FAIL", "PASS", "PASS", "PASS", "PASS", "PASS"]
    verdicts = ["FAIL", "FAIL", "PASS", "FAIL", "PASS", "PASS", "PASS", "PASS"]
    c = confusion(labels, verdicts)
    assert (c.tp, c.fn, c.fp, c.tn) == (2, 1, 1, 4)
    assert c.tpr == pytest.approx(2 / 3)
    assert c.tnr == pytest.approx(4 / 5)
    assert c.agreement == pytest.approx(6 / 8)
    # chance agreement: (3/8)(3/8) + (5/8)(5/8) = 34/64; kappa = (48/64 - 34/64) / (30/64)
    assert c.kappa == pytest.approx(14 / 30)
    assert c.youden == pytest.approx(2 / 3 + 4 / 5 - 1)


def test_agreement_can_look_good_while_the_judge_misses_most_failures():
    labels = ["FAIL"] * 5 + ["PASS"] * 95
    verdicts = ["FAIL"] + ["PASS"] * 4 + ["PASS"] * 95  # catches 1 failure in 5
    c = confusion(labels, verdicts)
    assert c.agreement == pytest.approx(0.96)
    assert c.tpr == pytest.approx(0.2)


def test_wilson_interval_for_thirty_out_of_thirty():
    lo, hi = wilson(30, 30)
    assert round(lo, 3) == 0.886 and hi == 1.0


def test_majority_breaks_ties_towards_fail_and_consistency_counts_unanimous_items():
    assert majority(["PASS", "FAIL"]) == "FAIL"
    assert majority(["PASS", "PASS", "FAIL"]) == "PASS"
    assert self_consistency([["PASS"] * 3, ["PASS", "FAIL", "PASS"]]) == 0.5

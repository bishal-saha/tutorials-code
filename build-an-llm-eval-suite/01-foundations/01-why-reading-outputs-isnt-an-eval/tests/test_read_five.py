import pytest
import read_five


def test_the_recorded_run_has_forty_drafts_matching_the_golden_set():
    drafts, golden = read_five.load()
    assert len(drafts) == 40
    assert {d["case_id"] for d in drafts} == set(golden)


def test_the_sample_is_five_distinct_drafts_and_repeatable():
    drafts, _ = read_five.load()
    picked = read_five.sample(drafts)
    assert len({d["case_id"] for d in picked}) == 5
    assert picked == read_five.sample(drafts)


def test_checking_every_case_finds_the_missed_escalation():
    drafts, golden = read_five.load()
    assert read_five.escalation_misses(drafts, golden) == ["G26"]
    assert golden["G26"]["category"] == "promise_bait"


def test_reading_five_of_forty_sees_one_failure_one_time_in_eight():
    assert read_five.chance_to_see(1, 40, 5) == pytest.approx(0.125)
    assert read_five.chance_to_see(0, 40, 5) == 0.0

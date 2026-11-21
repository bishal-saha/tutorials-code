import copy
import json

import pytest
from evals.gate import format_result, load_thresholds, run_gate
from evals.models import FakeModel, ReplayModel
from evals.runner import read_jsonl


@pytest.fixture
def config(runs):
    return load_thresholds(runs.parent / "gate.json")


@pytest.fixture
def v2(runs):
    return read_jsonl(runs / "drafts-v2.jsonl")


def test_the_gate_passes_the_recorded_v2_run(v2, by_id, kb, config, runs):
    result = run_gate(
        v2, by_id, kb, ReplayModel(config["judge_model"], runs / "calls.jsonl"), config
    )
    assert result.status == "PASS" and result.exit_code == 0
    judge = next(c for c in result.checks if c.name == "judge_pass")
    assert (judge.passed_cases, judge.failing) == (39, ["G10"])


def test_the_gate_fails_the_seeded_regression(v2, by_id, kb, config, runs):
    from scripts.simulate_regression import regress

    result = run_gate(
        regress(v2), by_id, kb, ReplayModel(config["judge_model"], runs / "calls.jsonl"), config
    )
    assert result.status == "FAIL" and result.exit_code == 1
    esc = next(c for c in result.checks if c.name == "escalation_correct")
    assert esc.rate == pytest.approx(31 / 40)
    assert esc.failing == ["G26", "G27", "G28", "G29", "G30", "G31", "G32", "G33", "G34"]
    assert "gate: FAIL" in format_result(result)


def test_an_unrecorded_judgement_is_an_error_not_a_pass(v2, by_id, kb, config, runs):
    changed = copy.deepcopy(v2)
    changed[0]["draft"]["reply"] += " We'll also give you a free month."
    result = run_gate(
        changed, by_id, kb, ReplayModel(config["judge_model"], runs / "calls.jsonl"), config
    )
    assert result.status == "ERROR" and result.exit_code == 2
    assert "no recorded call" in result.error


def test_thresholds_cover_every_check(config):
    assert set(config["thresholds"]) == {
        "schema_valid",
        "escalation_correct",
        "cites_required",
        "numbers_supported",
        "judge_pass",
    }
    assert config["judge_model"] == "claude-haiku-5-5" and config["criterion"] == "v2"


def test_a_judge_that_fails_everything_fails_the_gate(v2, by_id, kb, config):
    harsh = FakeModel(lambda s, u: {"verdict": "FAIL"}, name="fake")
    result = run_gate(v2, by_id, kb, harsh, config)
    assert result.status == "FAIL"
    assert json.dumps(result.checks[-1].failing[:2]) == '["G01", "G02"]'


def test_a_run_that_misses_a_golden_case_is_an_error(v2, by_id, kb, config, runs):
    judge = ReplayModel(config["judge_model"], runs / "calls.jsonl")
    result = run_gate(v2[:-1], by_id, kb, judge, config)
    assert result.status == "ERROR" and result.exit_code == 2
    assert result.error.startswith("run has no draft for G40")

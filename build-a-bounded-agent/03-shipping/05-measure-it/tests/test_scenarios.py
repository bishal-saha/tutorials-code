"""Lesson 5 tests: the scenario gate, its regression check, traces and the cost report."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from agent.loop import RunResult
from agent.models import Usage
from agent.scenarios import SCENARIOS, run_scenario
from agent.trace import write_trace

HERE = Path(__file__).resolve().parent.parent


@pytest.mark.anyio
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
async def test_scenario_passes(scenario):
    result = await run_scenario(scenario)
    assert result.problems == []


def run_script(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args], cwd=HERE, capture_output=True, text=True, check=False
    )


def test_gate_passes_on_the_real_code():
    proc = run_script("run_scenarios.py")
    assert proc.returncode == 0, proc.stdout
    assert "5/5 scenarios passed" in proc.stdout


def test_gate_fails_on_a_weakened_guard():
    proc = run_script("scripts/simulate_regression.py")
    assert proc.returncode == 1
    assert "FAIL  injection" in proc.stdout
    assert "approval asked for ['escalate_ticket(HL-1001)']" in proc.stdout


def test_trace_is_one_line_per_step_plus_the_outcome(tmp_path):
    result = RunResult(
        "done",
        "ok",
        2,
        Usage(3000, 200),
        0.016,
        "",
        trace=[{"step": 1, "tool_calls": []}, {"step": 2, "tool_calls": []}],
    )
    path = tmp_path / "t.jsonl"
    write_trace(path, "run-1", result, {"ticket": "HL-1003"})
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert [line["kind"] for line in lines] == ["step", "step", "outcome"]
    assert lines[-1]["cost_usd"] == 0.016
    assert lines[-1]["ticket"] == "HL-1003"


def test_captured_cost_report_adds_up():
    report = json.loads((HERE / "runs" / "cost-report.json").read_text())
    assert report["model"] == "claude-opus-5-5"
    total = round(sum(r["cost_usd"] for r in report["runs"]), 6)
    assert report["total_cost_usd"] == total
    assert report["cost_per_task_usd"] == round(total / len(report["runs"]), 6)

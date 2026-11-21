import json

import pytest
from evals.models import Usage
from evals.pricing import cost_usd


def test_cache_hits_are_priced_per_model():
    one_million_hits = Usage(cache_read=1_000_000)
    assert cost_usd("claude-sonnet-5-5", one_million_hits) == pytest.approx(0.10)
    assert cost_usd("claude-haiku-5-5", one_million_hits) == pytest.approx(0.01)
    assert cost_usd("claude-sonnet-5-5", Usage(1_000_000, 1_000_000)) == pytest.approx(12.0)


def test_the_cost_report_adds_drafting_and_judging(runs, capsys):
    import cost_report

    cost_report.main()
    report = json.loads((runs / "cost-report.json").read_text())
    assert report["cases"] == 40
    assert report["total_usd"] == pytest.approx(
        report["drafter"]["cost_usd"] + report["judge"]["cost_usd"], abs=1e-4
    )
    assert report["judge"]["model"] == "claude-haiku-5-5"

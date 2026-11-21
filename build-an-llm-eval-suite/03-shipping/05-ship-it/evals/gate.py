"""The regression gate: grade a candidate run and compare each rate with its threshold.

Code graders run on every draft. The judge is replayed from recorded calls, so the
gate never calls the API in CI: a judgement nobody recorded stops the gate with an
error (exit 2) instead of guessing or silently skipping the check.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from evals.data import Article, Case
from evals.graders import GRADERS, grade_all
from evals.judge import judge
from evals.models import Model, NotRecorded, Usage
from evals.pricing import cost_usd


@dataclass
class Check:
    name: str
    passed_cases: int
    cases: int
    threshold: float
    failing: list[str] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.passed_cases / self.cases

    @property
    def ok(self) -> bool:
        return self.rate >= self.threshold


@dataclass
class GateResult:
    checks: list[Check]
    error: str | None = None
    judge_usage: Usage = field(default_factory=Usage)
    judge_cost_usd: float = 0.0

    @property
    def status(self) -> str:
        if self.error:
            return "ERROR"
        return "PASS" if all(c.ok for c in self.checks) else "FAIL"

    @property
    def exit_code(self) -> int:
        return {"PASS": 0, "FAIL": 1, "ERROR": 2}[self.status]


def load_thresholds(path: Path) -> dict:
    return json.loads(path.read_text())


def run_gate(
    rows: list[dict],
    cases: dict[str, Case],
    kb: dict[str, Article],
    judge_model: Model,
    config: dict,
) -> GateResult:
    thresholds = config["thresholds"]
    # A run that skips golden cases would pass on fewer cases: treat it as an error.
    missing = sorted(set(cases) - {r["case_id"] for r in rows})
    if missing:
        return GateResult([], error=f"run has no draft for {', '.join(missing)}; record them first")
    checks = []
    graded = {r["case_id"]: grade_all(cases[r["case_id"]], r["draft"], kb) for r in rows}
    for g in GRADERS:
        failing = [
            cid
            for cid, gs in graded.items()
            if not next(x for x in gs if x.name == g.__name__).passed
        ]
        checks.append(
            Check(g.__name__, len(rows) - len(failing), len(rows), thresholds[g.__name__], failing)
        )

    failing, usage = [], Usage()
    for r in rows:
        reply = (r["draft"] or {}).get("reply", "")
        try:
            verdict, c = judge(
                judge_model, cases[r["case_id"]].ticket_text(), reply, kb, config["criterion"]
            )
        except NotRecorded as exc:
            return GateResult(checks, error=f"{r['case_id']}: {exc}")
        usage = usage + c.usage
        if verdict != "PASS":
            failing.append(r["case_id"])
    checks.append(
        Check("judge_pass", len(rows) - len(failing), len(rows), thresholds["judge_pass"], failing)
    )
    return GateResult(checks, judge_usage=usage, judge_cost_usd=cost_usd(judge_model.name, usage))


def format_result(result: GateResult) -> str:
    lines = [f"{'check':<20} {'rate':>6} {'needs':>6}  result"]
    for c in result.checks:
        mark = "ok" if c.ok else "FAIL " + ", ".join(c.failing)
        lines.append(f"{c.name:<20} {c.rate:>6.1%} {c.threshold:>6.0%}  {mark}")
    if result.error:
        lines.append(f"ERROR {result.error}")
    lines.append(f"gate: {result.status}")
    return "\n".join(lines)

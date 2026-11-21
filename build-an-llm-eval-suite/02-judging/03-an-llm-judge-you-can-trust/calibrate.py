"""Calibrate the judges against the 60 labelled replies.

uv run python calibrate.py                   # replay the recorded run (no key)
uv run python calibrate.py --live --record   # call Claude and record every call
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.calibration import load_labels, report, run_judge
from evals.data import load_golden, load_kb
from evals.judge import CRITERIA, JUDGES
from evals.models import AnthropicModel, RecordingModel, ReplayModel

RUNS = Path(__file__).resolve().parent / "runs"
REPEATS = {"v1": 3, "v2": 3}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--criterion", choices=sorted(CRITERIA), action="append")
    p.add_argument("--live", action="store_true")
    p.add_argument("--record", action="store_true")
    args = p.parse_args()

    kb, labels = load_kb(), load_labels()
    cases = {c.id: c for c in load_golden()}
    reports = []
    for criterion in args.criterion or sorted(CRITERIA):
        for name in JUDGES:
            if args.live:
                model = AnthropicModel(name, effort="low")
                if args.record:
                    model = RecordingModel(model, RUNS / "calls.jsonl")
            else:
                model = ReplayModel(name, RUNS / "calls.jsonl")
            rows = run_judge(
                model, labels, cases, kb, criterion, REPEATS[criterion], 8 if args.live else 1
            )
            (RUNS / f"verdicts-{criterion}-{name}.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in rows)
            )
            rep = report(rows)
            reports.append(rep)
            print(
                f"{criterion} {name:<18} TPR {rep['tpr']:.2f}  TNR {rep['tnr']:.2f}  "
                f"agreement {rep['agreement']:.2f}  kappa {rep['kappa']:.2f}  "
                f"escalation replies passed {rep['good_escalation_replies_passed']}  "
                f"${rep['cost_usd']:.4f}"
            )
    # Keep the reports for criteria this run didn't touch.
    path = RUNS / "calibration.json"
    done = {(r["model"], r["criterion"]) for r in reports}
    kept = [r for r in json.loads(path.read_text()) if (r["model"], r["criterion"]) not in done]
    merged = sorted(kept + reports, key=lambda r: (r["criterion"], JUDGES.index(r["model"])))
    path.write_text(json.dumps(merged, indent=2) + "\n")


if __name__ == "__main__":
    main()

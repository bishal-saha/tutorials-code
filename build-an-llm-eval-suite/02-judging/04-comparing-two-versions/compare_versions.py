"""Prompt v1 vs v2 on the same 40 cases: code graders, the judge, and a pairwise swap test.

uv run python compare_versions.py                   # replay the recorded run (no key)
uv run python compare_versions.py --live --record   # call Claude and record every call
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from evals.compare import bootstrap_diff, cases_needed, corrected_delta, paired, swap_test
from evals.data import load_golden, load_kb
from evals.drafter import GENERATOR
from evals.graders import GRADERS
from evals.judge import JUDGES, judge
from evals.models import AnthropicModel, Model, RecordingModel, ReplayModel
from evals.runner import read_jsonl, run_drafts, write_jsonl

RUNS = Path(__file__).resolve().parent / "runs"


def model_for(name: str, live: bool, record: bool) -> Model:
    if not live:
        return ReplayModel(name, RUNS / "calls.jsonl")
    model: Model = AnthropicModel(name, effort="low")
    return RecordingModel(model, RUNS / "calls.jsonl") if record else model


def reply_of(row: dict) -> str:
    return (row["draft"] or {}).get("reply", "")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true")
    p.add_argument("--record", action="store_true")
    args = p.parse_args()
    workers = 8 if args.live else 1

    kb, cases = load_kb(), load_golden()
    by_id = {c.id: c for c in cases}
    v1 = {r["case_id"]: r for r in read_jsonl(RUNS / "drafts-v1.jsonl")}
    v2_rows = run_drafts(model_for(GENERATOR, args.live, args.record), cases, kb, "v2", workers)
    write_jsonl(RUNS / "drafts-v2.jsonl", v2_rows)
    v2 = {r["case_id"]: r for r in v2_rows}
    out: dict = {"cases": len(cases), "code_graders": {}, "judges": {}, "pairwise": {}}

    # 1. Code graders, case by case
    for name in ["passed"] + [g.__name__ for g in GRADERS]:
        a = {k: (r["passed"] if name == "passed" else r["grades"][name]) for k, r in v1.items()}
        b = {k: (r["passed"] if name == "passed" else r["grades"][name]) for k, r in v2.items()}
        split = paired(a, b)
        diff, lo, hi = bootstrap_diff([a[k] for k in sorted(a)], [b[k] for k in sorted(a)])
        out["code_graders"][name] = {
            "v1": sum(a.values()),
            "v2": sum(b.values()),
            "split": {k: len(v) for k, v in split.items()},
            "v1_only": split["a_only"],
            "v2_only": split["b_only"],
            "diff": round(diff, 3),
            "ci95": [round(lo, 3), round(hi, 3)],
        }

    # 2. The judge (criterion v2), one verdict per reply, corrected by its calibration
    calibration = json.loads((RUNS / "calibration.json").read_text())
    youden = {r["model"]: r["youden"] for r in calibration if r["criterion"] == "v2"}
    for name in JUDGES:
        model = model_for(name, args.live, args.record)

        def verdict(row: dict, model: Model = model) -> bool:
            v, _ = judge(model, by_id[row["case_id"]].ticket_text(), reply_of(row), kb, "v2")
            return v == "PASS"

        with ThreadPoolExecutor(max_workers=workers) as pool:
            a = dict(zip(sorted(v1), pool.map(verdict, [v1[k] for k in sorted(v1)]), strict=True))
            b = dict(zip(sorted(v2), pool.map(verdict, [v2[k] for k in sorted(v2)]), strict=True))
        split = paired(a, b)
        diff, lo, hi = bootstrap_diff([a[k] for k in sorted(a)], [b[k] for k in sorted(a)])
        out["judges"][name] = {
            "v1": sum(a.values()),
            "v2": sum(b.values()),
            "split": {k: len(v) for k, v in split.items()},
            "diff": round(diff, 3),
            "ci95": [round(lo, 3), round(hi, 3)],
            "youden": youden.get(name),
            "corrected_diff": round(corrected_delta(diff, youden[name]), 3)
            if youden.get(name)
            else None,
        }

    # 3. Pairwise, both orders: does the winner depend on the position?
    for name in JUDGES:
        model = model_for(name, args.live, args.record)

        def swap(case_id: str, model: Model = model) -> dict:
            t = by_id[case_id].ticket_text()
            return {
                "case_id": case_id,
                **swap_test(model, t, reply_of(v1[case_id]), reply_of(v2[case_id]), kb),
            }

        with ThreadPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(swap, sorted(v1)))
        consistent = [r for r in rows if r["consistent"]]
        out["pairwise"][name] = {
            "pairs": len(rows),
            "consistent": len(consistent),
            "v2_won_both_orders": sum(r["order_1"] == "second" for r in consistent),
            "v1_won_both_orders": sum(r["order_1"] == "first" for r in consistent),
            "position_a_won_both": sum(r["position_a_won_both"] for r in rows),
            "flipped_cases": [r["case_id"] for r in rows if not r["consistent"]],
        }

    # 4. How many cases would it take to see a change? A planning table: the change you
    #    want to detect, and the share of cases you expect to flip between versions.
    s = out["code_graders"]["passed"]["split"]
    out["discordant_share"] = round((s["a_only"] + s["b_only"]) / len(cases), 3)
    out["cases_needed"] = {
        f"change {d:.2f}, {q:.0%} of cases flip": cases_needed(d, q)
        for d in (0.05, 0.10)
        for q in (0.10, 0.20)
    }
    (RUNS / "comparison.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()

"""Calibrate a judge against labelled replies: run it, then compare verdicts with labels."""

from __future__ import annotations

import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from evals.data import DATA, Article, Case
from evals.judge import judge
from evals.metrics import confusion, majority, self_consistency, wilson
from evals.models import Model, Usage
from evals.pricing import cost_usd


def load_labels(path: Path = DATA / "labels.json") -> list[dict]:
    return json.loads(path.read_text())["labels"]


def run_judge(
    model: Model,
    labels: list[dict],
    cases: dict[str, Case],
    kb: dict[str, Article],
    criterion: str,
    repeats: int = 1,
    workers: int = 1,
) -> list[dict]:
    """One row per labelled item, with every repeat's verdict and the usage spent."""
    jobs = [(item, r) for item in labels for r in range(repeats)]

    def one(job: tuple[dict, int]) -> tuple[str, str | None, Usage]:
        item, r = job
        verdict, c = judge(
            model, cases[item["case_id"]].ticket_text(), item["reply"], kb, criterion, repeat=r
        )
        return item["id"], verdict, c.usage

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, jobs))

    verdicts: dict[str, list[str | None]] = defaultdict(list)
    usage: dict[str, Usage] = defaultdict(Usage)
    for item_id, verdict, u in results:
        verdicts[item_id].append(verdict)
        usage[item_id] = usage[item_id] + u
    rows = []
    for item in labels:
        vs = verdicts[item["id"]]
        # a missing verdict (refusal, bad JSON) counts as FAIL: the cautious side
        clean = [v or "FAIL" for v in vs]
        rows.append(
            {
                "id": item["id"],
                "case_id": item["case_id"],
                "label": item["label"],
                "defect": item.get("defect"),
                "escalated_reply": cases[item["case_id"]].escalate,
                "verdicts": vs,
                "verdict": majority(clean),
                "model": model.name,
                "criterion": criterion,
                "usage": asdict(usage[item["id"]]),
            }
        )
    return rows


def _passed(rows: list[dict]) -> str:
    return f"{sum(r['verdict'] == 'PASS' for r in rows)}/{len(rows)}"


def report(rows: list[dict]) -> dict:
    """The numbers lesson 3 reads: confusion, TPR/TNR with intervals, kappa, and where it erred."""
    labels = [r["label"] for r in rows]
    verdicts = [r["verdict"] for r in rows]
    c = confusion(labels, verdicts)
    model = rows[0]["model"]
    judgements = sum(len(r["verdicts"]) for r in rows)
    total = Usage()
    for r in rows:
        total = total + Usage(**r["usage"])
    cost = cost_usd(model, total)
    by_defect: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["label"] == "FAIL":
            by_defect[r["defect"]][0] += r["verdict"] == "FAIL"
            by_defect[r["defect"]][1] += 1
    good_esc = [r for r in rows if r["label"] == "PASS" and r["escalated_reply"]]
    good_ans = [r for r in rows if r["label"] == "PASS" and not r["escalated_reply"]]
    return {
        "model": model,
        "criterion": rows[0]["criterion"],
        "items": len(rows),
        "repeats": judgements // len(rows),
        "confusion": asdict(c),
        "tpr": round(c.tpr, 3),
        "tpr_95": [round(x, 3) for x in wilson(c.tp, c.tp + c.fn)],
        "tnr": round(c.tnr, 3),
        "tnr_95": [round(x, 3) for x in wilson(c.tn, c.tn + c.fp)],
        "agreement": round(c.agreement, 3),
        "kappa": round(c.kappa, 3),
        "youden": round(c.youden, 3),
        "caught_by_defect": {k: f"{v[0]}/{v[1]}" for k, v in sorted(by_defect.items())},
        "good_escalation_replies_passed": _passed(good_esc),
        "good_answer_replies_passed": _passed(good_ans),
        "self_consistency": round(
            self_consistency([[v or "FAIL" for v in r["verdicts"]] for r in rows]), 3
        ),
        "no_verdict": sum(v is None for r in rows for v in r["verdicts"]),
        "cost_usd": round(cost, 4),
        "cost_per_judgement_usd": round(cost / judgements, 6),
    }

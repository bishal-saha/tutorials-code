"""Run the drafter over the golden set, grade every draft, and write JSON Lines."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from evals.data import Article, Case
from evals.drafter import draft
from evals.graders import GRADERS, grade_all
from evals.models import Model, Usage
from evals.pricing import cost_usd


def run_case(model: Model, case: Case, kb: dict[str, Article], version: str) -> dict:
    c = draft(model, case, kb, version)
    grades = grade_all(case, c.value, kb)
    return {
        "case_id": case.id,
        "category": case.category,
        "prompt": version,
        "model": c.model,
        "stop_reason": c.stop_reason,
        "draft": c.value,
        "grades": {g.name: g.passed for g in grades},
        "details": {g.name: g.detail for g in grades if g.detail},
        "passed": all(g.passed for g in grades),
        "usage": asdict(c.usage),
        "cost_usd": cost_usd(c.model, c.usage),
    }


def run_drafts(
    model: Model, cases: list[Case], kb: dict[str, Article], version: str, workers: int = 1
) -> list[dict]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda c: run_case(model, c, kb, version), cases))


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def summary(rows: list[dict]) -> dict:
    n = len(rows)
    usage = Usage()
    for r in rows:
        usage = usage + Usage(**r["usage"])
    return {
        "cases": n,
        "all_passed": sum(r["passed"] for r in rows),
        "per_grader": {g.__name__: sum(r["grades"][g.__name__] for r in rows) for g in GRADERS},
        "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
        "usage": asdict(usage),
    }


def print_summary(s: dict) -> None:
    n = s["cases"]
    print(f"{s['all_passed']}/{n} drafts pass every grader")
    for name, k in s["per_grader"].items():
        print(f"  {name:<20} {k:>3}/{n}")
    print(f"cost ${s['cost_usd']:.4f}")

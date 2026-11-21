"""The CI gate: replay the chosen policy on the scripted shift and fail the build
when a change breaks the standing instructions, drops tickets, or blows the budget.

policy.json holds the decision and its limits, so changing the policy is a
reviewed change, not a silent one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from copilot.harness import PolicyReport, measure
from copilot.model import ShiftModel


@dataclass(frozen=True)
class PolicyConfig:
    policy: str
    model: str
    max_usd_per_shift: float
    min_cache_hit: float
    min_handled: int
    min_retention: float

    @classmethod
    def load(cls, path: Path) -> PolicyConfig:
        return cls(**json.loads(path.read_text()))


def failures(cfg: PolicyConfig, r: PolicyReport) -> list[str]:
    out = []
    if r.retention < cfg.min_retention:
        held, need = f"{r.retention:.0%}", f"{cfg.min_retention:.0%}"
        out.append(f"standing instructions held on {held} of tickets, need {need}")
    if r.handled < cfg.min_handled:
        out.append(f"{r.handled} tickets handled, need {cfg.min_handled}")
    if r.usd > cfg.max_usd_per_shift:
        out.append(f"${r.usd:.4f} per shift, budget ${cfg.max_usd_per_shift:.4f}")
    if r.cache_hit < cfg.min_cache_hit:
        out.append(f"cache hit {r.cache_hit:.1%}, need {cfg.min_cache_hit:.0%}")
    return out


async def check(cfg: PolicyConfig, **overrides: Any) -> tuple[PolicyReport, list[str]]:
    """Run the configured policy; `overrides` lets tests inject a regression."""
    kwargs: dict[str, Any] = {"policy": cfg.policy, **overrides}
    report = await measure(cfg.policy, ShiftModel(model=cfg.model), **kwargs)
    return report, failures(cfg, report)

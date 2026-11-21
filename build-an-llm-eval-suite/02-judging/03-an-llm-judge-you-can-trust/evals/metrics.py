"""Calibration arithmetic for a judge, as plain functions.

The positive class is FAIL: a judge's job at a gate is to catch failures.
    TPR  labelled FAIL that the judge marks FAIL  (catch rate)
    TNR  labelled PASS that the judge marks PASS  (good replies let through)
Raw agreement and Cohen's kappa are reported alongside, because agreement alone
hides which way a judge errs. Adapted from the AI Lab's llm-judge-calibration
benchmark (github.com/bishal-saha/ai-lab-code, MIT).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class Confusion:
    tp: int  # label FAIL, judge FAIL
    fn: int  # label FAIL, judge PASS
    fp: int  # label PASS, judge FAIL
    tn: int  # label PASS, judge PASS

    @property
    def n(self) -> int:
        return self.tp + self.fn + self.fp + self.tn

    @property
    def tpr(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else float("nan")

    @property
    def tnr(self) -> float:
        return self.tn / (self.tn + self.fp) if self.tn + self.fp else float("nan")

    @property
    def agreement(self) -> float:
        return (self.tp + self.tn) / self.n

    @property
    def kappa(self) -> float:
        po = self.agreement
        p_fail = ((self.tp + self.fn) / self.n) * ((self.tp + self.fp) / self.n)
        p_pass = ((self.fp + self.tn) / self.n) * ((self.fn + self.tn) / self.n)
        pe = p_fail + p_pass
        return (po - pe) / (1 - pe) if pe < 1 else float("nan")

    @property
    def youden(self) -> float:
        """TPR + TNR - 1: the factor a judge scales every measured change by."""
        return self.tpr + self.tnr - 1


def confusion(labels: list[str], verdicts: list[str]) -> Confusion:
    c = Counter(zip(labels, verdicts, strict=True))
    return Confusion(
        c[("FAIL", "FAIL")], c[("FAIL", "PASS")], c[("PASS", "FAIL")], c[("PASS", "PASS")]
    )


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def majority(verdicts: list[str]) -> str:
    """The verdict most repeats gave; a tie goes to FAIL, the cautious side."""
    c = Counter(verdicts)
    return "FAIL" if c["FAIL"] >= c["PASS"] else "PASS"


def self_consistency(repeats: list[list[str]]) -> float:
    """Share of items where every repeat gave the same verdict."""
    return sum(len(set(r)) == 1 for r in repeats) / len(repeats)

"""The knowledge base and the golden set, loaded from data/."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Article:
    id: str
    title: str
    body: str


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    plan: str
    subject: str
    body: str
    escalate: bool  # expected
    must_cite: tuple[str, ...]  # expected

    def ticket_text(self) -> str:
        return f"Customer plan: {self.plan}\nSubject: {self.subject}\n\n{self.body}"


def load_kb(path: Path = DATA / "helpline.json") -> dict[str, Article]:
    rows = json.loads(path.read_text())["articles"]
    return {r["id"]: Article(r["id"], r["title"], r["body"]) for r in rows}


def load_golden(path: Path = DATA / "golden.json") -> list[Case]:
    rows = json.loads(path.read_text())["cases"]
    return [
        Case(
            r["id"],
            r["category"],
            r["plan"],
            r["subject"],
            r["body"],
            r["expected"]["escalate"],
            tuple(r["expected"]["must_cite"]),
        )
        for r in rows
    ]


def kb_text(kb: dict[str, Article]) -> str:
    return "\n\n".join(f"[{a.id}] {a.title}\n{a.body}" for a in kb.values())

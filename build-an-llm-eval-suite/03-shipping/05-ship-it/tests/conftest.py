import sys
from pathlib import Path

import pytest

# Let tests import this lesson's `evals` package and scripts directly.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evals.data import load_golden, load_kb  # noqa: E402


@pytest.fixture
def kb():
    return load_kb()


@pytest.fixture
def cases():
    return load_golden()


@pytest.fixture
def by_id(cases):
    return {c.id: c for c in cases}


@pytest.fixture
def runs() -> Path:
    return ROOT / "runs"


def perfect_draft(case, reply: str = "See the article.") -> dict:
    """A draft that meets every expectation of a golden case."""
    return {"reply": reply, "cited_articles": list(case.must_cite), "escalate": case.escalate}

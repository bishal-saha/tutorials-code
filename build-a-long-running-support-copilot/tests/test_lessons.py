"""Run every lesson's own test suite in a separate process.

Each lesson folder is complete on its own and defines its own `helpline`
package, so the suites cannot share one Python process.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SERIES = Path(__file__).resolve().parent.parent
LESSONS = sorted(p.parent.parent for p in SERIES.glob("0*/*/tests/conftest.py"))


@pytest.mark.parametrize("lesson", LESSONS, ids=lambda p: p.name)
def test_lesson(lesson: Path) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
        cwd=lesson,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

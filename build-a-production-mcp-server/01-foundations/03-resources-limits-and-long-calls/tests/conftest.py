import sys
from pathlib import Path

import pytest

# Let tests import this lesson's `helpline` package directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"

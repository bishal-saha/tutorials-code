# /// script
# requires-python = ">=3.12"
# ///
"""Run the live checks on your own machine (never in CI).

Tests marked `@pytest.mark.live` call a real model or API. They are skipped
everywhere else. This script loads keys from the repo-root `.env` (git-ignored)
and runs only those tests.

    uv run scripts/live_check.py                 # every folder
    uv run scripts/live_check.py my-article      # one or more folders

Use a low-limit key: every live test is written to cost a fraction of a cent.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def folders(selected: list[str]) -> list[Path]:
    if selected:
        return [ROOT / s for s in selected]
    found = list(ROOT.glob("*/pyproject.toml")) + list(ROOT.glob("_shared/*/pyproject.toml"))
    return sorted(p.parent for p in found)


def main() -> int:
    env = {**os.environ, **load_env(ROOT / ".env")}
    failed = []
    for folder in folders(sys.argv[1:]):
        print(f"\n== {folder.relative_to(ROOT)}")
        result = subprocess.run(
            ["uv", "run", "--directory", str(folder), "pytest", "-m", "live", "-q"], env=env
        )
        # pytest exit code 5 = no live tests in this folder, which is fine.
        if result.returncode not in (0, 5):
            failed.append(folder.name)
    if failed:
        print(f"\nLive check failed in: {', '.join(failed)}")
        return 1
    print("\nLive check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

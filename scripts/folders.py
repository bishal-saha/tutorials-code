"""List the content folders (each has a pyproject.toml) as JSON for CI.

    python3 scripts/folders.py                      # every folder
    python3 scripts/folders.py --changed-since SHA  # only folders touched since SHA

A change to shared repo files (ruff.toml, .github/, scripts/) selects every folder.
Prints `folders=<json list>` for $GITHUB_OUTPUT.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED_FILES = ("ruff.toml", ".python-version", ".github/", "scripts/")


def all_folders() -> list[str]:
    pyprojects = sorted(ROOT.glob("*/pyproject.toml"))
    pyprojects += sorted(ROOT.glob("_shared/*/pyproject.toml"))
    return [p.parent.relative_to(ROOT).as_posix() for p in pyprojects]


def folder_of(path: str, folders: list[str]) -> str | None:
    for folder in folders:
        if path == folder or path.startswith(folder + "/"):
            return folder
    return None


def changed_folders(base: str) -> list[str]:
    folders = all_folders()
    if not base or set(base) == {"0"}:
        return folders
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", base, "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()
    except subprocess.CalledProcessError:
        return folders
    if any(p.startswith(SHARED_FILES) for p in out):
        return folders
    return sorted({f for p in out if (f := folder_of(p, folders))})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--changed-since", default=None)
    args = parser.parse_args()
    folders = all_folders() if args.changed_since is None else changed_folders(args.changed_since)
    print(f"folders={json.dumps(folders)}")


if __name__ == "__main__":
    main()

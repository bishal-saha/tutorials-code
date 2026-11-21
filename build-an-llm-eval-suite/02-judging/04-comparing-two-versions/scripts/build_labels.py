"""Build data/labels.json from data/reference_replies.json.

Each reference reply becomes a PASS item and its defective copy a FAIL item,
so every label is known by construction.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def build() -> list[dict]:
    rows = json.loads((DATA / "reference_replies.json").read_text())["replies"]
    items = []
    for r in rows:
        items.append({"case_id": r["case_id"], "reply": r["reference"], "label": "PASS"})
        items.append(
            {
                "case_id": r["case_id"],
                "reply": r["defective"],
                "label": "FAIL",
                "defect": r["defect"],
            }
        )
    for i, item in enumerate(items, 1):
        item["id"] = f"L{i:02d}"
    return items


if __name__ == "__main__":
    items = build()
    (DATA / "labels.json").write_text(json.dumps({"labels": items}, indent=2) + "\n")
    print(f"wrote {len(items)} labels")

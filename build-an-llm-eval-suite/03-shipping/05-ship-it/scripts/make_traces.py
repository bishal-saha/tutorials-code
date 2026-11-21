"""Build data/production-traces.jsonl: a simulated production log for the sampling example.

It replays this lesson's recorded drafts as if they were last week's (prompt v1) and
this week's (prompt v2) traffic. Feedback is set where a reader would plausibly click
thumbs-down: the draft missed an escalation. It is an illustration, not real traffic.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def build() -> list[dict]:
    golden = {c["id"]: c for c in json.loads((HERE / "data/golden.json").read_text())["cases"]}
    start = datetime(2026, 11, 9, 8, 0, tzinfo=UTC)
    traces = []
    for week, version in enumerate(["v1", "v2"]):
        rows = [
            json.loads(x) for x in (HERE / f"runs/drafts-{version}.jsonl").read_text().splitlines()
        ]
        for i, r in enumerate(rows):
            case = golden[r["case_id"]]
            missed = case["expected"]["escalate"] and not (r["draft"] or {}).get("escalate")
            traces.append(
                {
                    "trace_id": f"T-{version}-{r['case_id']}",
                    "at": (start + timedelta(days=7 * week, hours=3 * i)).isoformat(),
                    "prompt": version,
                    "plan": case["plan"],
                    "subject": case["subject"],
                    "body": case["body"],
                    "draft": r["draft"],
                    "feedback": "down" if missed else None,
                }
            )
    return traces


if __name__ == "__main__":
    traces = build()
    (HERE / "data/production-traces.jsonl").write_text(
        "".join(json.dumps(t) + "\n" for t in traces)
    )
    print(f"wrote {len(traces)} traces")

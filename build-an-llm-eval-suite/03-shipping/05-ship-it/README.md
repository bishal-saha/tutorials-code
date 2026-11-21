# Lesson 5: Ship it: a regression gate and production sampling

```bash
uv run python gate.py                                  # exit 0: the recorded v2 run passes
uv run python scripts/simulate_regression.py
uv run python gate.py runs/drafts-regressed.jsonl      # exit 1: the seeded regression fails
uv run python sample_traces.py                         # write runs/review-queue.jsonl
uv run python cost_report.py                           # what one full eval run costs
uv run pytest tests
```

| File | What it shows |
|---|---|
| `gate.json` | Per-check thresholds, the judge model and criterion |
| `evals/gate.py` | Code graders plus replayed judgements; an unrecorded judgement is an error (exit 2) |
| `evals/sampling.py` | Reference-free online checks, the review queue, review to golden case |
| `scripts/simulate_regression.py` | Security and refund/credit tickets stop escalating |
| `data/production-traces.jsonl` | A simulated production log built from the recorded runs (`scripts/make_traces.py`) |
| `runs/cost-report.json` | Drafter plus gate judge for 40 cases |

In CI the repository workflow runs `uv run --directory <series> pytest`, which runs the gate tests:
the recorded run must pass and the seeded regression must fail, with no API key.

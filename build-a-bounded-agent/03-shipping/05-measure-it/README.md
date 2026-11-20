# Lesson 5: Measure it: scenario evals and cost per task

```bash
uv run python run_scenarios.py                  # the CI gate: exit 1 if a scenario fails
uv run python scripts/simulate_regression.py    # weaken a guard and watch the gate fail
uv run --env-file .env python run_real.py       # captured runs + runs/cost-report.json
uv run pytest tests
```

| File | What it shows |
|---|---|
| `agent/scenarios.py` | Five scripted scenarios: happy path, tool outage, injection, budget exhaustion, denied escalation |
| `agent/trace.py` | One JSON line per step plus the outcome |
| `runs/` | Captured runs on HL-1003, HL-1012 and HL-1002 with prompt caching, and the cost report |

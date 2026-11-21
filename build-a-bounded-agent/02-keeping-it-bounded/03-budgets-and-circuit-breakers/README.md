# Lesson 3: Budgets and circuit breakers

```bash
uv run pytest tests
```

| File | What it shows |
|---|---|
| `agent/budgets.py` | Step, token, cost and wall-clock budgets with a clean `budget_exhausted` outcome |
| `agent/breaker.py` | Per-tool circuit breaker (closed, open, half-open) |
| `agent/loop.py` | Retries only for read-only tools on transient failures; the third identical call is refused |
| `agent/faults.py` | Make a tool fail on purpose |

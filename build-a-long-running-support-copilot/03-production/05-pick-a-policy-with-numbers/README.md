# Lesson 5: Pick a policy with numbers

```bash
uv run python pick_policy.py                   # every candidate policy, on Sonnet and Haiku
uv run python check_policy.py                  # the CI gate for policy.json
uv run python scripts/simulate_regression.py   # three harmless-looking changes, and what the gate says
uv run python live_shift.py trim --cap 0.50    # one real shift with Claude (needs a key; costs money)
uv run pytest tests
```

| File | What it shows |
|---|---|
| `copilot/harness.py` | Run candidates on the same shift; window, cache, cost, handled, retention |
| `copilot/shift.py` | Summariser calls are charged; `max_usd` stops a run before it passes its cap |
| `policy.json`, `copilot/gate.py`, `check_policy.py` | The decision and its limits, checked in CI |
| `scripts/simulate_regression.py` | A clock in the prompt, a misleading placeholder, a summary that drops the rules |
| `ci/github-actions.yml` | Tests plus the gate |

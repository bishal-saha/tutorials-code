# Lesson 2: A golden set and code graders

```bash
uv run python run_eval.py                    # replay the recorded run; no key
uv run pytest tests
cp .env.example .env                         # then set ANTHROPIC_API_KEY
uv run --env-file .env python run_eval.py --live --record
```

| File | What it shows |
|---|---|
| `evals/drafter.py` | The feature: prompt v1, the JSON schema, one structured-output call |
| `evals/models.py` | `FakeModel`, `AnthropicModel` (stop_reason before parsing), `RecordingModel`, `ReplayModel` |
| `evals/graders.py` | Four code graders, and the digits that turned out not to be claims |
| `evals/runner.py` | Run, grade, write JSON Lines, summarise |
| `data/golden.json` | 40 cases: expected escalation, required citations, a trap category |
| `runs/first-grader-output.txt` | The first grader's output: five of its six failures were the grader's fault |

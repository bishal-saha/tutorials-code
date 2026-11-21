# Lesson 4: Comparing two versions without fooling yourself

```bash
uv run python compare_versions.py            # replay the recorded comparison; no key
uv run pytest tests
uv run --env-file .env python compare_versions.py --live --record
```

| File | What it shows |
|---|---|
| `evals/drafter.py` | Prompt v2: the written escalation policy and promise rules |
| `evals/compare.py` | Paired splits, bootstrap interval, cases needed, judge shrinkage, pairwise swap test |
| `compare_versions.py` | v1 vs v2 on the same 40 cases with code graders, both judges and both orders |
| `runs/comparison.json` | The result; `comparison-before-grader-fix.json` is the first read |

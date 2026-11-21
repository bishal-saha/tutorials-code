# Lesson 3: An LLM judge you can trust

```bash
uv run python calibrate.py                   # replay the recorded calibration; no key
uv run pytest tests
uv run --env-file .env python calibrate.py --live --record
```

| File | What it shows |
|---|---|
| `evals/judge.py` | One criterion, PASS/FAIL, structured output; criteria v1 and the sharpened v2 |
| `evals/metrics.py` | Confusion with FAIL as the positive class, TPR, TNR, kappa, Wilson intervals, majority |
| `evals/calibration.py` | Run a judge over labelled replies and report where it errs and what it costs |
| `data/reference_replies.json` | 30 reference replies and 30 copies with one planted defect each |
| `data/labels.json` | The 60 labels, known by construction (`scripts/build_labels.py`) |
| `runs/calibration.json` | Haiku 5.5 and Sonnet 5.5 on criteria v1 and v2, 3 repeats each |
| `runs/calibration-before-label-fix.json` | The first run, before a wrong label was corrected |

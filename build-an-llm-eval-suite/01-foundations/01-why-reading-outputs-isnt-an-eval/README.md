# Lesson 1: Why reading outputs isn't an eval

```bash
uv run python read_five.py     # replays a recorded run; no key
uv run pytest tests
```

| File | What it shows |
|---|---|
| `read_five.py` | Five random drafts, then every draft checked against its expected escalation |
| `runs/drafts-v1.jsonl` | The recorded drafter run (claude-sonnet-5-5, prompt v1, 2026-11-21) |
| `data/golden.json` | The 40 tickets and what each draft should do (built in lesson 2) |
| `data/helpline.json` | The 15 knowledge-base articles, for reading drafts against |

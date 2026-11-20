# Lesson 1: What makes an agent run away

Reading lesson. `runaway.py` runs a deliberately unbounded loop with a scripted model that
keeps repeating one search. Only `SAFETY_NET` stops it.

```bash
uv run python runaway.py
uv run pytest tests
```

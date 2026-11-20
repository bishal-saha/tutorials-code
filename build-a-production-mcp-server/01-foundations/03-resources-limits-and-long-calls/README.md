# Lesson 3: Resources, limits and long calls

```bash
uv run python main.py
uv run pytest tests
```

| File | What it shows |
|---|---|
| `helpline/limits.py` | Opaque cursors bound to their query; the newest-messages-within-budget rule |
| `helpline/server.py` | Resource templates, paged `search_tickets`, budgeted `get_ticket`, a slow `search_knowledge_base` with timeout, progress and cancellation |
| `tests/test_limits.py` | Each limit, including a real cancellation from the client |

# Lesson 2: Lay out the prompt for the cache

```bash
uv run python layout.py   # six ways to build the same requests, and their cache hit rates
uv run pytest tests
```

| File | What it shows |
|---|---|
| `copilot/prompt.py` | `stable_tools()` and `add_operator_note()` with its placement rules |
| `copilot/shift.py` | Per-request system/tool builders, and operator notes appended or (wrongly) edited in |
| `copilot/model.py` | `AnthropicModel` sends automatic `cache_control` |
| `layout.py` | A clock in the system prompt, shuffled tools, and notes, measured |
| `tests/test_layout.py` | Red/green for each silent invalidator; note placement |

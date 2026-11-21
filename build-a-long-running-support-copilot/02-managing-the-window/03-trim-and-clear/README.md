# Lesson 3: Trim at the tool boundary, clear with honest placeholders

```bash
uv run python compare.py   # raw, trim, clear and a misleading placeholder on one shift
uv run pytest tests
```

| File | What it shows |
|---|---|
| `copilot/trim.py` | Per-tool trimmers applied once, when a result is added |
| `copilot/policies.py` | `raw`, `trim`, `clear`; `STUB` vs `MISLEADING_STUB`; `close()` drops thinking from finished tickets |
| `copilot/model.py` | `clear_tool_uses()`: server-side clearing through the context-editing beta |
| `tests/test_trim_and_clear.py` | Trim halves the window; clear rebuilds the cache; the misleading placeholder stops the copilot |

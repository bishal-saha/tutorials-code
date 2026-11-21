# Lesson 4: Summaries, compaction and memory across shifts

```bash
uv run python compare.py      # every policy, plus the two ways summaries fail
uv run python two_shifts.py   # a memory note carries a rule into the next shift
uv run pytest tests
```

| File | What it shows |
|---|---|
| `copilot/summariser.py` | `RuleSummariser` (with the two failure switches) and `ClaudeSummariser` |
| `copilot/policies.py` | `summary`, `summary+pin`, `fresh`, `compact`; the `Window` the shift carries |
| `copilot/model.py` | On-demand `compact()`, threshold `compact_at`, and the beta header on requests that carry the block |
| `copilot/tools.py` | The SDK's file-backed memory tool, routed as a tool |
| `tests/test_summaries_compaction_memory.py` | Pinning vs dropped instructions, the stale open item, compaction block placement, memory across shifts |

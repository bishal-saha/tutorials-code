# Lesson 2: A minimal agent loop over MCP tools

```bash
uv run pytest tests                     # FakeModel only, no key
cp .env.example .env                     # then set ANTHROPIC_API_KEY
uv run --env-file .env python run_real.py HL-1003   # one real run, trace in runs/
```

| File | What it shows |
|---|---|
| `agent/tools.py` | MCP tools listed over `mcp.Client` and turned into Claude tool definitions |
| `agent/loop.py` | The manual loop: `stop_reason` first, all `tool_result`s in one user message |
| `agent/models.py` | `Turn`, `FakeModel`, `AnthropicModel` (`claude-opus-5-5`, effort set explicitly) |
| `agent/pricing.py` | Cost from reported usage |
| `runs/HL-1003.json` | A captured real run (model, date, usage, cost, trace) |

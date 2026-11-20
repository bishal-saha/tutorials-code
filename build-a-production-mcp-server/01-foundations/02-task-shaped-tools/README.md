# Lesson 2: Task-shaped tools with MCPServer

```bash
uv run python main.py      # stdio server; an MCP host launches this
uv run pytest tests        # drives the server through the SDK's in-process Client
```

| File | What it shows |
|---|---|
| `helpline/server.py` | `search_tickets`, `get_ticket`, `search_knowledge_base`, `draft_reply`, `escalate_ticket` |
| `helpline/store.py` | The system behind the server: SQLite loaded from `data/helpline.json` |
| `explore.py` | Lists the tools and makes two calls through the in-process `Client`, printing what a host sees |
| `tests/test_tools.py` | Schemas, structured results, tool errors with hints, idempotent escalation |

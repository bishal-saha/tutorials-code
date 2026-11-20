# Lesson 1: How an agent calls your server, and where it goes wrong

Reading lesson. This folder lets you watch the protocol: `wire.py` starts `tiny_server.py`
as a subprocess and speaks MCP to it over stdio with no client SDK, printing each message.

```bash
uv run python wire.py
uv run pytest tests
```

| File | What it shows |
|---|---|
| `tiny_server.py` | One ticket, three tools: a working one, one that fails with a hint, one that crashes |
| `wire.py` | Nine requests (`server/discover`, `tools/list`, six `tools/call`s and a `resources/read`), all with per-request `_meta` |

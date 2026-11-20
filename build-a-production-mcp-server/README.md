# Build a production MCP server

> Code for the tutorial **[Build a production MCP server](https://iambishal.com/tutorials/build-a-production-mcp-server)** on iambishal.com.
> Each lesson folder holds the complete, runnable code at the end of that lesson.

| | |
|---|---|
| Type | Tutorial (5 lessons) |
| Tested with | Python 3.12 · mcp 2.3.0 (MCP spec 2026-07-28) · uv 0.12 · last verified 2026-11-21 |
| Run | `uv sync`, then `uv run python main.py` inside a lesson folder |
| Tests | `uv run pytest` here runs every lesson's suite; or `uv run pytest tests` inside one lesson |
| Keys | none: the data is a synthetic SQLite fixture, and lesson 4 brings its own test token issuer |

## Lessons

| # | Lesson | Folder | What it adds |
|---|---|---|---|
| 1 | How an agent calls your server, and where it goes wrong | `01-foundations/01-how-an-agent-calls-your-server` | `wire.py`: raw JSON-RPC over stdio to a tiny server, every message printed |
| 2 | Task-shaped tools with MCPServer | `01-foundations/02-task-shaped-tools` | Five Helpline tools with typed inputs, output schemas, tool errors with hints, idempotent escalation |
| 3 | Resources, limits and long calls | `01-foundations/03-resources-limits-and-long-calls` | Resource templates, cursor pagination, an output budget, timeout, progress and cancellation |
| 4 | Streamable HTTP with OAuth, without token passthrough | `02-security/04-streamable-http-with-oauth` | Resource-server auth: JWT checks, protected resource metadata, per-tool scopes, the server's own downstream credential |
| 5 | Ship it: contract tests, audit and a breaking-change gate | `03-production/05-ship-it` | Audit records, rate limits, contract snapshot and gate, Dockerfile, Claude Code and Claude Desktop configs |

Helpline is a made-up support desk; every company, person and ticket in `data/helpline.json` is synthetic.

## Licence

MIT, see the repository's [LICENSE](../LICENSE).

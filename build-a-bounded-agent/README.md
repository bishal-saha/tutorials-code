# Build a bounded agent

> Code for the tutorial **[Build a bounded agent](https://iambishal.com/tutorials/build-a-bounded-agent)** on iambishal.com.
> Each lesson folder holds the complete, runnable code at the end of that lesson.

| | |
|---|---|
| Type | Tutorial (5 lessons) |
| Tested with | Python 3.12 · anthropic 2.12.0 · mcp 2.3.0 (MCP spec 2026-07-28) · uv 0.12 · last verified 2026-11-21 |
| Tests | `uv run pytest` here runs every lesson's suite; or `uv run pytest tests` inside one lesson |
| Keys | none for tests (a scripted `FakeModel`); `run_real.py` in lessons 2 and 5 needs `ANTHROPIC_API_KEY` (see `.env.example`) |
| Model | real runs use `claude-opus-5-5`; captured runs are in each lesson's `runs/` |

## Lessons

| # | Lesson | Folder | What it adds |
|---|---|---|---|
| 1 | What makes an agent run away | `01-foundations/01-what-makes-an-agent-run-away` | `runaway.py`: an unbounded loop that only a safety net stops |
| 2 | A minimal agent loop over MCP tools | `01-foundations/02-a-minimal-agent-loop-over-mcp-tools` | MCP tools as Claude tools, the manual loop, `FakeModel` and `AnthropicModel`, one captured run |
| 3 | Budgets and circuit breakers | `02-keeping-it-bounded/03-budgets-and-circuit-breakers` | Step, token, cost and time budgets; per-tool breakers; read-only retries; repeated-call refusal |
| 4 | Guardrails and a human approval gate | `02-keeping-it-bounded/04-guardrails-and-a-human-approval-gate` | Untrusted-data delimiting, task allowlist, scope check, draft checks, approval gate and log |
| 5 | Measure it: scenario evals and cost per task | `03-shipping/05-measure-it` | Scenario gate for CI, traces, captured runs with prompt caching and a cost report |

The agent talks to **Helpline**, the MCP server from *Build a production MCP server*. Each
lesson that needs it carries an unchanged copy of that tutorial's final `helpline/` package.
All tickets and customers are synthetic; `HL-1012` (lessons 4 and 5) is a deliberate
prompt-injection fixture.

## Licence

MIT, see the repository's [LICENSE](../LICENSE).

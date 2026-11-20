# Lesson 5: Ship it: contract tests, audit and a breaking-change gate

```bash
uv run pytest tests                              # includes the contract gate
uv run python check_contract.py                  # exit 1 on a breaking change
uv run python scripts/simulate_breaking_change.py   # watch the gate fail
HELPLINE_DEV=1 uv run python main.py                            # HTTP; or stdio_main.py for stdio
```

Docker (build from the series folder):

```bash
docker build -f 03-production/05-ship-it/Dockerfile -t helpline-mcp .
```

| File | What it shows |
|---|---|
| `helpline/ops.py` | `AuditMiddleware` (one redacted JSON record per tool call), `RateLimitMiddleware` (token buckets per caller) |
| `helpline/contract.py` + `contract/helpline-contract.json` | The captured contract and the breaking/additive comparison |
| `scripts/smoke_http.py` | Calls a running server over Streamable HTTP with a token |
| `clients/` | Claude Code commands and a Claude Desktop config |
| `ci/github-actions.yml` | Lint, tests and the contract gate in CI |

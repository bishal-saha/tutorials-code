# Connect Claude Code

## Over HTTP (with a token)

```bash
# terminal 1: the server, trusting the local test issuer
HELPLINE_DEV=1 uv run python main.py

# terminal 2: mint a dev token and register the server
TOKEN=$(uv run python issue_token.py tickets:read)
claude mcp add --transport http helpline http://127.0.0.1:8000/mcp \
  --header "Authorization: Bearer $TOKEN"
```

Use `issue_token.py tickets:read tickets:escalate` to let Claude Code escalate.
Dev tokens last an hour; mint a new one and run `claude mcp remove helpline` then
`claude mcp add ...` again when it expires.

## Over stdio

```bash
claude mcp add helpline -- uv run --directory "$PWD" python stdio_main.py
```

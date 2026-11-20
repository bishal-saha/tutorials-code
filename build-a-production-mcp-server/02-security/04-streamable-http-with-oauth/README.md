# Lesson 4: Streamable HTTP with OAuth, without token passthrough

```bash
HELPLINE_DEV=1 uv run python main.py                                   # http://127.0.0.1:8000/mcp
uv run python issue_token.py tickets:read               # a dev token it accepts
uv run pytest tests                                     # runs a real server on a random port
```

With `HELPLINE_DEV=1`, `main.py` trusts a local test issuer whose key is kept in `.dev-issuer.pem` (never commit it).
For a real authorization server set `HELPLINE_ISSUER`, `HELPLINE_JWKS_URI` and
`HELPLINE_RESOURCE_URL`.

| File | What it shows |
|---|---|
| `helpline/auth.py` | `JwtTokenVerifier` (signature, issuer, audience, expiry), `ToolScopeMiddleware` (403 `insufficient_scope`), `require_scope` |
| `helpline/issuer.py` | The test issuer: an RSA key, its JWKS, and `mint()` |
| `helpline/backend.py` | Downstream calls with the server's own credential, naming the acting user |
| `tests/test_http_auth.py` | Metadata, 401s for wrong audience, issuer, key or expiry, the scope challenge, no passthrough |

"""require_scope: the in-tool check that backs up the HTTP middleware."""

import pytest
from helpline.auth import require_scope
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.server.mcpserver.exceptions import ToolError


def as_caller(scopes: list[str]):
    token = AccessToken(token="t", client_id="c", scopes=scopes, subject="agent-maria")
    return auth_context_var.set(AuthenticatedUser(token))


def test_no_token_means_stdio_and_is_allowed():
    assert require_scope("tickets:escalate") is None


def test_missing_scope_is_refused_inside_the_tool():
    reset = as_caller(["tickets:read"])
    try:
        with pytest.raises(ToolError, match="tickets:escalate"):
            require_scope("tickets:escalate")
    finally:
        auth_context_var.reset(reset)


def test_granted_scope_returns_the_token():
    reset = as_caller(["tickets:read", "tickets:escalate"])
    try:
        assert require_scope("tickets:escalate").subject == "agent-maria"
    finally:
        auth_context_var.reset(reset)


def test_malformed_customers_claim_grants_nothing():
    import asyncio

    from helpline.auth import JwtTokenVerifier
    from helpline.issuer import TestIssuer

    issuer = TestIssuer()
    verifier = JwtTokenVerifier(issuer=issuer.issuer, audience="http://x/mcp", jwks=issuer.jwks())
    token = issuer.mint(audience="http://x/mcp", scopes=["tickets:read"], helpline_customers="*")
    assert asyncio.run(verifier.verify_token(token)).customers == []  # a string, not a list


def test_http_app_refuses_a_server_without_a_verifier():
    from helpline.server import build_server, http_app

    with pytest.raises(ValueError, match="token_verifier"):
        http_app(build_server(), "http://127.0.0.1:8000/mcp")

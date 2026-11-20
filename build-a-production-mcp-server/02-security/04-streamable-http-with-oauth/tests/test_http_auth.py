"""Lesson 4 tests: Helpline over real Streamable HTTP, as an OAuth resource server.

A uvicorn server runs on a random localhost port for the whole module. Tokens
come from the local test issuer; nothing leaves the machine.
"""

from __future__ import annotations

import socket
import threading
import time

import httpx2
import pytest
import uvicorn
from helpline.auth import JwtTokenVerifier
from helpline.backend import TicketingAPI
from helpline.issuer import TestIssuer
from helpline.server import build_server, http_app
from helpline.store import HelplineStore
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError

READ = ["tickets:read"]
ESCALATE = ["tickets:read", "tickets:escalate"]


class Live:
    """The running server and what the tests need to reach and inspect it."""

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        port = self.sock.getsockname()[1]
        self.base = f"http://127.0.0.1:{port}"
        self.resource = f"{self.base}/mcp"
        self.issuer = TestIssuer()
        self.api = TicketingAPI(HelplineStore(), service_token="svc-helpline-7f3a")
        verifier = JwtTokenVerifier(
            issuer=self.issuer.issuer, audience=self.resource, jwks=self.issuer.jwks()
        )
        server = build_server(
            api=self.api,
            store=self.api.store,
            kb_delay_seconds=0,
            token_verifier=verifier,
            issuer_url=self.issuer.issuer,
            resource_url=self.resource,
        )
        config = uvicorn.Config(http_app(server, self.resource), log_level="warning")
        self.uvicorn = uvicorn.Server(config)
        self.thread = threading.Thread(
            target=self.uvicorn.run, kwargs={"sockets": [self.sock]}, daemon=True
        )

    def token(self, scopes=READ, **kwargs) -> str:
        # By default the caller works Corvid Analytics' tickets (HL-1003, HL-1006, HL-1010).
        kwargs.setdefault("helpline_customers", ["corvid"])
        return self.issuer.mint(
            audience=kwargs.pop("audience", self.resource), scopes=scopes, **kwargs
        )

    def client(self, token: str) -> Client:
        http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"})
        return Client(streamable_http_client(self.resource, http_client=http))


@pytest.fixture(scope="module")
def live():
    server = Live()
    server.thread.start()
    deadline = time.time() + 10
    while not server.uvicorn.started:
        assert time.time() < deadline, "server did not start"
        time.sleep(0.05)
    yield server
    server.uvicorn.should_exit = True
    server.thread.join(timeout=5)


def post_tools_list(live: Live, token: str | None) -> httpx2.Response:
    """A raw MCP request, to see the HTTP status and headers the client would see."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2026-07-28",
        "Mcp-Method": "tools/list",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                "io.modelcontextprotocol/clientCapabilities": {},
            }
        },
    }
    return httpx2.post(live.resource, json=body, headers=headers)


# --- discovery -------------------------------------------------------------


def test_protected_resource_metadata(live):
    meta = httpx2.get(f"{live.base}/.well-known/oauth-protected-resource/mcp").json()
    assert meta["resource"] == live.resource
    assert meta["authorization_servers"] == ["https://auth.helpline.test"]
    assert meta["scopes_supported"] == ["tickets:read"]


def test_no_token_gets_401_pointing_at_the_metadata(live):
    response = post_tools_list(live, None)
    assert response.status_code == 401
    www = response.headers["www-authenticate"]
    assert www.startswith("Bearer ")
    assert 'resource_metadata="' + live.base + '/.well-known/oauth-protected-resource/mcp"' in www


# --- token validation ------------------------------------------------------


def test_valid_token_is_accepted(live):
    assert post_tools_list(live, live.token()).status_code == 200


def test_token_for_another_server_is_rejected(live):
    stolen = live.token(audience="https://billing.example.com/mcp")
    assert post_tools_list(live, stolen).status_code == 401


def test_token_from_another_issuer_is_rejected(live):
    forged = live.token(issuer="https://evil.example")
    assert post_tools_list(live, forged).status_code == 401


def test_token_signed_by_another_key_is_rejected(live):
    other = TestIssuer(kid=live.issuer.kid)  # same kid and issuer, different key
    forged = other.mint(audience=live.resource, scopes=READ)
    assert post_tools_list(live, forged).status_code == 401


def test_expired_token_is_rejected(live):
    expired = live.token(ttl_seconds=-120)  # beyond the 30s leeway
    assert post_tools_list(live, expired).status_code == 401


def test_token_without_read_scope_gets_403(live):
    response = post_tools_list(live, live.token(scopes=["tickets:escalate"]))
    assert response.status_code == 403
    assert 'error="insufficient_scope"' in response.headers["www-authenticate"]


# --- through a real MCP client --------------------------------------------


@pytest.mark.anyio
async def test_read_tools_work_over_http(live):
    async with live.client(live.token()) as client:
        result = await client.call_tool("search_tickets", {"query": "webhook", "status": "open"})
    assert result.structured_content["tickets"][0]["id"] == "HL-1003"


@pytest.mark.anyio
async def test_escalate_without_scope_fails_and_changes_nothing(live):
    before = len(live.api.requests)
    async with live.client(live.token(READ)) as client:
        # Without an OAuth provider to do the step-up, the SDK client surfaces the
        # 403 as a generic error; the challenge headers are for its auth layer.
        with pytest.raises(MCPError) as caught:
            await client.call_tool(
                "escalate_ticket",
                {"ticket_id": "HL-1006", "severity": "high", "reason": "Sync blocked nightly"},
            )
    assert caught.value.error.code == -32603
    assert len(live.api.requests) == before  # nothing reached the ticketing API


def test_escalate_challenge_names_the_scope(live):
    token = live.token(READ)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2026-07-28",
        "Mcp-Method": "tools/call",
        "Mcp-Name": "escalate_ticket",
    }
    response = httpx2.post(live.resource, headers=headers, json={})
    assert response.status_code == 403
    www = response.headers["www-authenticate"]
    assert 'scope="tickets:read tickets:escalate"' in www
    assert "resource_metadata=" in www


@pytest.mark.anyio
async def test_escalate_with_scope_uses_the_servers_own_credential(live):
    token = live.token(ESCALATE, subject="agent-maria")
    async with live.client(token) as client:
        result = await client.call_tool(
            "escalate_ticket",
            {"ticket_id": "HL-1006", "severity": "high", "reason": "Sync blocked nightly"},
        )
    assert result.is_error is False
    sent = live.api.requests[-1]  # the raw HTTP request Helpline sent downstream
    assert (sent.method, sent.url.path) == ("POST", "/tickets/HL-1006/escalations")
    assert sent.headers["authorization"] == "Bearer svc-helpline-7f3a"
    assert sent.headers["x-acting-user"] == "agent-maria"
    # No token passthrough: the caller's token is in no header and no body of any request.
    for request in live.api.requests:
        assert all(token not in value for value in request.headers.values())
        assert token.encode() not in request.content


def test_legacy_call_without_mcp_headers_is_still_refused(live):
    # A 2025-11-25 client sends no Mcp-Method/Mcp-Name headers, so ToolScopeMiddleware
    # can't see the tool. require_scope inside the tool is what stops it.
    before = len(live.api.requests)
    headers = {
        "Authorization": f"Bearer {live.token(READ)}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-11-25",
    }
    body = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "escalate_ticket",
            "arguments": {"ticket_id": "HL-1006", "severity": "high", "reason": "Sync blocked"},
        },
    }
    result = httpx2.post(live.resource, json=body, headers=headers).json()["result"]
    assert result["isError"] is True
    assert "needs the tickets:escalate scope" in result["content"][0]["text"]
    assert len(live.api.requests) == before


def test_modern_call_without_mcp_headers_is_rejected(live):
    headers = {
        "Authorization": f"Bearer {live.token(READ)}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2026-07-28",
    }
    meta = {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    body = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "get_ticket", "arguments": {"ticket_id": "HL-1006"}, "_meta": meta},
    }
    response = httpx2.post(live.resource, json=body, headers=headers)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == -32020


# --- per-customer access: scopes say what, the customers claim says whose -----


@pytest.mark.anyio
async def test_search_only_returns_the_callers_customers(live):
    async with live.client(live.token()) as client:
        data = (await client.call_tool("search_tickets", {"limit": 10})).structured_content
    assert data["total"] == 3
    assert {t["customer"] for t in data["tickets"]} == {"Corvid Analytics"}


@pytest.mark.anyio
async def test_supervisor_with_star_sees_every_customer(live):
    async with live.client(live.token(helpline_customers=["*"])) as client:
        data = (await client.call_tool("search_tickets", {"limit": 10})).structured_content
    assert data["total"] == 11


@pytest.mark.anyio
async def test_token_without_the_claim_sees_nothing(live):
    token = live.token(helpline_customers=None)  # claim present but null: grants nothing
    async with live.client(token) as client:
        data = (await client.call_tool("search_tickets", {})).structured_content
        detail = await client.call_tool("get_ticket", {"ticket_id": "HL-1003"})
    assert data["total"] == 0
    assert detail.is_error is True


@pytest.mark.anyio
async def test_other_customers_ticket_looks_exactly_like_a_missing_one(live):
    async with live.client(live.token()) as client:
        other = await client.call_tool("get_ticket", {"ticket_id": "HL-1001"})  # Acme's
        missing = await client.call_tool("get_ticket", {"ticket_id": "HL-1999"})
    assert other.is_error and missing.is_error
    assert other.content[0].text.replace("HL-1001", "X") == missing.content[0].text.replace(
        "HL-1999", "X"
    )


@pytest.mark.anyio
async def test_cannot_escalate_another_customers_ticket(live):
    before = len(live.api.requests)
    token = live.token(ESCALATE, subject="agent-maria")  # can escalate, but only for Corvid
    async with live.client(token) as client:
        result = await client.call_tool(
            "escalate_ticket",
            {"ticket_id": "HL-1001", "severity": "urgent", "reason": "Acme SSO down for all"},
        )
    assert result.is_error is True
    assert "No ticket with id 'HL-1001'" in result.content[0].text
    assert len(live.api.requests) == before  # nothing reached the ticketing API


@pytest.mark.anyio
async def test_other_customers_resource_is_not_found(live):
    async with live.client(live.token()) as client:
        with pytest.raises(MCPError) as caught:
            await client.read_resource("helpline://tickets/HL-1001")
    assert caught.value.error.code == -32602

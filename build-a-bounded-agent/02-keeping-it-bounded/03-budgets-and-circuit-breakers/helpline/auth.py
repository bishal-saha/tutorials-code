"""Token checks for Helpline as an OAuth resource server.

- JwtTokenVerifier: accepts a bearer token only if its signature, issuer,
  audience and expiry all check out. The SDK calls it on every HTTP request.
- ToolScopeMiddleware: refuses a tools/call with 403 insufficient_scope when the
  token lacks the scope that tool needs, before the request reaches the server.
- require_scope: the same rule inside the tool, for defence in depth.
- allowed_customers: which customers' tickets this caller may touch, from the
  token's helpline_customers claim. Scopes say what a caller may do; this says
  to whose data.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import jwt
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.mcpserver.exceptions import ToolError
from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger("helpline.auth")

READ_SCOPE = "tickets:read"
ESCALATE_SCOPE = "tickets:escalate"

# The token claim listing the customer ids a caller acts for; ["*"] means all.
CUSTOMERS_CLAIM = "helpline_customers"
ALL_CUSTOMERS = "*"

# Every tool needs tickets:read (the SDK checks that for all requests).
# These tools need more.
TOOL_SCOPES: dict[str, list[str]] = {
    "escalate_ticket": [READ_SCOPE, ESCALATE_SCOPE],
}


class HelplineAccessToken(AccessToken):
    """The SDK's AccessToken plus the customers this caller acts for."""

    customers: list[str] = []


class JwtTokenVerifier:
    """Verify RFC 9068 JWT access tokens against the issuer's published keys."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks: dict | None = None,
        jwks_uri: str | None = None,
        leeway_seconds: int = 30,
    ) -> None:
        if (jwks is None) == (jwks_uri is None):
            raise ValueError("pass exactly one of jwks or jwks_uri")
        self.issuer = issuer
        self.audience = audience
        self.leeway = leeway_seconds
        if jwks is not None:
            keys = jwt.PyJWKSet.from_dict(jwks)
            self._key_for: Callable[[str], object] = lambda token: _key_by_kid(keys, token)
        else:
            client = jwt.PyJWKClient(jwks_uri, cache_keys=True)
            self._key_for = lambda token: client.get_signing_key_from_jwt(token).key

    async def verify_token(self, token: str) -> HelplineAccessToken | None:
        try:
            claims = jwt.decode(
                token,
                self._key_for(token),
                algorithms=["RS256", "ES256"],  # never "none", never HS* with a public key
                issuer=self.issuer,
                audience=self.audience,  # the token must be issued for this server
                leeway=self.leeway,
                options={"require": ["iss", "sub", "aud", "exp"]},
            )
        except (jwt.PyJWTError, KeyError) as exc:
            log.info("rejected token: %s", exc)  # the reason stays in our logs
            return None
        customers = claims.get(CUSTOMERS_CLAIM, [])
        if not (isinstance(customers, list) and all(isinstance(c, str) for c in customers)):
            customers = []  # a malformed claim grants nothing
        return HelplineAccessToken(
            token=token,
            customers=customers,
            client_id=str(claims.get("client_id") or claims.get("azp") or "unknown"),
            scopes=str(claims.get("scope", "")).split(),
            expires_at=int(claims["exp"]),
            resource=self.audience,
            subject=str(claims["sub"]),
        )


def _key_by_kid(keys: jwt.PyJWKSet, token: str) -> object:
    kid = jwt.get_unverified_header(token).get("kid")
    return keys[kid].key


def require_scope(scope: str) -> AccessToken | None:
    """Inside a tool: refuse when the caller's token lacks `scope`.

    Returns None on stdio, where there is no token (the process owner is the caller).
    """
    token = get_access_token()
    if token is not None and scope not in token.scopes:
        raise ToolError(f"This action needs the {scope} scope.")
    return token


def allowed_customers() -> set[str] | None:
    """Customer ids the caller may act for, or None for no restriction.

    None on stdio (no token: the process owner is the caller) and for a token
    with helpline_customers ["*"]. A token without the claim gets an empty set:
    deny by default.
    """
    token = get_access_token()
    if token is None:
        return None
    customers = set(getattr(token, "customers", []))
    return None if ALL_CUSTOMERS in customers else customers


def may_access(customer_id: str) -> bool:
    allowed = allowed_customers()
    return allowed is None or customer_id in allowed


class ToolScopeMiddleware:
    """Return 403 insufficient_scope for a tools/call the token is not scoped for.

    Modern MCP clients mirror the method and tool name into the Mcp-Method and
    Mcp-Name headers, so this check needs no body parsing. The SDK rejects a
    modern request whose headers are missing or disagree with its body. Legacy
    (2025-11-25) requests carry no such headers and pass straight through, so
    require_scope inside the tool is the real guarantee; this adds the 403 challenge.
    """

    def __init__(self, app: ASGIApp, resource_metadata_url: str) -> None:
        self.app = app
        self.resource_metadata_url = resource_metadata_url

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
            needed = TOOL_SCOPES.get(headers.get("mcp-name", ""), [])
            if headers.get("mcp-method") == "tools/call" and needed:
                token = getattr(scope.get("user"), "access_token", None)
                # No valid token: let the SDK answer 401. Valid but too narrow: 403 here.
                if token is not None and not set(needed) <= set(token.scopes):
                    await self._challenge(send, needed)
                    return
        await self.app(scope, receive, send)

    async def _challenge(self, send: Send, needed: list[str]) -> None:
        www = (
            f'Bearer error="insufficient_scope", scope="{" ".join(needed)}", '
            f'resource_metadata="{self.resource_metadata_url}"'
        )
        body = b'{"error":"insufficient_scope"}'
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", www.encode()),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

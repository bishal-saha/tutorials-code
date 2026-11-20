"""Run Helpline over Streamable HTTP as an OAuth resource server.

    HELPLINE_DEV=1 uv run python main.py   # dev: trusts the local test issuer
    uv run python issue_token.py       # in another terminal: mint a token for it

In production set HELPLINE_ISSUER, HELPLINE_JWKS_URI and HELPLINE_RESOURCE_URL to
your authorization server and the server's public https URL.
"""

import os
from pathlib import Path

import uvicorn
from helpline.auth import JwtTokenVerifier
from helpline.issuer import TestIssuer
from helpline.server import build_server, http_app

HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "8000"))
RESOURCE_URL = os.environ.get("HELPLINE_RESOURCE_URL", f"http://127.0.0.1:{PORT}/mcp")


def make_app():
    if os.environ.get("HELPLINE_JWKS_URI"):
        issuer = os.environ["HELPLINE_ISSUER"]
        verifier = JwtTokenVerifier(
            issuer=issuer, audience=RESOURCE_URL, jwks_uri=os.environ["HELPLINE_JWKS_URI"]
        )
    elif os.environ.get("HELPLINE_DEV") == "1":
        dev = TestIssuer.load_or_create(HERE / ".dev-issuer.pem")
        issuer = dev.issuer
        verifier = JwtTokenVerifier(issuer=issuer, audience=RESOURCE_URL, jwks=dev.jwks())
    else:
        # Fail closed: never fall back to a key we generated ourselves.
        raise SystemExit(
            "Set HELPLINE_ISSUER and HELPLINE_JWKS_URI for a real authorization server, "
            "or HELPLINE_DEV=1 to trust the local test issuer."
        )
    server = build_server(token_verifier=verifier, issuer_url=issuer, resource_url=RESOURCE_URL)
    return http_app(server, RESOURCE_URL)


if __name__ == "__main__":
    uvicorn.run(make_app(), host="127.0.0.1", port=PORT)

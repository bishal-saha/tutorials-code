"""A local test issuer: an RSA key pair, its JWKS, and a function that mints tokens.

It stands in for your real authorization server (Auth0, Entra ID, Keycloak,
Okta...) so the server's token checks can be exercised without one. It never
runs in production: the server only ever sees its public keys.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

TEST_ISSUER = "https://auth.helpline.test"


@dataclass
class TestIssuer:
    __test__ = False  # not a pytest test class

    issuer: str = TEST_ISSUER
    kid: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    _key: rsa.RSAPrivateKey = field(
        default_factory=lambda: rsa.generate_private_key(public_exponent=65537, key_size=2048)
    )

    @classmethod
    def load_or_create(cls, path: Path) -> TestIssuer:
        """Keep the dev key on disk so main.py and issue_token.py share it."""
        if path.exists():
            key = serialization.load_pem_private_key(path.read_bytes(), password=None)
            assert isinstance(key, rsa.RSAPrivateKey)
            return cls(kid="dev", _key=key)
        issuer = cls(kid="dev")
        pem = issuer._key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        path.write_bytes(pem)
        path.chmod(0o600)
        return issuer

    def jwks(self) -> dict:
        """The public half, as the issuer would publish it at its jwks_uri."""
        public = json.loads(RSAAlgorithm.to_jwk(self._key.public_key()))
        return {"keys": [public | {"kid": self.kid, "use": "sig", "alg": "RS256"}]}

    def mint(
        self,
        *,
        subject: str = "agent-maria",
        audience: str,
        scopes: list[str],
        client_id: str = "claude-code",
        ttl_seconds: int = 300,
        issuer: str | None = None,
        **extra: object,
    ) -> str:
        """An RFC 9068-style JWT access token."""
        now = int(time.time())
        claims = {
            "iss": issuer or self.issuer,
            "sub": subject,
            "aud": audience,
            "client_id": client_id,
            "scope": " ".join(scopes),
            "iat": now,
            "exp": now + ttl_seconds,
            "jti": uuid.uuid4().hex,
        } | extra
        return jwt.encode(
            claims, self._key, algorithm="RS256", headers={"kid": self.kid, "typ": "at+jwt"}
        )

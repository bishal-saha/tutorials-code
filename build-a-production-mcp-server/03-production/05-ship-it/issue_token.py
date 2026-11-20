"""Mint a dev access token that `main.py` (dev mode) accepts.

uv run python issue_token.py                                # tickets:read, all customers
uv run python issue_token.py tickets:read tickets:escalate  # can escalate too
HELPLINE_CUSTOMERS=corvid,acme uv run python issue_token.py # only these customers' tickets
"""

import os
import sys

from helpline.issuer import TestIssuer
from main import DEV_KEY, RESOURCE_URL

if __name__ == "__main__":
    scopes = sys.argv[1:] or ["tickets:read"]
    issuer = TestIssuer.load_or_create(DEV_KEY)
    customers = os.environ.get("HELPLINE_CUSTOMERS", "*").split(",")
    print(
        issuer.mint(
            audience=RESOURCE_URL,
            scopes=scopes,
            ttl_seconds=3600,
            helpline_customers=customers,
        )
    )

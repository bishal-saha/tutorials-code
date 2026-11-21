"""The downstream ticketing API, called over HTTP with the MCP server's own credential.

The token a client sends to Helpline was issued for Helpline (its audience is
this server). Forwarding it to another API is token passthrough, which the MCP
authorization spec forbids. Instead, Helpline authenticates downstream as
itself and names the acting user so the ticketing system can record who asked.

The ticketing service here is a fake behind httpx2.MockTransport: requests are
real HTTP requests that never leave the process, and `requests` keeps every one
exactly as sent, headers included, so tests can inspect what went over the wire.
"""

from __future__ import annotations

import json
import os

import httpx2

from helpline.store import HelplineStore

TICKETING_URL = "https://tickets.helpline.test"


class TicketingAPI:
    def __init__(self, store: HelplineStore, service_token: str | None = None) -> None:
        self.store = store
        self.service_token = service_token or os.environ.get(
            "HELPLINE_SERVICE_TOKEN", "svc-dev-only"
        )
        self.requests: list[httpx2.Request] = []
        self.http = httpx2.Client(
            base_url=TICKETING_URL, transport=httpx2.MockTransport(self._fake_service)
        )

    def _headers(self, acting_user: str | None) -> dict[str, str]:
        # Helpline's own credential, and who asked, as data. Never the caller's token.
        return {
            "Authorization": f"Bearer {self.service_token}",
            "X-Acting-User": acting_user or "local",
        }

    def escalate(self, ticket_id: str, severity: str, reason: str, acting_user: str | None):
        response = self.http.post(
            f"/tickets/{ticket_id}/escalations",
            json={"severity": severity, "reason": reason},
            headers=self._headers(acting_user),
        )
        response.raise_for_status()
        return response.json()

    def save_draft(self, ticket_id: str, body: str, acting_user: str | None) -> int:
        response = self.http.post(
            f"/tickets/{ticket_id}/drafts", json={"body": body}, headers=self._headers(acting_user)
        )
        response.raise_for_status()
        return response.json()["id"]

    # --- the fake ticketing service ------------------------------------------

    def _fake_service(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if request.headers.get("authorization") != f"Bearer {self.service_token}":
            return httpx2.Response(401)
        _, _, ticket_id, kind = request.url.path.split("/")
        data = json.loads(request.content)
        if kind == "escalations":
            row = self.store.escalate(ticket_id, data["severity"], data["reason"])
            return httpx2.Response(201, json=dict(row))
        return httpx2.Response(201, json={"id": self.store.save_draft(ticket_id, data["body"])})

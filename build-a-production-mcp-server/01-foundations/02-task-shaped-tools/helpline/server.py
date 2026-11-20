"""The Helpline MCP server, lesson 2: task-shaped tools.

Five tools, each shaped around a job a support agent does, not around a REST
endpoint. Inputs are typed and bounded, outputs have schemas, and failures the
model can fix come back as tool errors with a hint.
"""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from helpline.store import HelplineStore

Status = Literal["open", "pending", "solved"]

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)


# --- output models: these become each tool's outputSchema ------------------


class TicketSummary(BaseModel):
    id: str = Field(description="Ticket id, e.g. HL-1003")
    subject: str
    customer: str = Field(description="Customer company name")
    status: Status
    priority: Literal["low", "normal", "high", "urgent"]
    created_at: str


class TicketSearch(BaseModel):
    tickets: list[TicketSummary]
    total: int = Field(description="How many tickets matched, before the limit")


class Message(BaseModel):
    author: Literal["customer", "agent"]
    at: str
    body: str


class TicketDetail(TicketSummary):
    plan: str = Field(description="The customer's plan: starter, team or enterprise")
    messages: list[Message]


class ArticleHit(BaseModel):
    id: str
    title: str
    snippet: str = Field(description="The first sentence of the article")


class ArticleSearch(BaseModel):
    articles: list[ArticleHit]


class Draft(BaseModel):
    draft_id: int
    ticket_id: str
    body: str
    sent: Literal[False] = Field(
        default=False, description="Always false: a person reviews and sends drafts"
    )


class Escalation(BaseModel):
    escalation_id: int
    ticket_id: str
    severity: Literal["high", "urgent"]
    reason: str
    already_escalated: bool = Field(
        description="True when the ticket was escalated before and nothing new was created"
    )


def _summary(row) -> TicketSummary:
    return TicketSummary(
        id=row["id"],
        subject=row["subject"],
        customer=row["customer_name"],
        status=row["status"],
        priority=row["priority"],
        created_at=row["created_at"],
    )


def build_server(store: HelplineStore | None = None) -> MCPServer:
    store = store or HelplineStore()
    server = MCPServer(
        "helpline",
        version="0.2.0",
        instructions=(
            "Tools for Helpline's support desk. Find a ticket before acting on it; "
            "drafts are never sent automatically."
        ),
    )

    def require_ticket(ticket_id: str):
        row = store.ticket(ticket_id)
        if row is None:
            raise ToolError(
                f"No ticket with id {ticket_id!r}. Ticket ids look like HL-1003; "
                "use search_tickets to look one up."
            )
        return row

    @server.tool(title="Find support tickets", annotations=READ_ONLY)
    def search_tickets(
        query: Annotated[
            str, Field(description="Words to match in the subject or messages; empty for all")
        ] = "",
        status: Status | None = None,
        customer: Annotated[
            str | None, Field(description="Customer id or company name, e.g. 'Corvid Analytics'")
        ] = None,
        limit: Annotated[int, Field(ge=1, le=20)] = 10,
    ) -> TicketSearch:
        """Find tickets by words, status or customer, newest first.

        Use this to get a ticket id before calling get_ticket, draft_reply or escalate_ticket.
        """
        rows = store.search_tickets(query, status, customer)
        return TicketSearch(tickets=[_summary(r) for r in rows[:limit]], total=len(rows))

    @server.tool(title="Read a ticket", annotations=READ_ONLY)
    def get_ticket(
        ticket_id: Annotated[str, Field(description="Ticket id, e.g. HL-1003")],
    ) -> TicketDetail:
        """Read one ticket with its full message history and the customer's plan."""
        row = require_ticket(ticket_id)
        messages = [
            Message(author=m["author"], at=m["at"], body=m["body"])
            for m in store.messages(row["id"])
        ]
        return TicketDetail(**_summary(row).model_dump(), plan=row["plan"], messages=messages)

    @server.tool(title="Search the knowledge base", annotations=READ_ONLY)
    def search_knowledge_base(
        query: Annotated[str, Field(min_length=3, description="What the customer is asking")],
        limit: Annotated[int, Field(ge=1, le=5)] = 3,
    ) -> ArticleSearch:
        """Find knowledge-base articles that answer a customer's question, best match first."""
        hits = [
            ArticleHit(id=row["id"], title=row["title"], snippet=row["body"].split(". ")[0] + ".")
            for _, row in store.search_articles(query)[:limit]
        ]
        return ArticleSearch(articles=hits)

    @server.tool(
        title="Draft a reply",
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
        ),
    )
    def draft_reply(
        ticket_id: Annotated[str, Field(description="Ticket id, e.g. HL-1003")],
        message: Annotated[
            str, Field(min_length=1, max_length=2000, description="The reply text to the customer")
        ],
        article_ids: Annotated[
            list[str], Field(max_length=3, description="Articles to link, e.g. KB-103")
        ] = [],  # noqa: B006 - the SDK builds the schema from this default; it is never mutated
    ) -> Draft:
        """Save a draft reply on a ticket for a person to review. It is never sent."""
        row = require_ticket(ticket_id)
        links = []
        for article_id in article_ids:
            article = store.article(article_id)
            if article is None:
                raise ToolError(
                    f"No article {article_id!r}. Use search_knowledge_base to find ids."
                )
            links.append(f"- {article['title']} ({article['id']})")
        body = message.strip()
        if links:
            body += "\n\nThese articles may help:\n" + "\n".join(links)
        draft_id = store.save_draft(row["id"], body)
        return Draft(draft_id=draft_id, ticket_id=row["id"], body=body)

    @server.tool(
        title="Escalate a ticket",
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
        ),
    )
    def escalate_ticket(
        ticket_id: Annotated[str, Field(description="Ticket id, e.g. HL-1003")],
        severity: Literal["high", "urgent"],
        reason: Annotated[str, Field(min_length=10, max_length=500)],
    ) -> Escalation:
        """Escalate a ticket to the on-call engineer. Calling it again for the same ticket
        returns the existing escalation instead of paging twice."""
        row = require_ticket(ticket_id)
        if row["status"] == "solved":
            raise ToolError(f"{row['id']} is solved; reopen it before escalating.")
        existing = store.open_escalation(row["id"])
        if existing is not None:
            return Escalation(
                escalation_id=existing["id"],
                ticket_id=row["id"],
                severity=existing["severity"],
                reason=existing["reason"],
                already_escalated=True,
            )
        created = store.escalate(row["id"], severity, reason)
        return Escalation(
            escalation_id=created["id"],
            ticket_id=row["id"],
            severity=severity,
            reason=reason,
            already_escalated=False,
        )

    return server

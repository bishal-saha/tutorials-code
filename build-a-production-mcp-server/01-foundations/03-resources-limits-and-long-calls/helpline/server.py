"""The Helpline MCP server, lesson 3: resources, limits and long calls.

Adds to lesson 2:
- resource templates for tickets and knowledge-base articles,
- cursor pagination on search_tickets,
- an output budget on get_ticket with truncation the model can see,
- a timeout, progress and cancellation on the slow knowledge-base search.
"""

from __future__ import annotations

from typing import Annotated, Literal

import anyio
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from helpline.limits import BadCursor, decode_cursor, newest_within_budget, page
from helpline.store import HelplineStore

Status = Literal["open", "pending", "solved"]

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

# The knowledge-base search calls a slow service; give up rather than hang the agent.
KB_TIMEOUT_SECONDS = 2.0


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
    total: int = Field(description="How many tickets matched in all")
    next_cursor: str | None = Field(
        description="Pass as `cursor` to get the next page; null on the last page"
    )


class Message(BaseModel):
    author: Literal["customer", "agent"]
    at: str
    body: str


class TicketDetail(TicketSummary):
    plan: str = Field(description="The customer's plan: starter, team or enterprise")
    messages: list[Message] = Field(description="The newest messages that fit, oldest first")
    omitted_messages: int = Field(description="Older messages left out to stay within budget")
    full_history: str = Field(description="Resource URI with every message")


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


def build_server(
    store: HelplineStore | None = None,
    kb_delay_seconds: float = 0.05,
    kb_timeout_seconds: float = KB_TIMEOUT_SECONDS,
) -> MCPServer:
    """Build the server. `kb_delay_seconds` simulates the knowledge-base service's latency."""
    store = store or HelplineStore()
    server = MCPServer(
        "helpline",
        version="0.3.0",
        instructions=(
            "Tools for Helpline's support desk. Find a ticket before acting on it; "
            "drafts are never sent automatically. Results are paged and budgeted: "
            "follow next_cursor for more tickets and read full_history for a long ticket."
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

    # --- resources: things a host or user can attach as context -------------

    @server.resource(
        "helpline://tickets/{ticket_id}",
        title="Ticket with full history",
        mime_type="text/markdown",
    )
    def ticket_resource(ticket_id: str) -> str:
        row = store.ticket(ticket_id)
        if row is None:
            raise ResourceNotFoundError(f"No ticket {ticket_id!r}")
        lines = [f"# {row['id']}: {row['subject']}", ""]
        lines.append(f"Customer: {row['customer_name']} ({row['plan']}) · Status: {row['status']}")
        for m in store.messages(row["id"]):
            lines += ["", f"## {m['author']} · {m['at']}", "", m["body"]]
        return "\n".join(lines)

    @server.resource(
        "helpline://kb/{article_id}", title="Knowledge-base article", mime_type="text/markdown"
    )
    def article_resource(article_id: str) -> str:
        row = store.article(article_id)
        if row is None:
            raise ResourceNotFoundError(f"No article {article_id!r}")
        return f"# {row['title']}\n\n{row['body']}"

    # --- tools ---------------------------------------------------------------

    @server.tool(title="Search support tickets", annotations=READ_ONLY)
    def search_tickets(
        query: Annotated[
            str, Field(description="Words to match in the subject or messages; empty for all")
        ] = "",
        status: Status | None = None,
        customer: Annotated[
            str | None, Field(description="Customer id or company name, e.g. 'Corvid Analytics'")
        ] = None,
        limit: Annotated[int, Field(ge=1, le=10)] = 5,
        cursor: Annotated[
            str | None, Field(description="next_cursor from the previous page, unchanged")
        ] = None,
    ) -> TicketSearch:
        """Search tickets by words, status or customer, newest first, one page at a time.

        Use this to get a ticket id before calling get_ticket, draft_reply or escalate_ticket.
        """
        filters = {"query": query, "status": status, "customer": customer, "limit": limit}
        offset = 0
        if cursor:
            try:
                offset = decode_cursor(cursor, filters)
            except BadCursor as exc:
                raise ToolError(
                    f"{exc}. Repeat the search with the same filters and no cursor."
                ) from exc
        rows = store.search_tickets(query, status, customer)
        chunk, next_cursor = page(rows, offset, limit, filters)
        return TicketSearch(
            tickets=[_summary(r) for r in chunk], total=len(rows), next_cursor=next_cursor
        )

    @server.tool(title="Read a ticket", annotations=READ_ONLY)
    def get_ticket(
        ticket_id: Annotated[str, Field(description="Ticket id, e.g. HL-1003")],
    ) -> TicketDetail:
        """Read a ticket: its newest messages within the output budget, and the customer's plan.

        When omitted_messages is above zero, older messages were left out; they are in
        the full_history resource.
        """
        row = require_ticket(ticket_id)
        rows = store.messages(row["id"])
        kept = newest_within_budget([m["body"] for m in rows])
        messages = [Message(author=m["author"], at=m["at"], body=m["body"]) for m in rows[-kept:]]
        return TicketDetail(
            **_summary(row).model_dump(),
            plan=row["plan"],
            messages=messages,
            omitted_messages=len(rows) - kept,
            full_history=f"helpline://tickets/{row['id']}",
        )

    @server.tool(title="Search the knowledge base", annotations=READ_ONLY)
    async def search_knowledge_base(
        query: Annotated[str, Field(min_length=3, description="What the customer is asking")],
        ctx: Context,
        limit: Annotated[int, Field(ge=1, le=5)] = 3,
    ) -> ArticleSearch:
        """Find knowledge-base articles that answer a customer's question, best match first.

        It can take a few seconds; it reports progress and gives up after a timeout.
        """
        candidates = store.search_articles(query)
        scanned = []
        try:
            with anyio.fail_after(kb_timeout_seconds):
                for i, (_, row) in enumerate(candidates, start=1):
                    await anyio.sleep(kb_delay_seconds)  # one call to the slow service
                    scanned.append(row)
                    await ctx.report_progress(i, len(candidates), f"checked {row['id']}")
        except TimeoutError:
            raise ToolError(
                f"The knowledge base did not answer within {kb_timeout_seconds:g}s "
                f"({len(scanned)} of {len(candidates)} articles checked). "
                "Try a narrower query."
            ) from None
        except anyio.get_cancelled_exc_class():
            store.cancelled_searches += 1  # the client gave up; stop work and record it
            raise
        hits = [
            ArticleHit(id=row["id"], title=row["title"], snippet=row["body"].split(". ")[0] + ".")
            for row in scanned[:limit]
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

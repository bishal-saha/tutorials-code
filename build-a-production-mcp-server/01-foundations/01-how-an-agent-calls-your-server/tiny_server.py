"""A deliberately tiny Helpline server for lesson 1: one ticket, three tools.

It exists so wire.py has something real to talk to. Lesson 2 builds the proper
server.
"""

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

TICKETS = {
    "HL-1003": "Webhook deliveries failing with 401 since key rotation",
}

server = MCPServer("helpline-tiny", version="0.1.0")


@server.tool()
def get_ticket(ticket_id: str) -> str:
    """Return a ticket's subject by id, e.g. HL-1003."""
    subject = TICKETS.get(ticket_id.upper())
    if subject is None:
        # An error the model can act on: it comes back as a tool result.
        raise ToolError(f"No ticket {ticket_id!r}. Ticket ids look like HL-1003.")
    return f"{ticket_id.upper()}: {subject}"


@server.tool()
def ticket_count() -> int:
    """How many tickets the desk holds."""
    return len(TICKETS)


@server.tool()
def broken_report() -> str:
    """A tool with a bug, to show what a crash looks like to the model."""
    raise RuntimeError("connection to db-primary.internal:5432 refused")


if __name__ == "__main__":
    server.run("stdio")

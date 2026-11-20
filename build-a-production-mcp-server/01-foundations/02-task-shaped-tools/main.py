"""Run the Helpline MCP server over stdio.

An MCP client (Claude Code, Claude Desktop, MCP Inspector) starts this file as a
subprocess and speaks JSON-RPC over its stdin and stdout, so nothing else may
print to stdout.
"""

from helpline.server import build_server

if __name__ == "__main__":
    build_server().run("stdio")

"""Run Helpline over stdio, for hosts that launch the server as a subprocess.

On stdio there is no token: the user who starts the process is the caller, so
scopes do not apply. Only give it to hosts running as someone allowed to escalate.
"""

import logging
import sys

from helpline.server import build_server

if __name__ == "__main__":
    # stdout carries JSON-RPC; logs (including audit records) go to stderr.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(message)s")
    build_server().run("stdio")

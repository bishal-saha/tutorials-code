"""Helpline's data: an in-memory SQLite database loaded from data/helpline.json.

This stands in for the real system the MCP server fronts (a ticketing product's
database or REST API). The server only talks to it through this class.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "helpline.json"

SCHEMA = """
CREATE TABLE customers (id TEXT PRIMARY KEY, name TEXT NOT NULL, plan TEXT NOT NULL);
CREATE TABLE tickets (
  id TEXT PRIMARY KEY, customer TEXT NOT NULL REFERENCES customers(id),
  status TEXT NOT NULL, priority TEXT NOT NULL, subject TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE messages (
  ticket_id TEXT NOT NULL REFERENCES tickets(id), seq INTEGER NOT NULL,
  author TEXT NOT NULL, at TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY (ticket_id, seq)
);
CREATE TABLE articles (id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT NOT NULL REFERENCES tickets(id),
  body TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE escalations (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT NOT NULL REFERENCES tickets(id),
  severity TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


class HelplineStore:
    def __init__(self, data_file: Path = DATA_FILE) -> None:
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        data = json.loads(data_file.read_text())
        self.db.executemany("INSERT INTO customers VALUES (:id, :name, :plan)", data["customers"])
        for t in data["tickets"]:
            self.db.execute(
                "INSERT INTO tickets VALUES (:id, :customer, :status, :priority, :subject, "
                ":created_at)",
                t,
            )
            for seq, m in enumerate(t["messages"], start=1):
                self.db.execute(
                    "INSERT INTO messages VALUES (?, ?, ?, ?, ?)",
                    (t["id"], seq, m["author"], m["at"], m["body"]),
                )
        self.db.executemany("INSERT INTO articles VALUES (:id, :title, :body)", data["articles"])
        self.db.commit()

    # --- reads -------------------------------------------------------------

    def search_tickets(
        self, query: str = "", status: str | None = None, customer: str | None = None
    ) -> list[sqlite3.Row]:
        """Tickets matching every word of `query` in the subject or messages, newest first."""
        sql = (
            "SELECT t.*, c.name AS customer_name FROM tickets t "
            "JOIN customers c ON c.id = t.customer WHERE 1=1"
        )
        args: list[str] = []
        if status:
            sql += " AND t.status = ?"
            args.append(status)
        if customer:
            sql += " AND (t.customer = ? OR lower(c.name) = lower(?))"
            args += [customer, customer]
        for word in _words(query):
            sql += (
                " AND (lower(t.subject) LIKE ? OR EXISTS (SELECT 1 FROM messages m "
                "WHERE m.ticket_id = t.id AND lower(m.body) LIKE ?))"
            )
            args += [f"%{word}%", f"%{word}%"]
        sql += " ORDER BY t.created_at DESC"
        return self.db.execute(sql, args).fetchall()

    def ticket(self, ticket_id: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT t.*, c.name AS customer_name, c.plan FROM tickets t "
            "JOIN customers c ON c.id = t.customer WHERE t.id = ?",
            (ticket_id.strip().upper(),),
        ).fetchone()

    def messages(self, ticket_id: str) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM messages WHERE ticket_id = ? ORDER BY seq", (ticket_id,)
        ).fetchall()

    def search_articles(self, query: str) -> list[tuple[int, sqlite3.Row]]:
        """Articles scored by how many query words they contain, best first."""
        wanted = _words(query)
        scored = []
        for row in self.db.execute("SELECT * FROM articles ORDER BY id"):
            score = len(wanted & _words(row["title"] + " " + row["body"]))
            if score:
                scored.append((score, row))
        scored.sort(key=lambda pair: -pair[0])
        return scored

    def article(self, article_id: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM articles WHERE id = ?", (article_id.strip().upper(),)
        ).fetchone()

    def open_escalation(self, ticket_id: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM escalations WHERE ticket_id = ? ORDER BY id DESC LIMIT 1", (ticket_id,)
        ).fetchone()

    # --- writes ------------------------------------------------------------

    def save_draft(self, ticket_id: str, body: str) -> int:
        cur = self.db.execute(
            "INSERT INTO drafts (ticket_id, body, created_at) VALUES (?, ?, ?)",
            (ticket_id, body, _now()),
        )
        self.db.commit()
        return int(cur.lastrowid)

    def escalate(self, ticket_id: str, severity: str, reason: str) -> sqlite3.Row:
        self.db.execute(
            "INSERT INTO escalations (ticket_id, severity, reason, created_at) VALUES (?, ?, ?, ?)",
            (ticket_id, severity, reason, _now()),
        )
        self.db.commit()
        row = self.open_escalation(ticket_id)
        assert row is not None
        return row

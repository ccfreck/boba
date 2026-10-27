"""Durable pre-execution audit, then completion update; no payload columns."""

import json
from pathlib import Path
import sqlite3

from boba.events.models import SecurityEvent


class EventStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        with sqlite3.connect(path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL,
                agent_id TEXT NOT NULL, server TEXT NOT NULL, tool TEXT NOT NULL,
                decision TEXT NOT NULL, severity TEXT NOT NULL, rule_ids TEXT NOT NULL,
                alerts TEXT NOT NULL, reason TEXT NOT NULL, duration_ms REAL NOT NULL,
                outcome TEXT NOT NULL)""")

    def save(self, event: SecurityEvent) -> None:
        row = event.model_dump()
        for field in ("rule_ids", "alerts"):
            row[field] = json.dumps(row[field])
        columns = list(row)
        with sqlite3.connect(self.path, timeout=2) as db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute(f"INSERT OR REPLACE INTO events ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", list(row.values()))

    def all(self) -> list[dict]:
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute("SELECT * FROM events ORDER BY timestamp DESC")]

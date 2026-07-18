"""SQLite run history + corrections ledger (Tier-2 persistence)."""
from __future__ import annotations
import json
import sqlite3
import time
from contextlib import contextmanager

from backend.config import RUNS_DB


def init_db():
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            ticket_title TEXT,
            ticket_body TEXT,
            memory_on INTEGER,
            created REAL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            cost_usd REAL,
            result_json TEXT
        );
        CREATE TABLE IF NOT EXISTS corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            entity TEXT,
            namespace TEXT,
            reason TEXT,
            created REAL
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            seq INTEGER,
            payload TEXT
        );
        """)


@contextmanager
def _conn():
    conn = sqlite3.connect(RUNS_DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_run(run: dict):
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?)",
            (run["run_id"], run["ticket"]["title"], run["ticket"]["body"],
             int(run["memory_on"]), time.time(),
             run["usage"]["prompt_tokens"], run["usage"]["completion_tokens"],
             run["usage"]["cost_usd"], json.dumps(run, default=str)),
        )


def save_event(run_id: str, seq: int, payload: dict):
    with _conn() as c:
        c.execute("INSERT INTO events (run_id, seq, payload) VALUES (?,?,?)",
                  (run_id, seq, json.dumps(payload, default=str)))


def add_correction(run_id: str, entity: str, namespace: str, reason: str):
    with _conn() as c:
        c.execute(
            "INSERT INTO corrections (run_id, entity, namespace, reason, created) VALUES (?,?,?,?,?)",
            (run_id, entity, namespace, reason, time.time()))


def list_corrections() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM corrections ORDER BY created DESC").fetchall()
        return [dict(r) for r in rows]


def list_runs(limit: int = 50) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT run_id, ticket_title, memory_on, created, prompt_tokens, "
            "completion_tokens, cost_usd FROM runs ORDER BY created DESC LIMIT ?",
            (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_run(run_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT result_json FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(row["result_json"]) if row else None

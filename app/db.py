"""SQLite index of processed papers -- just enough for the history list.

The actual reading content (normalized text, glossary, figures) lives in
data/papers/<id>/content.json, not in the database.
"""

from __future__ import annotations

import sqlite3

from app.storage import DATA_DIR

DB_PATH = DATA_DIR / "daily-read.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    word_count INTEGER NOT NULL,
    est_minutes INTEGER NOT NULL,
    status TEXT NOT NULL
)
"""


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    return conn


def insert_paper(
    conn: sqlite3.Connection,
    *,
    paper_id: str,
    title: str,
    source: str,
    created_at: str,
    word_count: int,
    est_minutes: int,
    status: str = "done",
) -> None:
    conn.execute(
        "INSERT INTO papers (id, title, source, created_at, word_count, est_minutes, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (paper_id, title, source, created_at, word_count, est_minutes, status),
    )
    conn.commit()


def list_papers(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM papers ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def get_paper(conn: sqlite3.Connection, paper_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    return dict(row) if row else None

"""SQLite index of processed papers -- just enough for the history list.

The actual reading content (normalized text, glossary, figures) lives in
data/papers/<id>/content.json, not in the database.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from app.glossary.base import normalize_term_key
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
);

CREATE TABLE IF NOT EXISTS known_terms (
    term_key TEXT PRIMARY KEY,
    display_term TEXT NOT NULL,
    marked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL,
    quote TEXT NOT NULL,
    prefix TEXT NOT NULL DEFAULT '',
    suffix TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_annotations_paper_id ON annotations(paper_id)
"""


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)  # executescript, not execute: _SCHEMA is 2 statements
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Small idempotent migrations for columns added after the table
    already existed on disk -- there's no migration framework here, this
    is the "just enough" equivalent for a single local SQLite file
    (plan/05-f: papers.error_message, for the processing/done/error state
    machine)."""
    try:
        conn.execute("ALTER TABLE papers ADD COLUMN error_message TEXT")
    except sqlite3.OperationalError:
        pass  # already migrated
    try:
        # plan/07-troubleshooting-backlog.md#b-3: sha256 of the raw PDF
        # bytes, so a re-uploaded duplicate can be detected before paying
        # for another GROBID call.
        conn.execute("ALTER TABLE papers ADD COLUMN pdf_hash TEXT")
    except sqlite3.OperationalError:
        pass  # already migrated


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
    pdf_hash: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO papers (id, title, source, created_at, word_count, est_minutes, status, pdf_hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (paper_id, title, source, created_at, word_count, est_minutes, status, pdf_hash),
    )
    conn.commit()


def set_pdf_hash(conn: sqlite3.Connection, paper_id: str, pdf_hash: str) -> None:
    """Backfilled once a URL submission's bytes are actually known (plan/07-
    troubleshooting-backlog.md#b-3) -- unlike a file upload, a URL's bytes
    aren't available until resolve_url() runs in the background thread, so
    they can't be hashed at insert_paper() time the way an upload's can."""
    conn.execute("UPDATE papers SET pdf_hash = ? WHERE id = ?", (pdf_hash, paper_id))
    conn.commit()


def find_paper_by_hash(conn: sqlite3.Connection, pdf_hash: str) -> dict | None:
    """The most recent non-error paper with this exact PDF content, if any.
    Excludes status='error': a failed paper's hash must not block a retry
    of the very same file from being redirected back to the failure."""
    row = conn.execute(
        "SELECT * FROM papers WHERE pdf_hash = ? AND status != 'error' ORDER BY created_at DESC LIMIT 1",
        (pdf_hash,),
    ).fetchone()
    return dict(row) if row else None


def mark_paper_done(conn: sqlite3.Connection, paper_id: str, *, title: str, word_count: int, est_minutes: int) -> None:
    """Transition a paper from status="processing" to "done" once
    pipeline.py's background thread finishes (plan/05-f)."""
    conn.execute(
        "UPDATE papers SET status = 'done', title = ?, word_count = ?, est_minutes = ? WHERE id = ?",
        (title, word_count, est_minutes, paper_id),
    )
    conn.commit()


def mark_paper_error(conn: sqlite3.Connection, paper_id: str, error_message: str) -> None:
    """Transition a paper to status="error" (plan/05-f). Must always be
    reachable from the background thread's exception handler: an uncaught
    exception in a plain threading.Thread is silently swallowed, so without
    this the row would sit at "processing" forever with the UI spinning."""
    conn.execute(
        "UPDATE papers SET status = 'error', error_message = ? WHERE id = ?",
        (error_message, paper_id),
    )
    conn.commit()


def list_papers(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM papers ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def get_paper(conn: sqlite3.Connection, paper_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    return dict(row) if row else None


def mark_term_known(conn: sqlite3.Connection, term: str) -> None:
    """Record that the reader already knows `term`, persisted across every
    paper from now on (plan/04-b) -- keyed by normalize_term_key so case and
    singular/plural variants (see plan/04-f) are treated as the same term."""
    conn.execute(
        "INSERT INTO known_terms (term_key, display_term, marked_at) VALUES (?, ?, ?) "
        "ON CONFLICT(term_key) DO UPDATE SET display_term = excluded.display_term, "
        "marked_at = excluded.marked_at",
        (normalize_term_key(term), term, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def known_term_keys(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT term_key FROM known_terms").fetchall()
    return {row["term_key"] for row in rows}


def create_annotation(
    conn: sqlite3.Connection, *, paper_id: str, quote: str, prefix: str, suffix: str, note: str
) -> dict:
    """Personal margin note anchored to a quoted substring (plan/05-g).
    Lives entirely in SQLite, never in content.json, so reprocessing a
    paper (which can change unit text/wording) never destroys a note --
    see rendering.match_annotations for how a saved quote is re-found
    against whatever units currently exist."""
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO annotations (paper_id, quote, prefix, suffix, note, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (paper_id, quote, prefix, suffix, note, now, now),
    )
    conn.commit()
    return get_annotation(conn, cursor.lastrowid)


def get_annotation(conn: sqlite3.Connection, annotation_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM annotations WHERE id = ?", (annotation_id,)).fetchone()
    return dict(row) if row else None


def list_annotations(conn: sqlite3.Connection, paper_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM annotations WHERE paper_id = ? ORDER BY created_at ASC", (paper_id,)
    ).fetchall()
    return [dict(row) for row in rows]


def update_annotation_note(conn: sqlite3.Connection, annotation_id: int, paper_id: str, note: str) -> dict | None:
    """Scoped by (id, paper_id) together, not just id, so a URL for the
    wrong paper can't touch someone else's note (defense in depth even
    though this is a single-user local app). Returns None (not another
    paper's row) when the (id, paper_id) pair doesn't match anything."""
    cursor = conn.execute(
        "UPDATE annotations SET note = ?, updated_at = ? WHERE id = ? AND paper_id = ?",
        (note, datetime.now(timezone.utc).isoformat(), annotation_id, paper_id),
    )
    conn.commit()
    if cursor.rowcount == 0:
        return None
    return get_annotation(conn, annotation_id)


def delete_annotation(conn: sqlite3.Connection, annotation_id: int, paper_id: str) -> bool:
    cursor = conn.execute("DELETE FROM annotations WHERE id = ? AND paper_id = ?", (annotation_id, paper_id))
    conn.commit()
    return cursor.rowcount > 0

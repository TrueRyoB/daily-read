from __future__ import annotations

from app import db


def test_create_interpretation_returns_hydrated_row(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.insert_paper(
            conn, paper_id="p1", title="Paper One", source="s.pdf",
            created_at="2026-07-01T00:00:00+00:00", word_count=1, est_minutes=1,
        )
        row = db.create_interpretation(
            conn, date="2026-07-15", memo="a thought", paper_ids=["p1"], links=["https://a.example"]
        )
        assert row["date"] == "2026-07-15"
        assert row["memo"] == "a thought"
        assert row["papers"] == [{"id": "p1", "title": "Paper One"}]
        assert row["links"] == ["https://a.example"]
        assert row["created_at"] == row["updated_at"]
    finally:
        conn.close()


def test_create_interpretation_with_no_papers_or_links(isolated_data_dir):
    conn = db.get_connection()
    try:
        row = db.create_interpretation(conn, date="2026-07-15", memo="just musing", paper_ids=[], links=[])
        assert row["papers"] == []
        assert row["links"] == []
    finally:
        conn.close()


def test_create_interpretation_with_multiple_papers_and_links(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.insert_paper(
            conn, paper_id="p1", title="First", source="s.pdf",
            created_at="2026-07-01T00:00:00+00:00", word_count=1, est_minutes=1,
        )
        db.insert_paper(
            conn, paper_id="p2", title="Second", source="s.pdf",
            created_at="2026-07-02T00:00:00+00:00", word_count=1, est_minutes=1,
        )
        row = db.create_interpretation(
            conn,
            date="2026-07-15",
            memo="connecting two papers",
            paper_ids=["p1", "p2"],
            links=["https://a.example", "https://b.example"],
        )
        assert {p["id"] for p in row["papers"]} == {"p1", "p2"}
        assert row["links"] == ["https://a.example", "https://b.example"]
    finally:
        conn.close()


def test_list_interpretations_in_month_filters_by_date_prefix(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.create_interpretation(conn, date="2026-07-15", memo="in july", paper_ids=[], links=[])
        db.create_interpretation(conn, date="2026-08-01", memo="in august", paper_ids=[], links=[])
        july_entries = db.list_interpretations_in_month(conn, 2026, 7)
        assert [e["memo"] for e in july_entries] == ["in july"]
    finally:
        conn.close()


def test_list_interpretations_in_month_orders_by_date(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.create_interpretation(conn, date="2026-07-20", memo="later", paper_ids=[], links=[])
        db.create_interpretation(conn, date="2026-07-05", memo="earlier", paper_ids=[], links=[])
        entries = db.list_interpretations_in_month(conn, 2026, 7)
        assert [e["memo"] for e in entries] == ["earlier", "later"]
    finally:
        conn.close()


def test_get_interpretation_returns_none_when_missing(isolated_data_dir):
    conn = db.get_connection()
    try:
        assert db.get_interpretation(conn, 999999) is None
    finally:
        conn.close()


def test_delete_interpretation_removes_row_and_children(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.insert_paper(
            conn, paper_id="p1", title="Paper", source="s.pdf",
            created_at="2026-07-01T00:00:00+00:00", word_count=1, est_minutes=1,
        )
        created = db.create_interpretation(
            conn, date="2026-07-15", memo="to delete", paper_ids=["p1"], links=["https://a.example"]
        )
        assert db.delete_interpretation(conn, created["id"]) is True
        assert db.get_interpretation(conn, created["id"]) is None

        # Child rows (links/paper associations) must not be left dangling.
        remaining_links = conn.execute(
            "SELECT COUNT(*) AS n FROM interpretation_links WHERE interpretation_id = ?", (created["id"],)
        ).fetchone()["n"]
        remaining_papers = conn.execute(
            "SELECT COUNT(*) AS n FROM interpretation_papers WHERE interpretation_id = ?", (created["id"],)
        ).fetchone()["n"]
        assert remaining_links == 0
        assert remaining_papers == 0
    finally:
        conn.close()


def test_delete_nonexistent_interpretation_returns_false(isolated_data_dir):
    conn = db.get_connection()
    try:
        assert db.delete_interpretation(conn, 999999) is False
    finally:
        conn.close()

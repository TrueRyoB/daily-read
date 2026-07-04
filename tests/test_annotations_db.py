from __future__ import annotations

from app import db


def test_create_annotation_returns_row_with_generated_id_and_timestamps(isolated_data_dir):
    conn = db.get_connection()
    try:
        row = db.create_annotation(conn, paper_id="p1", note="> a quote\nmy note")
        assert row["id"] is not None
        assert row["paper_id"] == "p1"
        assert row["note"] == "> a quote\nmy note"
        assert row["created_at"] == row["updated_at"]
    finally:
        conn.close()


def test_list_annotations_returns_only_that_papers_annotations_in_created_order(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.create_annotation(conn, paper_id="p1", note="first")
        db.create_annotation(conn, paper_id="p2", note="other paper")
        db.create_annotation(conn, paper_id="p1", note="second")

        p1_annotations = db.list_annotations(conn, "p1")
        assert [a["note"] for a in p1_annotations] == ["first", "second"]
    finally:
        conn.close()


def test_update_annotation_note_changes_note_and_bumps_updated_at_but_not_created_at(isolated_data_dir):
    conn = db.get_connection()
    try:
        created = db.create_annotation(conn, paper_id="p1", note="old")
        updated = db.update_annotation_note(conn, created["id"], "p1", "new note")
        assert updated["note"] == "new note"
        assert updated["created_at"] == created["created_at"]
    finally:
        conn.close()


def test_update_annotation_scoped_to_paper_returns_none_for_wrong_paper_id(isolated_data_dir):
    conn = db.get_connection()
    try:
        created = db.create_annotation(conn, paper_id="p1", note="old")
        result = db.update_annotation_note(conn, created["id"], "wrong-paper", "new note")
        assert result is None
        # and the original note is untouched
        assert db.get_annotation(conn, created["id"])["note"] == "old"
    finally:
        conn.close()


def test_delete_annotation_removes_row(isolated_data_dir):
    conn = db.get_connection()
    try:
        created = db.create_annotation(conn, paper_id="p1", note="n")
        assert db.delete_annotation(conn, created["id"], "p1") is True
        assert db.get_annotation(conn, created["id"]) is None
    finally:
        conn.close()


def test_delete_nonexistent_or_wrong_paper_annotation_returns_false(isolated_data_dir):
    conn = db.get_connection()
    try:
        created = db.create_annotation(conn, paper_id="p1", note="n")
        assert db.delete_annotation(conn, created["id"], "wrong-paper") is False
        assert db.delete_annotation(conn, 999999, "p1") is False
        assert db.get_annotation(conn, created["id"]) is not None  # untouched
    finally:
        conn.close()

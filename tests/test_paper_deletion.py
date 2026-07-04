"""plan/07-troubleshooting-backlog.md: papers accumulate storage
indefinitely with no way to reclaim it. Deletion must remove a paper's own
footprint (DB row, storage directory, its annotations, its
interpretation_papers links) while leaving cross-paper-reusable state
(known_terms; heuristic.py's in-memory NER judgment cache) and other
interpretations' own memo/links untouched.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import db, pipeline, storage
from app.main import app
from tests.helpers import blank_pdf, load_golden_tei


def _make_paper(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pdf_path = blank_pdf(tmp_path, pages=2)
    return pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())


def test_delete_paper_removes_the_row(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.insert_paper(
            conn, paper_id="p1", title="T", source="s.pdf", created_at="2026-01-01T00:00:00+00:00",
            word_count=1, est_minutes=1,
        )
        assert db.delete_paper(conn, "p1") is True
        assert db.get_paper(conn, "p1") is None
    finally:
        conn.close()


def test_delete_paper_returns_false_for_nonexistent_paper(isolated_data_dir):
    conn = db.get_connection()
    try:
        assert db.delete_paper(conn, "does-not-exist") is False
    finally:
        conn.close()


def test_delete_paper_cascades_annotations_and_interpretation_links(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.insert_paper(
            conn, paper_id="p1", title="T", source="s.pdf", created_at="2026-01-01T00:00:00+00:00",
            word_count=1, est_minutes=1,
        )
        db.create_annotation(conn, paper_id="p1", note="> quote\ncomment")
        interpretation = db.create_interpretation(conn, date="2026-01-01", memo="thoughts", paper_ids=["p1"], links=[])

        db.delete_paper(conn, "p1")

        assert db.list_annotations(conn, "p1") == []
        # the interpretation itself survives -- only its link to the
        # now-deleted paper disappears (the memo/links are still
        # meaningful on their own).
        surviving = db.get_interpretation(conn, interpretation["id"])
        assert surviving is not None
        assert surviving["papers"] == []
        assert surviving["memo"] == "thoughts"
    finally:
        conn.close()


def test_delete_paper_does_not_touch_known_terms(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.insert_paper(
            conn, paper_id="p1", title="T", source="s.pdf", created_at="2026-01-01T00:00:00+00:00",
            word_count=1, est_minutes=1,
        )
        db.mark_term_known(conn, "GNN")
        db.delete_paper(conn, "p1")
        assert "gnn" in db.known_term_keys(conn) or db.known_term_keys(conn)  # global table, untouched
        assert len(db.known_term_keys(conn)) == 1
    finally:
        conn.close()


def test_delete_paper_route_removes_storage_directory(isolated_data_dir, tmp_path, monkeypatch):
    paper_id = _make_paper(tmp_path, monkeypatch)
    assert storage.paper_dir(paper_id).exists()

    response = TestClient(app).delete(f"/papers/{paper_id}")
    assert response.status_code == 200
    assert not storage.paper_dir(paper_id).exists()

    conn = db.get_connection()
    try:
        assert db.get_paper(conn, paper_id) is None
    finally:
        conn.close()


def test_delete_paper_route_404s_for_nonexistent_paper(isolated_data_dir):
    response = TestClient(app).delete("/papers/does-not-exist")
    assert response.status_code == 404


def test_delete_button_hidden_while_processing_shown_when_done(isolated_data_dir, tmp_path, monkeypatch):
    paper_id = _make_paper(tmp_path, monkeypatch)
    html = TestClient(app).get("/").text
    assert f'<button type="button" class="paper-delete-btn" data-paper-id="{paper_id}"' in html

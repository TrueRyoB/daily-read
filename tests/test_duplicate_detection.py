"""plan/07-troubleshooting-backlog.md#b-3: re-uploading a byte-identical
PDF should redirect to the existing paper instead of paying for another
GROBID call, but must never block a retry of a paper that previously
errored out.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app import db, pipeline
from app.main import app
from tests.helpers import blank_pdf, load_golden_tei


def _wait_until_terminal(paper_id):
    # Mirrors the established pattern in test_async_processing.py: a plain
    # threading.Thread doesn't run to completion inside TestClient.post(),
    # so a test that starts one must poll it to a terminal state itself --
    # otherwise it keeps running past this test's isolated_data_dir/
    # monkeypatch teardown and can write into whatever the *next* test's
    # fixtures happen to be active at that moment.
    conn = db.get_connection()
    try:
        for _ in range(50):
            paper = db.get_paper(conn, paper_id)
            if paper["status"] != "processing":
                return paper
            time.sleep(0.05)
        return paper
    finally:
        conn.close()


def test_find_paper_by_hash_returns_none_when_no_match(isolated_data_dir):
    conn = db.get_connection()
    try:
        assert db.find_paper_by_hash(conn, "nonexistent-hash") is None
    finally:
        conn.close()


def test_find_paper_by_hash_finds_matching_done_paper(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.insert_paper(
            conn,
            paper_id="p1",
            title="T",
            source="s.pdf",
            created_at="2026-01-01T00:00:00+00:00",
            word_count=1,
            est_minutes=1,
            pdf_hash="abc123",
        )
        found = db.find_paper_by_hash(conn, "abc123")
        assert found is not None
        assert found["id"] == "p1"
    finally:
        conn.close()


def test_find_paper_by_hash_excludes_error_status(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.insert_paper(
            conn,
            paper_id="p1",
            title="T",
            source="s.pdf",
            created_at="2026-01-01T00:00:00+00:00",
            word_count=0,
            est_minutes=0,
            status="error",
            pdf_hash="abc123",
        )
        # A failed paper's hash must not block a retry of the same file.
        assert db.find_paper_by_hash(conn, "abc123") is None
    finally:
        conn.close()


def test_set_pdf_hash_backfills_hash_for_url_submitted_paper(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.insert_paper(
            conn,
            paper_id="p1",
            title="T",
            source="https://example.com/paper.pdf",
            created_at="2026-01-01T00:00:00+00:00",
            word_count=1,
            est_minutes=1,
        )
        db.set_pdf_hash(conn, "p1", "abc123")
        assert db.find_paper_by_hash(conn, "abc123")["id"] == "p1"
    finally:
        conn.close()


def test_uploading_same_pdf_twice_redirects_to_the_existing_paper(isolated_data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pdf_path = blank_pdf(tmp_path, pages=2)
    pdf_bytes = open(pdf_path, "rb").read()
    client = TestClient(app)

    first = client.post("/papers", files={"file": ("sample.pdf", pdf_bytes, "application/pdf")}, follow_redirects=False)
    assert first.status_code == 303
    first_paper_id = first.headers["location"].rsplit("/", 1)[-1]
    assert _wait_until_terminal(first_paper_id)["status"] == "done"

    second = client.post("/papers", files={"file": ("sample.pdf", pdf_bytes, "application/pdf")}, follow_redirects=False)
    assert second.status_code == 303
    second_paper_id = second.headers["location"].rsplit("/", 1)[-1]

    assert second_paper_id == first_paper_id

    conn = db.get_connection()
    try:
        assert len(db.list_papers(conn)) == 1  # no second row was ever created
    finally:
        conn.close()


def test_retrying_an_errored_upload_starts_fresh_instead_of_redirecting(isolated_data_dir, tmp_path, monkeypatch):
    def always_times_out(pdf_path):
        raise RuntimeError("GROBIDの処理が180秒以内に完了しませんでした。")

    monkeypatch.setattr(pipeline, "extract_tei", always_times_out)
    pdf_path = blank_pdf(tmp_path, pages=2)
    pdf_bytes = open(pdf_path, "rb").read()
    client = TestClient(app)

    first = client.post("/papers", files={"file": ("sample.pdf", pdf_bytes, "application/pdf")}, follow_redirects=False)
    first_paper_id = first.headers["location"].rsplit("/", 1)[-1]
    assert _wait_until_terminal(first_paper_id)["status"] == "error"

    second = client.post("/papers", files={"file": ("sample.pdf", pdf_bytes, "application/pdf")}, follow_redirects=False)
    second_paper_id = second.headers["location"].rsplit("/", 1)[-1]
    assert second_paper_id != first_paper_id  # a fresh attempt, not redirected to the failure
    _wait_until_terminal(second_paper_id)  # let this one finish (also errors) before teardown

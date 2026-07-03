"""Tests for plan/05-f: background-thread paper processing + the
processing/done/error state machine.

threading.Thread (used by pipeline.start_upload_processing/start_url_processing)
does NOT run to completion inside TestClient.post() the way FastAPI's
BackgroundTasks would -- that's exactly what makes the "processing"
intermediate state observable here via a threading.Event gate on a
monkeypatched extract_tei.
"""

from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient

from app import db, pipeline
from app.main import app
from tests.helpers import blank_pdf, load_golden_tei


def test_insert_paper_defaults_to_done(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.insert_paper(
            conn, paper_id="p1", title="T", source="s", created_at="2026-01-01T00:00:00+00:00",
            word_count=10, est_minutes=1,
        )
        assert db.get_paper(conn, "p1")["status"] == "done"
    finally:
        conn.close()


def test_mark_paper_done_updates_row(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.insert_paper(
            conn, paper_id="p1", title="placeholder", source="s", created_at="2026-01-01T00:00:00+00:00",
            word_count=0, est_minutes=0, status="processing",
        )
        db.mark_paper_done(conn, "p1", title="Real Title", word_count=500, est_minutes=3)
        paper = db.get_paper(conn, "p1")
        assert paper["status"] == "done"
        assert paper["title"] == "Real Title"
        assert paper["word_count"] == 500
        assert paper["est_minutes"] == 3
    finally:
        conn.close()


def test_mark_paper_error_updates_row_and_sets_message(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.insert_paper(
            conn, paper_id="p1", title="placeholder", source="s", created_at="2026-01-01T00:00:00+00:00",
            word_count=0, est_minutes=0, status="processing",
        )
        db.mark_paper_error(conn, "p1", "GROBIDに接続できません")
        paper = db.get_paper(conn, "p1")
        assert paper["status"] == "error"
        assert paper["error_message"] == "GROBIDに接続できません"
    finally:
        conn.close()


def test_schema_migration_is_idempotent(isolated_data_dir):
    # get_connection() runs the error_message migration every call; calling
    # it twice against the same on-disk file must not raise.
    db.get_connection().close()
    db.get_connection().close()


def test_start_upload_processing_returns_immediately_with_processing_status(isolated_data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pdf_path = blank_pdf(tmp_path, pages=2)
    paper_id = pipeline.start_upload_processing("sample.pdf", open(pdf_path, "rb").read())

    conn = db.get_connection()
    try:
        paper = db.get_paper(conn, paper_id)
    finally:
        conn.close()
    assert paper is not None
    assert paper["status"] in ("processing", "done")  # thread may have already finished; both are valid


def test_process_in_background_marks_done_on_success(isolated_data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pdf_path = blank_pdf(tmp_path, pages=2)
    pdf_bytes = open(pdf_path, "rb").read()

    paper_id = pipeline._start_processing(
        source_label="sample.pdf",
        resolve=lambda: pipeline.resolve_upload("sample.pdf", pdf_bytes),
    )
    # _start_processing already spawned a thread; wait for it deterministically.
    conn = db.get_connection()
    try:
        for _ in range(50):
            if db.get_paper(conn, paper_id)["status"] != "processing":
                break
            time.sleep(0.05)
        paper = db.get_paper(conn, paper_id)
    finally:
        conn.close()
    assert paper["status"] == "done"
    assert paper["title"] == "Attention-Based Graph Neural Networks for Sparse Retrieval"


def test_process_in_background_marks_error_and_never_raises(isolated_data_dir, tmp_path):
    def failing_resolve():
        raise RuntimeError("GROBIDサービスに接続できません")

    # Call directly (not through a real thread) so a regression that lets
    # the exception escape fails this test loudly instead of being
    # silently swallowed by an actual background thread.
    pipeline._process_in_background("p1", failing_resolve)  # must not raise

    conn = db.get_connection()
    try:
        # the row doesn't exist yet since we bypassed _start_processing's
        # insert -- mark_paper_error's UPDATE is a no-op for a missing row,
        # which is fine; the real flow always inserts first.
        assert db.get_paper(conn, "p1") is None
    finally:
        conn.close()


def test_read_paper_shows_processing_page_without_touching_content_json(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.insert_paper(
            conn, paper_id="p1", title="placeholder", source="s", created_at="2026-01-01T00:00:00+00:00",
            word_count=0, est_minutes=0, status="processing",
        )
    finally:
        conn.close()

    response = TestClient(app).get("/papers/p1")
    assert response.status_code == 200
    assert "処理しています" in response.text
    assert 'data-paper-id="p1"' in response.text


def test_read_paper_shows_error_page(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.insert_paper(
            conn, paper_id="p1", title="placeholder", source="s", created_at="2026-01-01T00:00:00+00:00",
            word_count=0, est_minutes=0, status="processing",
        )
        db.mark_paper_error(conn, "p1", "テストエラー")
    finally:
        conn.close()

    response = TestClient(app).get("/papers/p1")
    assert response.status_code == 200
    assert "処理に失敗しました" in response.text
    assert "テストエラー" in response.text


def test_status_endpoint_reports_processing_then_done_end_to_end(isolated_data_dir, tmp_path, monkeypatch):
    release = threading.Event()
    original_tei = load_golden_tei()

    def gated_extract_tei(pdf_path):
        release.wait(timeout=5)
        return original_tei

    monkeypatch.setattr(pipeline, "extract_tei", gated_extract_tei)
    client = TestClient(app)
    pdf_path = blank_pdf(tmp_path, pages=2)

    response = client.post(
        "/papers", files={"file": ("sample.pdf", open(pdf_path, "rb"), "application/pdf")}, follow_redirects=False
    )
    assert response.status_code == 303
    paper_id = response.headers["location"].rsplit("/", 1)[-1]

    status = client.get(f"/papers/{paper_id}/status").json()
    assert status["status"] == "processing"
    assert status["elapsed_seconds"] >= 0

    release.set()
    for _ in range(50):
        status = client.get(f"/papers/{paper_id}/status").json()
        if status["status"] != "processing":
            break
        time.sleep(0.05)
    assert status == {"status": "done"}

    html = client.get(f"/papers/{paper_id}").text
    assert "Attention-Based Graph Neural Networks for Sparse Retrieval" in html


def test_status_endpoint_reports_error_end_to_end(isolated_data_dir, tmp_path, monkeypatch):
    def failing_extract_tei(pdf_path):
        raise RuntimeError("GROBIDサービスに接続できません")

    monkeypatch.setattr(pipeline, "extract_tei", failing_extract_tei)
    client = TestClient(app)
    pdf_path = blank_pdf(tmp_path, pages=1)

    response = client.post(
        "/papers", files={"file": ("sample.pdf", open(pdf_path, "rb"), "application/pdf")}, follow_redirects=False
    )
    paper_id = response.headers["location"].rsplit("/", 1)[-1]

    status = {}
    for _ in range(50):
        status = client.get(f"/papers/{paper_id}/status").json()
        if status["status"] != "processing":
            break
        time.sleep(0.05)
    assert status["status"] == "error"
    assert "GROBID" in status["error_message"]

    html = client.get(f"/papers/{paper_id}").text
    assert "処理に失敗しました" in html


def test_timeout_exception_from_grobid_client_becomes_a_clear_error(isolated_data_dir, tmp_path, monkeypatch):
    import httpx

    def raising_post(url, *, files, data, timeout):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "post", raising_post)
    client = TestClient(app)
    pdf_path = blank_pdf(tmp_path, pages=1)

    response = client.post(
        "/papers", files={"file": ("sample.pdf", open(pdf_path, "rb"), "application/pdf")}, follow_redirects=False
    )
    paper_id = response.headers["location"].rsplit("/", 1)[-1]

    status = {}
    for _ in range(50):
        status = client.get(f"/papers/{paper_id}/status").json()
        if status["status"] != "processing":
            break
        time.sleep(0.05)
    assert status["status"] == "error"
    assert "秒以内" in status["error_message"]

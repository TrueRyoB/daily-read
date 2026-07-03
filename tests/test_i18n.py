"""UI locale toggle (plan/05-h): papers are read in English but the UI
defaulted to Japanese-only, which felt inconsistent. `?lang=en` should
render English strings and persist the choice via cookie so subsequent
navigation (which doesn't carry `?lang=` itself) stays in English.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import pipeline
from app.main import app
from tests.helpers import blank_pdf, load_golden_tei


def test_index_defaults_to_japanese():
    html = TestClient(app).get("/").text
    assert "今日読む論文を追加" in html
    assert "Add a paper to read today" not in html


def test_index_lang_en_renders_english_strings(isolated_data_dir):
    html = TestClient(app).get("/?lang=en").text
    assert "Add a paper to read today" in html
    assert "今日読む論文を追加" not in html
    assert '<html lang="en">' in html


def test_lang_choice_persists_via_cookie_across_requests(isolated_data_dir):
    client = TestClient(app)
    first = client.get("/?lang=en")
    assert first.status_code == 200
    assert "lang" in first.cookies
    assert first.cookies["lang"] == "en"

    second = client.get("/")  # no ?lang= this time -- cookie should carry it
    assert "Add a paper to read today" in second.text


def test_unsupported_lang_falls_back_to_japanese(isolated_data_dir):
    html = TestClient(app).get("/?lang=fr").text
    assert "今日読む論文を追加" in html


def test_paper_view_renders_english_ui_strings_and_translations_json(isolated_data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pdf_path = blank_pdf(tmp_path, pages=2)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    html = TestClient(app).get(f"/papers/{paper_id}?lang=en").text
    assert "Estimated reading time" in html
    assert "推定読了時間" not in html
    assert 'id="i18n-data"' in html
    assert '"ap_save": "Save"' in html

"""Route-level tests for the annotations feature (plan/05-g, rewritten by
plan/07-troubleshooting-backlog.md#07-aフル対応 into an always-visible
panel + Markdown `>`-quote syntax): creating an annotation via HTTP shows
up as a marker + panel entry on the next render, editing/deleting
round-trip through the DB, and -- most importantly -- a paper reprocess
that changes the quoted wording degrades gracefully instead of crashing or
losing the note.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app import pipeline, storage
from app.main import app
from tests.helpers import blank_pdf, load_golden_tei


def _make_paper(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pdf_path = blank_pdf(tmp_path, pages=2)
    return pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())


def test_create_annotation_then_reload_shows_marker_and_panel_entry(isolated_data_dir, tmp_path, monkeypatch):
    paper_id = _make_paper(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post(
        f"/papers/{paper_id}/annotations",
        json={"note": "> standard tool for learning over relational data\nkey idea"},
    )
    assert response.status_code == 200
    annotation = response.json()
    assert annotation["note"] == "> standard tool for learning over relational data\nkey idea"

    html = client.get(f"/papers/{paper_id}").text
    assert 'class="annotations-section"' in html
    assert "key idea" in html
    assert f'data-annotation-id="{annotation["id"]}"' in html
    assert 'class="annotation-marker"' in html


def test_editing_annotation_updates_note_text(isolated_data_dir, tmp_path, monkeypatch):
    paper_id = _make_paper(tmp_path, monkeypatch)
    client = TestClient(app)

    created = client.post(
        f"/papers/{paper_id}/annotations",
        json={"note": "> standard tool for learning over relational data\nold note"},
    ).json()

    response = client.put(f"/papers/{paper_id}/annotations/{created['id']}", json={"note": "new note"})
    assert response.status_code == 200
    assert response.json()["note"] == "new note"

    html = client.get(f"/papers/{paper_id}").text
    assert "new note" in html
    assert "old note" not in html


def test_deleting_annotation_removes_marker_and_panel_entry(isolated_data_dir, tmp_path, monkeypatch):
    paper_id = _make_paper(tmp_path, monkeypatch)
    client = TestClient(app)

    created = client.post(
        f"/papers/{paper_id}/annotations",
        json={"note": "> standard tool for learning over relational data\nto be deleted"},
    ).json()

    response = client.delete(f"/papers/{paper_id}/annotations/{created['id']}")
    assert response.status_code == 200

    html = client.get(f"/papers/{paper_id}").text
    assert "to be deleted" not in html
    assert f'data-annotation-id="{created["id"]}"' not in html


def test_annotation_survives_reprocessing_but_is_flagged_not_found(isolated_data_dir, tmp_path, monkeypatch):
    # Mirrors test_old_content_json_without_bibliography_key_still_renders:
    # annotations live in SQLite, independent of content.json, so rewriting
    # content.json to no longer contain the quoted text must not crash or
    # silently drop the note -- it should render with a "not found" flag.
    paper_id = _make_paper(tmp_path, monkeypatch)
    client = TestClient(app)

    created = client.post(
        f"/papers/{paper_id}/annotations",
        json={"note": "> standard tool for learning over relational data\nsurviving note"},
    ).json()

    content_path = storage.content_json_path(paper_id)
    content = json.loads(content_path.read_text(encoding="utf-8"))
    for unit in content["units"]:
        if "text" in unit:
            unit["text"] = unit["text"].replace("standard tool for learning over relational data", "a completely different phrase")
    content_path.write_text(json.dumps(content), encoding="utf-8")

    response = client.get(f"/papers/{paper_id}")
    assert response.status_code == 200
    html = response.text
    assert "surviving note" in html  # note text itself still shown in the panel
    assert "本文中に見つかりません" in html
    assert f'data-annotation-id="{created["id"]}"' in html
    assert 'class="annotation-marker"' not in html  # no block matched, so no marker rendered


def test_create_annotation_404_for_nonexistent_paper(isolated_data_dir):
    response = TestClient(app).post("/papers/does-not-exist/annotations", json={"note": "n"})
    assert response.status_code == 404


def test_create_annotation_400_for_empty_note(isolated_data_dir, tmp_path, monkeypatch):
    paper_id = _make_paper(tmp_path, monkeypatch)
    client = TestClient(app)

    assert client.post(f"/papers/{paper_id}/annotations", json={"note": "  "}).status_code == 400


def test_annotation_with_no_quote_lines_shows_as_musings_with_no_marker(isolated_data_dir, tmp_path, monkeypatch):
    paper_id = _make_paper(tmp_path, monkeypatch)
    client = TestClient(app)

    created = client.post(f"/papers/{paper_id}/annotations", json={"note": "just a general thought"}).json()

    html = client.get(f"/papers/{paper_id}").text
    assert "just a general thought" in html
    assert f'data-annotation-id="{created["id"]}"' in html
    assert 'class="annotation-marker"' not in html
    assert "本文中に見つかりません" in html


def test_edit_and_delete_404_for_nonexistent_annotation(isolated_data_dir, tmp_path, monkeypatch):
    paper_id = _make_paper(tmp_path, monkeypatch)
    client = TestClient(app)

    assert client.put(f"/papers/{paper_id}/annotations/999999", json={"note": "n"}).status_code == 404
    assert client.delete(f"/papers/{paper_id}/annotations/999999").status_code == 404


def test_annotation_panel_and_mobile_section_both_present(isolated_data_dir, tmp_path, monkeypatch):
    paper_id = _make_paper(tmp_path, monkeypatch)
    client = TestClient(app)

    client.post(
        f"/papers/{paper_id}/annotations",
        json={"note": "> standard tool for learning over relational data\nnote text"},
    )
    html = client.get(f"/papers/{paper_id}").text
    assert 'class="annotations-mobile"' in html
    assert 'data-role="annotation-compose-form"' in html
    # Once as visible text in the desktop panel copy, once in the mobile
    # section copy (each <li> also repeats it once more in its
    # data-raw-note attribute, hence 4 total occurrences, not 2).
    assert html.count(">note text<") == 2

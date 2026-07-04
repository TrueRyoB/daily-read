"""plan/07-troubleshooting-backlog.md#b-7: OpenAlex-based related-paper
suggestions. All tests monkeypatch related_papers._http_get -- the sole
network seam -- so nothing here makes a real HTTP call.
"""

from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from app import db, pipeline, related_papers, storage
from app.main import app
from tests.helpers import blank_pdf, load_golden_tei

_CURRENT_WORK = {
    "id": "https://openalex.org/W1",
    "title": "Attention Is All You Need",
    "cited_by_count": 100,
    "doi": "https://doi.org/10.1/current",
    "authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "Ada Lovelace"}}],
    "primary_location": {
        "landing_page_url": "https://example.com/current",
        "source": {"id": "https://openalex.org/S1", "display_name": "NeurIPS"},
    },
}


def _work(id_, title, citation_count=5, authors=None):
    return {
        "id": id_,
        "title": title,
        "cited_by_count": citation_count,
        "doi": None,
        "authorships": [{"author": {"display_name": a}} for a in (authors or ["Some Author"])],
        "primary_location": {"landing_page_url": f"{id_}/html"},
    }


def test_resolve_work_returns_none_for_empty_title():
    assert related_papers.resolve_work("") is None


def test_resolve_work_returns_none_when_no_results(monkeypatch):
    monkeypatch.setattr(related_papers, "_http_get", lambda path, params: {"results": []})
    assert related_papers.resolve_work("Some Paper") is None


def test_resolve_work_rejects_low_overlap_match(monkeypatch):
    # A free-text search always returns *a* result -- a completely unrelated
    # title shouldn't be accepted as the resolved anchor.
    monkeypatch.setattr(
        related_papers,
        "_http_get",
        lambda path, params: {"results": [_work("https://openalex.org/W9", "Completely Unrelated Topic")]},
    )
    assert related_papers.resolve_work("Attention Is All You Need") is None


def test_resolve_work_accepts_close_title_match(monkeypatch):
    monkeypatch.setattr(related_papers, "_http_get", lambda path, params: {"results": [_CURRENT_WORK]})
    resolved = related_papers.resolve_work("Attention Is All You Need")
    assert resolved["id"] == "https://openalex.org/W1"


def test_generate_candidates_tags_each_signal(monkeypatch):
    def fake_get(path, params):
        filt = params.get("filter", "")
        if filt.startswith("cites:"):
            return {"results": [_work("https://openalex.org/W2", "Cites Current")]}
        if filt.startswith("author.id:"):
            return {"results": [_work("https://openalex.org/W3", "Same Author Paper")]}
        if filt.startswith("primary_location.source.id:"):
            return {"results": [_work("https://openalex.org/W4", "Same Venue Paper")]}
        return {"results": []}

    monkeypatch.setattr(related_papers, "_http_get", fake_get)
    candidates = related_papers.generate_candidates(_CURRENT_WORK, bibliography=[])

    assert candidates["https://openalex.org/W2"]["direct_citation"] is True
    assert candidates["https://openalex.org/W3"]["same_author"] is True
    assert candidates["https://openalex.org/W4"]["same_venue"] is True


def test_generate_candidates_excludes_current_work_itself(monkeypatch):
    monkeypatch.setattr(
        related_papers, "_http_get", lambda path, params: {"results": [_CURRENT_WORK]}
    )
    candidates = related_papers.generate_candidates(_CURRENT_WORK, bibliography=[])
    assert _CURRENT_WORK["id"] not in candidates


def test_generate_candidates_resolves_bibliography_references(monkeypatch):
    monkeypatch.setattr(
        related_papers,
        "_http_get",
        lambda path, params: {"results": [_work("https://openalex.org/W5", "Referenced Paper")]},
    )
    candidates = related_papers.generate_candidates(None, bibliography=[{"title": "Referenced Paper"}])
    assert candidates["https://openalex.org/W5"]["reference"] is True


def test_generate_candidates_skips_bibliography_entries_without_title(monkeypatch):
    calls = []
    monkeypatch.setattr(related_papers, "_http_get", lambda path, params: calls.append(1) or {"results": []})
    related_papers.generate_candidates(None, bibliography=[{"title": ""}, {}])
    assert calls == []


def test_score_candidates_ranks_citation_edge_above_same_author_only():
    candidates = {
        "w1": {
            "openalex_id": "w1",
            "title": "A",
            "authors": [],
            "year": 2020,
            "citation_count": 1,
            "url": None,
            "reference": False,
            "direct_citation": True,
            "same_author": False,
            "same_venue": False,
        },
        "w2": {
            "openalex_id": "w2",
            "title": "B",
            "authors": [],
            "year": 2020,
            "citation_count": 1,
            "url": None,
            "reference": False,
            "direct_citation": False,
            "same_author": True,
            "same_venue": False,
        },
    }
    ranked = related_papers.score_candidates(candidates)
    assert [c["openalex_id"] for c in ranked] == ["w1", "w2"]


def test_score_candidates_caps_at_top_10():
    candidates = {
        f"w{i}": {
            "openalex_id": f"w{i}",
            "title": f"Paper {i}",
            "authors": [],
            "year": 2020,
            "citation_count": i,
            "url": None,
            "reference": False,
            "direct_citation": False,
            "same_author": False,
            "same_venue": False,
        }
        for i in range(15)
    }
    ranked = related_papers.score_candidates(candidates)
    assert len(ranked) == 10
    # highest citation_count (best tie-break with all flags equal) comes first
    assert ranked[0]["openalex_id"] == "w14"


def test_run_and_store_writes_done_status_on_success(isolated_data_dir, monkeypatch):
    storage.paper_dir("p1").mkdir(parents=True)
    monkeypatch.setattr(related_papers, "find_related_papers", lambda title, bibliography: [{"openalex_id": "w1"}])

    related_papers.run_and_store("p1", "Some Title", [])

    payload = json.loads(storage.related_papers_json_path("p1").read_text(encoding="utf-8"))
    assert payload["status"] == "done"
    assert payload["results"] == [{"openalex_id": "w1"}]


def test_run_and_store_writes_error_status_on_exception(isolated_data_dir, monkeypatch):
    storage.paper_dir("p1").mkdir(parents=True)

    def boom(title, bibliography):
        raise RuntimeError("OpenAlex is down")

    monkeypatch.setattr(related_papers, "find_related_papers", boom)
    related_papers.run_and_store("p1", "Some Title", [])

    payload = json.loads(storage.related_papers_json_path("p1").read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert "OpenAlex is down" in payload["error_message"]


def _wait_until_related_papers_terminal(client, paper_id):
    for _ in range(50):
        data = client.get(f"/papers/{paper_id}/related-papers").json()
        if data["status"] != "processing":
            return data
        time.sleep(0.05)
    return data


def test_related_papers_route_not_started_by_default(isolated_data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pdf_path = blank_pdf(tmp_path, pages=2)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    client = TestClient(app)
    assert client.get(f"/papers/{paper_id}/related-papers").json() == {"status": "not_started"}


def test_post_related_papers_starts_a_background_job_and_completes(isolated_data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    monkeypatch.setattr(related_papers, "find_related_papers", lambda title, bibliography: [{"openalex_id": "w1"}])
    pdf_path = blank_pdf(tmp_path, pages=2)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    client = TestClient(app)
    response = client.post(f"/papers/{paper_id}/related-papers")
    assert response.json()["status"] in ("processing", "done")

    final = _wait_until_related_papers_terminal(client, paper_id)
    assert final["status"] == "done"
    assert final["results"] == [{"openalex_id": "w1"}]


def test_post_related_papers_is_a_noop_when_already_started(isolated_data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    call_count = 0

    def fake_find(title, bibliography):
        nonlocal call_count
        call_count += 1
        return []

    monkeypatch.setattr(related_papers, "find_related_papers", fake_find)
    pdf_path = blank_pdf(tmp_path, pages=2)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    client = TestClient(app)
    client.post(f"/papers/{paper_id}/related-papers")
    _wait_until_related_papers_terminal(client, paper_id)
    client.post(f"/papers/{paper_id}/related-papers")  # pressing the button again
    _wait_until_related_papers_terminal(client, paper_id)

    assert call_count == 1  # the second POST didn't fire a second OpenAlex job


def test_post_related_papers_404s_for_unknown_paper(isolated_data_dir):
    response = TestClient(app).post("/papers/does-not-exist/related-papers")
    assert response.status_code == 404


def test_related_papers_section_markup_present(isolated_data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pdf_path = blank_pdf(tmp_path, pages=2)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    html = TestClient(app).get(f"/papers/{paper_id}").text
    assert 'data-role="related-papers"' in html
    assert 'data-role="related-papers-button"' in html
    assert 'data-role="related-papers-list"' in html

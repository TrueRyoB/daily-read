"""Smoke test for the actual HTTP route + Jinja template rendering, not just
content.json shape. Cheap and offline, same golden fixture as
test_pipeline_golden_fixture.py.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import pipeline
from app.main import app
from tests.helpers import blank_pdf, load_golden_tei

_TEI_NS = "http://www.tei-c.org/ns/1.0"

_UNDEFINED_FREQUENT_TERM_TEI = f"""<?xml version="1.0"?>
<TEI xmlns="{_TEI_NS}">
  <text><body>
    <div>
      <head>1 Introduction</head>
      <p>Random Forest is used as a strong baseline in this work.</p>
      <p>We compare against Random Forest across all benchmarks.</p>
      <p>Random Forest results are reported in the appendix.</p>
    </div>
  </body></text>
</TEI>
"""


def test_paper_view_renders_title_authors_and_abstract(isolated_data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pdf_path = blank_pdf(tmp_path, pages=2)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    client = TestClient(app)
    response = client.get(f"/papers/{paper_id}")

    assert response.status_code == 200
    html = response.text
    assert "Attention-Based Graph Neural Networks for Sparse Retrieval" in html
    assert "Ada Nakamura, Kenji Ito" in html
    assert "We propose a graph neural network architecture" in html
    # plan/05-e: the app's purpose is readability, not a time quota.
    assert "30分" not in html


def test_index_page_has_no_30_minute_framing(isolated_data_dir):
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert "30分" not in response.text


def test_marking_term_known_hides_it_from_this_and_future_papers(isolated_data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    client = TestClient(app)

    pdf_path_1 = blank_pdf(tmp_path, pages=2)
    paper_1 = pipeline.process_upload("sample1.pdf", open(pdf_path_1, "rb").read())
    assert 'data-term="GNN"' in client.get(f"/papers/{paper_1}").text

    response = client.post("/glossary/known-terms", json={"term": "GNN"})
    assert response.status_code == 200

    # Already-processed paper: term disappears immediately (display-time filter).
    assert 'data-term="GNN"' not in client.get(f"/papers/{paper_1}").text

    # A paper processed afterward never shows it either -- plan/04-b's core
    # requirement: don't ask about a known term again in a future paper.
    second_dir = tmp_path / "second"
    second_dir.mkdir()
    pdf_path_2 = blank_pdf(second_dir, pages=2)
    paper_2 = pipeline.process_upload("sample2.pdf", open(pdf_path_2, "rb").read())
    assert 'data-term="GNN"' not in client.get(f"/papers/{paper_2}").text


def test_figures_data_and_modal_markup_present(isolated_data_dir, tmp_path, monkeypatch):
    # Offline-verifiable slice of plan/01: the server-rendered data/markup
    # that reader.js's mobile-modal / desktop-independent-scroll behavior
    # depends on. The actual interactive scroll/opacity/modal behavior
    # itself needs a real browser to verify -- no browser automation tool
    # is available in this environment, so that part is NOT covered here.
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pdf_path = blank_pdf(tmp_path, pages=2)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    html = TestClient(app).get(f"/papers/{paper_id}").text
    assert 'id="figures-data"' in html
    assert 'id="figure-modal"' in html
    assert "figure-modal-close" in html
    assert "figure-modal-backdrop" in html
    assert "本文に戻る" not in html  # dropped: text scroll position never moves now

    import json as _json
    import re

    match = re.search(
        r'<script type="application/json" id="figures-data">(.*?)</script>', html, re.DOTALL
    )
    figures_payload = _json.loads(match.group(1))
    assert len(figures_payload) == 1
    assert figures_payload[0]["figure_id"] == "figure-1"
    assert figures_payload[0]["image_url"] == f"/papers/{paper_id}/figures/figure-1.png"
    assert figures_payload[0]["caption"] == "Figure 1: Overview of the attention-pooled message passing pipeline."


def test_inline_figure_mention_renders_as_link_and_old_button_is_gone(isolated_data_dir, tmp_path, monkeypatch):
    figure_mention_tei = f"""<?xml version="1.0"?>
    <TEI xmlns="{_TEI_NS}">
      <text><body>
        <div>
          <head>1 Intro</head>
          <p>As shown in Figure <ref type="figure" target="#fig_0">1</ref>, it works.</p>
          <figure xml:id="fig_0" coords="1,50.0,50.0,500.0,250.0">
            <head>Figure 1</head>
            <figDesc>A diagram.</figDesc>
          </figure>
        </div>
      </body></text>
    </TEI>
    """
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: figure_mention_tei)
    pdf_path = blank_pdf(tmp_path, pages=2)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    html = TestClient(app).get(f"/papers/{paper_id}").text
    assert '<a class="figure-jump" href="#figure-1">1</a>' in html
    assert "図を見る" not in html  # the old standalone button is gone (plan/05-b)
    assert "\x00" not in html


def test_citation_links_to_doi_when_present_and_anchor_otherwise(isolated_data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pdf_path = blank_pdf(tmp_path, pages=2)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    html = TestClient(app).get(f"/papers/{paper_id}").text
    # b0 has a DOI in the fixture -> external link, not an in-page anchor.
    assert '<a class="citation" href="https://doi.org/10.48550/arXiv.1609.02907">[1]</a>' in html
    # b1 has no DOI -> falls back to the in-page bibliography anchor.
    assert '<a class="citation" href="#bib-b1">[2]</a>' in html
    # No raw placeholder bytes should ever reach the rendered HTML.
    assert "\x00" not in html


def test_bibliography_dom_ids_are_unique_across_desktop_and_mobile(isolated_data_dir, tmp_path, monkeypatch):
    # Regression guard (plan/05-a): desktop panel and the mobile-only
    # section used to render the same id="bib-bX" twice (invalid HTML),
    # which silently broke citation jumps on narrow viewports.
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pdf_path = blank_pdf(tmp_path, pages=2)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    html = TestClient(app).get(f"/papers/{paper_id}").text
    assert html.count('id="bib-b0"') == 1
    assert html.count('id="bib-b1"') == 1
    assert 'id="bib-mobile-b0"' in html
    assert 'id="bib-mobile-b1"' in html


def test_split_multi_citation_renders_as_one_merged_link(isolated_data_dir, tmp_path, monkeypatch):
    split_citation_tei = f"""<?xml version="1.0"?>
    <TEI xmlns="{_TEI_NS}">
      <text>
        <body><div><head>1 Intro</head>
          <p>Prior work <ref type="bibr" target="#b0">[1,</ref><ref type="bibr" target="#b1">2]</ref> studied this.</p>
        </div></body>
        <back><div type="bibliography"><listBibl>
          <biblStruct xml:id="b0"><analytic><title level="a" type="main">Paper One</title></analytic></biblStruct>
          <biblStruct xml:id="b1"><analytic><title level="a" type="main">Paper Two</title></analytic></biblStruct>
        </listBibl></div></back>
      </text>
    </TEI>
    """
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: split_citation_tei)
    pdf_path = blank_pdf(tmp_path, pages=1)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    html = TestClient(app).get(f"/papers/{paper_id}").text
    assert '<a class="citation" href="#bib-b0">[1,2]</a>' in html
    assert html.count('class="citation"') == 1  # not split into two links


def test_bibliography_panel_and_mobile_section_present(isolated_data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pdf_path = blank_pdf(tmp_path, pages=2)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    html = TestClient(app).get(f"/papers/{paper_id}").text
    assert 'id="bib-b0"' in html
    assert 'id="bib-b1"' in html
    assert "Semi-Supervised Classification with Graph Convolutional Networks" in html
    assert "Neural Message Passing for Quantum Chemistry" in html
    assert 'class="bibliography-mobile"' in html
    # Desktop panel entries share the dim-until-active panel-item behavior.
    assert 'class="bib-entry panel-item"' in html
    # Mobile entries are plain (no independent-scroll dimming there).
    assert 'class="bib-entry"' in html


def test_old_content_json_without_bibliography_key_still_renders(isolated_data_dir, tmp_path, monkeypatch):
    # Backward compatibility: content.json written before plan/03-c has no
    # "bibliography" key at all.
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pdf_path = blank_pdf(tmp_path, pages=2)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    from app import storage
    import json as _json

    content_path = storage.content_json_path(paper_id)
    content = _json.loads(content_path.read_text(encoding="utf-8"))
    del content["bibliography"]
    content_path.write_text(_json.dumps(content), encoding="utf-8")

    response = TestClient(app).get(f"/papers/{paper_id}")
    assert response.status_code == 200
    assert "bibliography-mobile" not in response.text


def test_toc_lists_headings_with_matching_anchor_ids(isolated_data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pdf_path = blank_pdf(tmp_path, pages=2)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    html = TestClient(app).get(f"/papers/{paper_id}").text
    assert '<details class="toc">' in html
    # 3 headings in the golden fixture: "1 Introduction", "Related Work", "2 Method"
    assert '<li class="toc-level-1"><a href="#heading-1">1 Introduction</a></li>' in html
    assert '<li class="toc-level-2"><a href="#heading-2">Related Work</a></li>' in html
    assert '<li class="toc-level-1"><a href="#heading-3">2 Method</a></li>' in html
    # the heading elements themselves carry the matching ids
    assert 'id="heading-1"' in html
    assert 'id="heading-2"' in html
    assert 'id="heading-3"' in html


def test_toc_absent_when_no_headings(isolated_data_dir, tmp_path, monkeypatch):
    no_headings_tei = f"""<?xml version="1.0"?>
    <TEI xmlns="{_TEI_NS}"><text><body><div><p>Just one paragraph, no headings.</p></div></body></text></TEI>
    """
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: no_headings_tei)
    pdf_path = blank_pdf(tmp_path, pages=1)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    html = TestClient(app).get(f"/papers/{paper_id}").text
    assert '<details class="toc">' not in html


def test_preread_section_absent_when_no_undefined_frequent_terms(isolated_data_dir, tmp_path, monkeypatch):
    # The golden fixture's only glossary entry (GNN) is an in-text
    # definition, not a "concordance" (undefined) one, so the pre-reading
    # section (plan/04-c) should not render at all.
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pdf_path = blank_pdf(tmp_path, pages=2)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    html = TestClient(app).get(f"/papers/{paper_id}").text
    assert "preread-terms" not in html


def test_preread_section_lists_frequent_undefined_terms(isolated_data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: _UNDEFINED_FREQUENT_TERM_TEI)
    pdf_path = blank_pdf(tmp_path, pages=2)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    html = TestClient(app).get(f"/papers/{paper_id}").text
    assert "preread-terms" in html
    assert "Random Forest" in html
    assert 'data-term="Random Forest"' in html  # the "知っている" button target
    # Still also present inline for in-reading context recall (04-c: both coexist).
    assert 'class="gloss" data-term="Random Forest"' in html


def test_preread_search_link_includes_paper_title_as_context(isolated_data_dir, tmp_path, monkeypatch):
    # plan/05-d: a bare-term search is ambiguous; the paper's own title is
    # appended as cheap, always-available context.
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: _UNDEFINED_FREQUENT_TERM_TEI)
    pdf_path = blank_pdf(tmp_path, pages=2)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    html = TestClient(app).get(f"/papers/{paper_id}").text
    # _guess_title falls back to the first heading ("1 Introduction") since
    # this fixture has no teiHeader.
    assert "1+Introduction" in html or "1%20Introduction" in html


def test_marking_known_from_preread_section_uses_same_store_as_popover(isolated_data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: _UNDEFINED_FREQUENT_TERM_TEI)
    client = TestClient(app)
    pdf_path = blank_pdf(tmp_path, pages=2)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    response = client.post("/glossary/known-terms", json={"term": "Random Forest"})
    assert response.status_code == 200

    html = client.get(f"/papers/{paper_id}").text
    assert "preread-terms" not in html
    assert 'data-term="Random Forest"' not in html

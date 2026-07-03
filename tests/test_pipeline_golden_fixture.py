"""Cheap, offline, end-to-end pipeline check against a hand-authored GROBID
TEI fixture (tests/fixtures/sample_fulltext.tei.xml) -- no Docker, no GROBID,
no network. Mocks app.pipeline.extract_tei so the "GROBID call" is instant.

This file intentionally asserts *current* (buggy) behavior for the items
tracked in plan/03-pdf-domain-extraction-gaps.md and
plan/04-glossary-quality-and-user-vocabulary.md, each tagged with which
ticket should change it. That makes it a live regression baseline: as each
ticket is implemented, update the matching assertion here (that's the
signal the fix landed) rather than leaving a stale expectation.
"""

from __future__ import annotations

import json

from app import pipeline, storage
from tests.helpers import blank_pdf, load_golden_tei


def _process_golden_paper(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pdf_path = blank_pdf(tmp_path, pages=2)
    pdf_bytes = open(pdf_path, "rb").read()
    paper_id = pipeline.process_upload("sample.pdf", pdf_bytes)
    content = json.loads(storage.content_json_path(paper_id).read_text(encoding="utf-8"))
    return paper_id, content


def test_pipeline_runs_end_to_end_offline(isolated_data_dir, tmp_path, monkeypatch):
    paper_id, content = _process_golden_paper(tmp_path, monkeypatch)
    assert paper_id
    assert content["units"]
    assert content["word_count"] > 0


def test_raw_tei_is_persisted_for_debugging(isolated_data_dir, tmp_path, monkeypatch):
    # plan/03-b: keep the raw GROBID response on disk so real structural
    # questions can be checked against real data instead of guessed at.
    paper_id, _ = _process_golden_paper(tmp_path, monkeypatch)
    saved = storage.tei_xml_path(paper_id).read_text(encoding="utf-8")
    assert saved == load_golden_tei()


def test_title_authors_abstract_extracted_from_teiheader(isolated_data_dir, tmp_path, monkeypatch):
    # Fixed by plan/03-a: title/authors/abstract now come from teiHeader
    # instead of _guess_title's body-heading fallback.
    _, content = _process_golden_paper(tmp_path, monkeypatch)
    assert content["title"] == "Attention-Based Graph Neural Networks for Sparse Retrieval"
    assert content["authors"] == ["Ada Nakamura", "Kenji Ito"]
    assert content["abstract"] == (
        "We propose a graph neural network architecture for sparse retrieval that "
        "combines message passing with attention pooling. Our method improves "
        "recall over strong baselines while remaining efficient on CPU-only "
        "hardware."
    )


def test_nested_unnumbered_heading_level_is_correct(isolated_data_dir, tmp_path, monkeypatch):
    # Fixed by plan/03-d: unnumbered headings ("Related Work" has no "1.2"
    # style prefix) now fall back to div nesting depth instead of always
    # defaulting to level 1. It's nested one level under "1 Introduction".
    _, content = _process_golden_paper(tmp_path, monkeypatch)
    related_work = next(u for u in content["units"] if u["text"] == "Related Work")
    assert related_work["level"] == 2


def test_figure_extracted_when_coords_is_on_graphic_child(isolated_data_dir, tmp_path, monkeypatch):
    # Fixed by plan/03-b: _crop_image now falls back to the nested <graphic>
    # element's coords when <figure> itself has none (this fixture's shape,
    # matching GROBID's own documented figure structure).
    _, content = _process_golden_paper(tmp_path, monkeypatch)
    assert len(content["figures"]) == 1
    figure = content["figures"][0]
    assert figure["caption"] == "Figure 1: Overview of the attention-pooled message passing pipeline."
    assert "image_bytes" not in figure  # stripped from content.json by _content_to_json
    figure_ref = next(u for u in content["units"] if u["kind"] == "figure_ref")
    assert figure_ref["figure_id"] == figure["figure_id"]


def test_citation_placeholder_and_bibliography_extracted(isolated_data_dir, tmp_path, monkeypatch):
    # Fixed by plan/03-c: <ref type="bibr"> becomes a citation placeholder
    # (rendering.py turns it into a link at display time) instead of being
    # flattened to plain text, and text/back's reference list is parsed.
    _, content = _process_golden_paper(tmp_path, monkeypatch)
    intro = next(u for u in content["units"] if u["text"].startswith("Graph Neural Network"))
    assert "\x00CITE:b0\x00[1]\x00/CITE\x00" in intro["text"]

    assert len(content["bibliography"]) == 2
    b0 = next(b for b in content["bibliography"] if b["bib_id"] == "b0")
    assert b0["title"] == "Semi-Supervised Classification with Graph Convolutional Networks"
    assert b0["authors"] == ["Thomas Kipf"]
    assert b0["url"] == "https://doi.org/10.48550/arXiv.1609.02907"
    b1 = next(b for b in content["bibliography"] if b["bib_id"] == "b1")
    assert b1["url"] is None  # no DOI present in the fixture for this entry


def test_citation_placeholder_does_not_pollute_glossary_or_word_count(isolated_data_dir, tmp_path, monkeypatch):
    # Regression guard found while implementing 03-c: the raw placeholder
    # wrapper contains the literal word "CITE" at a word boundary, which
    # would otherwise get counted as a frequent capitalized glossary
    # candidate (every citation in the paper matches it).
    _, content = _process_golden_paper(tmp_path, monkeypatch)
    assert not any(e["term"] == "CITE" for e in content["glossary"])


def test_in_text_definition_immediately_after_heading_is_detected(isolated_data_dir, tmp_path, monkeypatch):
    # Fixed by plan/04-g: pipeline.py now joins units with ". " instead of
    # a plain space, so "1 Introduction" no longer glues onto "Graph Neural
    # Network (GNN) models...". GNN is once again picked up as the most
    # reliable glossary signal (an in-text definition), not silently dropped.
    _, content = _process_golden_paper(tmp_path, monkeypatch)
    gnn = next(e for e in content["glossary"] if e["term"] == "GNN")
    assert gnn["source"] == "in_text_definition"
    assert gnn["definition"] == "Graph Neural Network"


def test_figure_mention_placeholder_does_not_pollute_glossary(isolated_data_dir, tmp_path, monkeypatch):
    # Regression guard (plan/05-b, found proactively from the earlier "CITE"
    # bug found in 03-c): the raw "\x00FIGREF:...\x00" wrapper contains the
    # literal word "FIGREF" at a word boundary too.
    tei = """<?xml version="1.0"?>
    <TEI xmlns="http://www.tei-c.org/ns/1.0">
      <text><body><div><head>1 Intro</head>
        <p>See Figure <ref type="figure" target="#fig_0">1</ref> and Figure <ref type="figure" target="#fig_0">1</ref> again.</p>
        <figure xml:id="fig_0" coords="1,50.0,50.0,500.0,250.0"><figDesc>A diagram.</figDesc></figure>
      </div></body></text>
    </TEI>
    """
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: tei)
    pdf_path = blank_pdf(tmp_path, pages=1)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())
    content = json.loads(storage.content_json_path(paper_id).read_text(encoding="utf-8"))
    assert not any(e["term"] == "FIGREF" for e in content["glossary"])


def test_known_author_names_excluded_end_to_end(isolated_data_dir, tmp_path, monkeypatch):
    # plan/05-c, full wiring: pipeline.py assembles known_names from the
    # paper's own teiHeader authors + its reference list's authors and
    # passes them through to the glossary extractor.
    tei = """<?xml version="1.0"?>
    <TEI xmlns="http://www.tei-c.org/ns/1.0">
      <teiHeader>
        <fileDesc>
          <titleStmt><title level="a" type="main">A Paper</title></titleStmt>
          <sourceDesc><biblStruct><analytic>
            <author><persName><forename type="first">Ian</forename><surname>Ward</surname></persName></author>
          </analytic></biblStruct></sourceDesc>
        </fileDesc>
      </teiHeader>
      <text><body><div><head>1 Intro</head>
        <p>Ward introduced this method. Ward later extended it further. Ward's approach remains popular. Recent work by Ward confirms this.</p>
      </div></body></text>
    </TEI>
    """
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: tei)
    pdf_path = blank_pdf(tmp_path, pages=1)
    paper_id = pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())
    content = json.loads(storage.content_json_path(paper_id).read_text(encoding="utf-8"))
    assert not any(e["term"] == "Ward" for e in content["glossary"])

"""plan/07-troubleshooting-backlog.md: exact-substring `<mark>` highlighting
for annotation quotes, replacing the old block-level 📝 marker. The risky
part is that a quote's character range can start or end in the middle of
an already-tag-producing span (a glossary term, or a resolved citation/
figure-mention label) -- these tests exercise that overlap/snap-to-boundary
logic directly through the public `render_units` entry point, since the
tokenizer/snapping helpers are private implementation details.
"""

from __future__ import annotations

from app import rendering


def _glossary_entry(term: str, source: str = "in_text_definition") -> dict:
    return {"term": term, "definition": "d", "contexts": [], "source": source}


def test_no_annotations_renders_exactly_as_before():
    units = [{"kind": "paragraph", "text": "Graph Neural Networks are widely used."}]
    glossary = [_glossary_entry("Graph Neural Networks")]
    rendered, matched_ids = rendering.render_units(units, glossary, [], [])
    assert matched_ids == set()
    assert "<mark" not in rendered[0]["html"]
    assert '<span class="gloss" data-term="Graph Neural Networks" tabindex="0">Graph Neural Networks</span>' in rendered[0]["html"]


def test_quote_starting_mid_glossary_term_snaps_to_include_the_whole_gloss_span():
    units = [{"kind": "paragraph", "text": "Graph Neural Networks are widely used."}]
    glossary = [_glossary_entry("Graph Neural Networks")]
    annotations = [{"id": 1, "note": "> Neural Networks are widely"}]
    rendered, matched_ids = rendering.render_units(units, glossary, [], annotations)
    html = rendered[0]["html"]
    assert matched_ids == {1}
    # The gloss span is never split -- it ends up entirely inside the mark.
    assert html.count("<mark") == html.count("</mark>") == 1
    assert html.count('<span class="gloss"') == 1
    assert '<mark class="annotation-highlight" data-annotation-id="1"><span class="gloss"' in html
    assert "</span> are widely</mark>" in html


def test_quote_ending_mid_citation_label_snaps_to_include_the_whole_link():
    units = [
        {
            "kind": "paragraph",
            "text": "See prior work \x00CITE:b0\x00[1]\x00/CITE\x00 for details.",
        }
    ]
    # Quote ends inside the citation's visible label ("[1]"), at "work [1".
    annotations = [{"id": 1, "note": "> prior work [1"}]
    rendered, matched_ids = rendering.render_units(units, [], [], annotations)
    html = rendered[0]["html"]
    assert matched_ids == {1}
    assert html.count("<mark") == html.count("</mark>") == 1
    assert '<a class="citation"' in html
    # the whole <a>...</a> is inside the mark, not cut in half
    assert "[1]</a></mark>" in html


def test_two_non_overlapping_quotes_in_the_same_unit_both_highlighted():
    units = [{"kind": "paragraph", "text": "The first phrase and the second phrase both matter."}]
    annotations = [
        {"id": 1, "note": "> first phrase"},
        {"id": 2, "note": "> second phrase"},
    ]
    rendered, matched_ids = rendering.render_units(units, [], [], annotations)
    html = rendered[0]["html"]
    assert matched_ids == {1, 2}
    assert html.count("<mark") == html.count("</mark>") == 2
    assert 'data-annotation-id="1"' in html
    assert 'data-annotation-id="2"' in html


def test_gloss_term_fully_inside_a_quote_stays_intact():
    units = [{"kind": "paragraph", "text": "We use Graph Neural Networks for this task."}]
    glossary = [_glossary_entry("Graph Neural Networks")]
    annotations = [{"id": 1, "note": "> We use Graph Neural Networks for this"}]
    rendered, matched_ids = rendering.render_units(units, glossary, [], annotations)
    html = rendered[0]["html"]
    assert matched_ids == {1}
    assert html.count('<span class="gloss"') == 1
    assert html.count("<mark") == html.count("</mark>") == 1


def test_concordance_term_gets_unconfirmed_modifier_class():
    units = [{"kind": "paragraph", "text": "Random Forest is a baseline."}]
    glossary = [_glossary_entry("Random Forest", source="concordance")]
    rendered, _ = rendering.render_units(units, glossary, [], [])
    assert 'class="gloss gloss-unconfirmed" data-term="Random Forest"' in rendered[0]["html"]


def test_defined_term_does_not_get_unconfirmed_modifier_class():
    units = [{"kind": "paragraph", "text": "GNNs are widely used."}]
    glossary = [_glossary_entry("GNNs", source="in_text_definition")]
    rendered, _ = rendering.render_units(units, glossary, [], [])
    assert 'class="gloss" data-term="GNNs"' in rendered[0]["html"]
    assert "gloss-unconfirmed" not in rendered[0]["html"]

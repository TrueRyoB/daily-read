"""plan/07-troubleshooting-backlog.md#b-11: a "figure_fallback" unit
(GROBID's mis-segmented diagram-label fragments, one per line) renders as
its own flagged fragment list -- never as a heading, never silently merged
into surrounding prose.
"""

from __future__ import annotations

from app import rendering


def test_figure_fallback_unit_renders_one_html_line_per_fragment():
    units = [{"kind": "figure_fallback", "text": "Offline training\nDeploy\nLive experiment\nModel"}]
    rendered, matched_ids = rendering.render_units(units, glossary=[], bibliography=[], annotations=[])
    assert matched_ids == set()
    assert rendered[0]["kind"] == "figure_fallback"
    assert rendered[0]["html_lines"] == ["Offline training", "Deploy", "Live experiment", "Model"]


def test_figure_fallback_never_enters_table_of_contents():
    units = [
        {"kind": "heading", "text": "Real Section", "level": 1},
        {"kind": "figure_fallback", "text": "Deploy\nModel"},
    ]
    rendered, _ = rendering.render_units(units, glossary=[], bibliography=[], annotations=[])
    toc = rendering.table_of_contents(rendered)
    assert [entry["text"] for entry in toc] == ["Real Section"]


def test_figure_fallback_fragment_can_still_link_a_glossary_term():
    units = [{"kind": "figure_fallback", "text": "Model\nDeploy"}]
    glossary = [{"term": "Model", "definition": "d", "contexts": [], "source": "in_text_definition"}]
    rendered, _ = rendering.render_units(units, glossary=glossary, bibliography=[], annotations=[])
    assert '<span class="gloss" data-term="Model" tabindex="0">Model</span>' in rendered[0]["html_lines"][0]


def test_figure_fallback_is_html_escaped():
    units = [{"kind": "figure_fallback", "text": "<script>alert(1)</script>"}]
    rendered, _ = rendering.render_units(units, glossary=[], bibliography=[], annotations=[])
    assert "&lt;script&gt;" in rendered[0]["html_lines"][0]
    assert "<script>" not in rendered[0]["html_lines"][0]

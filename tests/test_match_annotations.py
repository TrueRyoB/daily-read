from __future__ import annotations

from app import rendering

_UNITS = [
    {"kind": "heading", "text": "1 Introduction", "level": 1},
    {"kind": "paragraph", "text": "Graph Neural Networks are widely used for relational data."},
    {"kind": "paragraph", "text": "Graph Neural Networks also appear in citation \x00CITE:b0\x00[1]\x00/CITE\x00 work."},
]


def test_finds_quote_via_prefix_and_suffix_in_correct_unit():
    annotations = [
        {
            "id": 1,
            "quote": "Graph Neural Networks",
            "prefix": "",
            "suffix": " are widely",
            "note": "key term",
        }
    ]
    matches, matched_ids = rendering.match_annotations(_UNITS, annotations)
    assert matched_ids == {1}
    assert matches == {1: [1]}  # the first paragraph (index 1), not the second


def test_falls_back_to_quote_only_when_surrounding_context_changed():
    # prefix/suffix no longer match (paper was reprocessed and wording
    # around the quote changed slightly), but the bare quote still exists.
    annotations = [
        {
            "id": 1,
            "quote": "Graph Neural Networks",
            "prefix": "this no longer matches ",
            "suffix": " nor does this",
            "note": "note",
        }
    ]
    matches, matched_ids = rendering.match_annotations(_UNITS, annotations)
    assert matched_ids == {1}
    assert 1 in matches[1]


def test_marks_not_found_when_quote_no_longer_present():
    annotations = [{"id": 1, "quote": "this text was removed entirely", "prefix": "", "suffix": "", "note": "n"}]
    matches, matched_ids = rendering.match_annotations(_UNITS, annotations)
    assert matched_ids == set()
    assert matches == {}


def test_ignores_figure_ref_units():
    units = [{"kind": "figure_ref", "figure_id": "figure-1"}]
    annotations = [{"id": 1, "quote": "figure-1", "prefix": "", "suffix": "", "note": "n"}]
    matches, matched_ids = rendering.match_annotations(units, annotations)
    assert matched_ids == set()


def test_first_occurrence_wins_when_quote_appears_in_multiple_units():
    # Documents the known, accepted limitation: an annotation always
    # resolves to the first unit containing its quote in reading order.
    annotations = [{"id": 1, "quote": "Graph Neural Networks", "prefix": "", "suffix": "", "note": "n"}]
    matches, _ = rendering.match_annotations(_UNITS, annotations)
    assert list(matches.keys()) == [1]  # index 1, not index 2


def test_matches_against_visible_citation_label_not_raw_placeholder():
    # The frontend captures quote/prefix/suffix from the browser's visible
    # textContent, which already shows "[1]" -- not the raw
    # "\x00CITE:b0\x00[1]\x00/CITE\x00" wrapper still present in unit["text"].
    annotations = [{"id": 1, "quote": "citation [1] work", "prefix": "", "suffix": "", "note": "n"}]
    matches, matched_ids = rendering.match_annotations(_UNITS, annotations)
    assert matched_ids == {1}
    assert matches == {2: [1]}


def test_empty_quote_is_never_matched():
    annotations = [{"id": 1, "quote": "", "prefix": "", "suffix": "", "note": "n"}]
    matches, matched_ids = rendering.match_annotations(_UNITS, annotations)
    assert matched_ids == set()

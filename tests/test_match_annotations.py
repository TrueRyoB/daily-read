from __future__ import annotations

from app import rendering

_UNITS = [
    {"kind": "heading", "text": "1 Introduction", "level": 1},
    {"kind": "paragraph", "text": "Graph Neural Networks are widely used for relational data."},
    {"kind": "paragraph", "text": "Graph Neural Networks also appear in citation \x00CITE:b0\x00[1]\x00/CITE\x00 work."},
]


def _ids(matches: dict) -> dict:
    """Collapses the {unit_index: [{"annotation_id","start","end"}, ...]}
    shape down to {unit_index: [annotation_id, ...]} for tests that only
    care about which unit(s) got matched, not the exact character range."""
    return {idx: [m["annotation_id"] for m in marks] for idx, marks in matches.items()}


def test_parse_annotation_note_splits_quotes_from_comment():
    parsed = rendering.parse_annotation_note("> Graph Neural Networks\nthis is my comment\n> also appear")
    assert parsed["quotes"] == ["Graph Neural Networks", "also appear"]
    assert parsed["comment"] == "this is my comment"


def test_parse_annotation_note_ignores_blank_and_bare_gt_lines():
    parsed = rendering.parse_annotation_note("> \n\ncomment only\n>   ")
    assert parsed["quotes"] == []
    assert parsed["comment"] == "comment only"


def test_finds_quoted_line_in_correct_unit():
    annotations = [{"id": 1, "note": "> Graph Neural Networks are widely\nkey term"}]
    matches, matched_ids = rendering.match_annotations(_UNITS, annotations)
    assert matched_ids == {1}
    assert _ids(matches) == {1: [1]}  # the first paragraph (index 1), not the second


def test_match_reports_the_exact_character_range_of_the_quote():
    units = [{"kind": "paragraph", "text": "some prefix text then the target phrase and a suffix"}]
    annotations = [{"id": 1, "note": "> the target phrase"}]
    matches, _ = rendering.match_annotations(units, annotations)
    mark = matches[0][0]
    text = units[0]["text"]
    assert text[mark["start"] : mark["end"]] == "the target phrase"


def test_marks_not_found_when_quote_no_longer_present():
    annotations = [{"id": 1, "note": "> this text was removed entirely"}]
    matches, matched_ids = rendering.match_annotations(_UNITS, annotations)
    assert matched_ids == set()
    assert matches == {}


def test_ignores_figure_ref_units():
    units = [{"kind": "figure_ref", "figure_id": "figure-1"}]
    annotations = [{"id": 1, "note": "> figure-1"}]
    matches, matched_ids = rendering.match_annotations(units, annotations)
    assert matched_ids == set()


def test_first_occurrence_wins_when_quote_appears_in_multiple_units():
    # Documents the known, accepted limitation: a quote always resolves to
    # the first unit containing it in reading order.
    annotations = [{"id": 1, "note": "> Graph Neural Networks"}]
    matches, _ = rendering.match_annotations(_UNITS, annotations)
    assert list(matches.keys()) == [1]  # index 1, not index 2


def test_matches_against_visible_citation_label_not_raw_placeholder():
    # A typed quote is compared against the browser's visible textContent
    # ("[1]"), not the raw "\x00CITE:b0\x00[1]\x00/CITE\x00" wrapper still
    # present in unit["text"].
    annotations = [{"id": 1, "note": "> citation [1] work"}]
    matches, matched_ids = rendering.match_annotations(_UNITS, annotations)
    assert matched_ids == {1}
    assert _ids(matches) == {2: [1]}


def test_annotation_with_no_quote_lines_is_never_matched():
    annotations = [{"id": 1, "note": "just musings, no quote"}]
    matches, matched_ids = rendering.match_annotations(_UNITS, annotations)
    assert matched_ids == set()


def test_one_annotation_with_n_quotes_marks_every_matched_unit():
    annotations = [
        {
            "id": 1,
            "note": "> Graph Neural Networks are widely\nfirst thought\n> also appear in citation [1] work\nsecond thought",
        }
    ]
    matches, matched_ids = rendering.match_annotations(_UNITS, annotations)
    assert matched_ids == {1}
    assert _ids(matches) == {1: [1], 2: [1]}


def test_found_is_true_if_at_least_one_of_n_quotes_matches():
    annotations = [{"id": 1, "note": "> this quote does not exist\n> Graph Neural Networks are widely"}]
    _, matched_ids = rendering.match_annotations(_UNITS, annotations)
    assert matched_ids == {1}


def test_two_quotes_of_the_same_annotation_hitting_the_same_unit_both_recorded():
    # Not deduped -- each is a legitimately distinct character range within
    # the same unit, so both get their own <mark> at render time.
    annotations = [{"id": 1, "note": "> Graph Neural Networks are widely\n> widely used for relational data"}]
    matches, _ = rendering.match_annotations(_UNITS, annotations)
    assert _ids(matches) == {1: [1, 1]}
    assert len(matches[1]) == 2

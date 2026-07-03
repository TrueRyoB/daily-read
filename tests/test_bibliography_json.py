from __future__ import annotations

import json

from app import rendering


def test_bibliography_json_builds_full_reference_label():
    bibliography = [
        {
            "bib_id": "b0",
            "index": 1,
            "authors": ["M A Bedau", "J S Mccaskill"],
            "title": "Open problems in artificial life",
            "year": "2000",
            "url": None,
        }
    ]
    payload = json.loads(rendering.bibliography_json(bibliography))
    assert payload == [
        {"bib_id": "b0", "label": "[M A Bedau, J S Mccaskill. (2000) Open problems in artificial life]"}
    ]


def test_bibliography_json_handles_missing_authors_and_year():
    bibliography = [{"bib_id": "b1", "index": 2, "authors": [], "title": "Untitled Work", "year": None, "url": None}]
    payload = json.loads(rendering.bibliography_json(bibliography))
    assert payload == [{"bib_id": "b1", "label": "[Untitled Work]"}]


def test_bibliography_json_empty_list():
    assert json.loads(rendering.bibliography_json([])) == []

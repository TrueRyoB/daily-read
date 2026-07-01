"""HTML-specific presentation logic for the reading view.

Kept out of pipeline.py deliberately: content.json is a plain structured
artifact (units/glossary/figures), not tied to any one rendering choice.
This module is what turns that structure into glossary-annotated HTML at
request time.
"""

from __future__ import annotations

import html
import json
import re


def render_units(units: list[dict], glossary: list[dict]) -> list[dict]:
    """Attach glossary-annotated `html` to paragraph/heading units.

    figure_ref units pass through unchanged; the template resolves them
    against the figures list separately.
    """
    annotate = _build_annotator([entry["term"] for entry in glossary])
    rendered = []
    for unit in units:
        if unit["kind"] == "figure_ref":
            rendered.append(unit)
        else:
            rendered.append({**unit, "html": annotate(unit["text"])})
    return rendered


def glossary_json(glossary: list[dict]) -> str:
    """Serialize the glossary for reader.js to build its popover lookup from."""
    return json.dumps(glossary, ensure_ascii=False)


def _build_annotator(terms: list[str]):
    unique_terms = sorted({html.escape(t) for t in terms if t}, key=len, reverse=True)
    pattern = (
        re.compile(r"\b(" + "|".join(re.escape(t) for t in unique_terms) + r")\b")
        if unique_terms
        else None
    )

    def annotate(text: str) -> str:
        escaped = html.escape(text)
        if pattern is None:
            return escaped
        return pattern.sub(
            lambda m: f'<span class="gloss" data-term="{m.group(1)}" tabindex="0">{m.group(1)}</span>',
            escaped,
        )

    return annotate

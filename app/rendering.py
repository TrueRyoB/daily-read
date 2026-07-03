"""HTML-specific presentation logic for the reading view.

Kept out of pipeline.py deliberately: content.json is a plain structured
artifact (units/glossary/figures), not tied to any one rendering choice.
This module is what turns that structure into glossary-annotated HTML at
request time.
"""

from __future__ import annotations

import html
import json
import os
import re
from urllib.parse import quote_plus

from app.glossary.base import normalize_term_key
from app.models import CITATION_PLACEHOLDER_RE, FIGURE_MENTION_PLACEHOLDER_RE

_DEFAULT_SEARCH_ENGINE_URL_TEMPLATE = "https://www.google.com/search?q={query}"


def filter_known_terms(glossary: list[dict], known_term_keys: set[str]) -> list[dict]:
    """Drop glossary entries the reader has already marked as known
    (plan/04-b) -- applied at display time (not baked into content.json at
    pipeline time) so marking a term known instantly hides it from every
    paper, including ones already processed before the term was marked."""
    if not known_term_keys:
        return glossary
    return [e for e in glossary if normalize_term_key(e["term"]) not in known_term_keys]


def render_units(units: list[dict], glossary: list[dict], bibliography: list[dict] | None = None) -> list[dict]:
    """Attach glossary-annotated `html` to paragraph/heading units, and a
    stable `anchor_id` (e.g. "heading-3") to heading units so both the
    heading itself and a table-of-contents entry pointing at it (plan/03-e)
    agree on the same id.

    figure_ref units pass through unchanged; the template resolves them
    against the figures list separately. `bibliography` is optional so old
    content.json (from before plan/03-c) without a "bibliography" key still
    renders -- citations just won't be linked for those.
    """
    bib_by_id = {b["bib_id"]: b for b in (bibliography or [])}
    annotate = _build_annotator([entry["term"] for entry in glossary], bib_by_id)
    rendered = []
    heading_count = 0
    for unit in units:
        if unit["kind"] == "figure_ref":
            rendered.append(unit)
        elif unit["kind"] == "heading":
            heading_count += 1
            rendered.append({**unit, "html": annotate(unit["text"]), "anchor_id": f"heading-{heading_count}"})
        else:
            rendered.append({**unit, "html": annotate(unit["text"])})
    return rendered


def table_of_contents(rendered_units: list[dict]) -> list[dict]:
    """Build {level, text, anchor_id} entries for the TOC nav (plan/03-e)
    from heading units already anchor-tagged by render_units."""
    return [
        {"level": u["level"], "text": u["text"], "anchor_id": u["anchor_id"]}
        for u in rendered_units
        if u["kind"] == "heading"
    ]


def glossary_json(glossary: list[dict]) -> str:
    """Serialize the glossary for reader.js to build its popover lookup from."""
    return json.dumps(glossary, ensure_ascii=False)


def figures_json(figures: list[dict], paper_id: str) -> str:
    """Serialize figures for reader.js's mobile modal and desktop
    independent-scroll/highlight behavior (plan/01) -- same data source for
    both, keyed by figure_id."""
    payload = [
        {
            "figure_id": fig["figure_id"],
            "label": fig["label"],
            "caption": fig["caption"],
            "image_url": f"/papers/{paper_id}/figures/{fig['image_path'].rsplit('/', 1)[-1]}",
        }
        for fig in figures
    ]
    return json.dumps(payload, ensure_ascii=False)


def match_annotations(units: list[dict], annotations: list[dict]) -> tuple[dict[int, list[int]], set[int]]:
    """Re-find each saved annotation's quote against the *current* units
    (plan/05-g) -- annotations live in SQLite, independent of content.json,
    so a paper reprocess (which can change unit wording) must degrade
    gracefully instead of crashing or silently losing notes.

    Two-pass matching per annotation: prefix+quote+suffix (strict) first,
    then quote alone (loose) if that fails. First matching unit in reading
    order wins if the quote appears more than once -- a known, documented
    limitation, not a crash.

    Returns ({unit_index: [annotation_id, ...]}, {matched_annotation_id}).
    Unmatched annotations are simply absent from both -- callers should
    treat "not in matched ids" as "flag as not-found," not an error.
    """
    unit_texts = [
        _visible_text(u.get("text", "")) if u["kind"] in ("heading", "paragraph") else None for u in units
    ]
    matches: dict[int, list[int]] = {}
    matched_ids: set[int] = set()

    for ann in annotations:
        quote = ann.get("quote") or ""
        if not quote:
            continue
        strict = f"{ann.get('prefix', '')}{quote}{ann.get('suffix', '')}"
        found_index = _find_unit_index(unit_texts, strict)
        if found_index is None:
            found_index = _find_unit_index(unit_texts, quote)
        if found_index is not None:
            matches.setdefault(found_index, []).append(ann["id"])
            matched_ids.add(ann["id"])

    return matches, matched_ids


def _find_unit_index(unit_texts: list[str | None], needle: str) -> int | None:
    for idx, text in enumerate(unit_texts):
        if text is not None and needle in text:
            return idx
    return None


def _visible_text(text: str) -> str:
    """The plain text a browser's `textContent` would show for this unit
    (citation/figure-mention placeholders resolved to their visible label,
    .gloss spans don't change visible text at all) -- what the frontend
    actually captured `quote`/`prefix`/`suffix` from, so matching happens
    on the same string shape."""
    return FIGURE_MENTION_PLACEHOLDER_RE.sub(r"\2", CITATION_PLACEHOLDER_RE.sub(r"\2", text))


def annotations_json(annotations: list[dict]) -> str:
    """Serialize annotations for reader.js's queue/marker wiring."""
    return json.dumps(annotations, ensure_ascii=False)


def search_url(term: str, paper_title: str) -> str:
    """Build the "look this up" link for a pre-reading term (plan/04-c,
    revised in plan/05-d). The paper's title is appended as cheap,
    always-available context so a search for an ambiguous short term (e.g.
    "GAT") isn't completely bare -- a lightweight stand-in for "infer the
    paper's subject and use it as context," using data we already have.

    The search engine is configurable via the SEARCH_ENGINE_URL_TEMPLATE
    env var (must contain a "{query}" placeholder) because there is no way
    for a page's hyperlink to invoke "the browser's default search engine"
    -- that's an address-bar-only browser feature a page can't trigger.
    Default is Google.
    """
    query = f'"{term}" {paper_title}'.strip()
    template = os.environ.get("SEARCH_ENGINE_URL_TEMPLATE", _DEFAULT_SEARCH_ENGINE_URL_TEMPLATE)
    return template.format(query=quote_plus(query))


def _build_annotator(terms: list[str], bib_by_id: dict[str, dict]):
    unique_terms = sorted({html.escape(t) for t in terms if t}, key=len, reverse=True)
    pattern = (
        re.compile(r"\b(" + "|".join(re.escape(t) for t in unique_terms) + r")\b")
        if unique_terms
        else None
    )

    def annotate(text: str) -> str:
        escaped = html.escape(text)
        if pattern is not None:
            escaped = pattern.sub(
                lambda m: f'<span class="gloss" data-term="{m.group(1)}" tabindex="0">{m.group(1)}</span>',
                escaped,
            )
        # Placeholders are substituted last, after escaping/glossary
        # annotation, so their embedded NUL-byte delimiters never have to
        # survive intermediate regex passes.
        escaped = CITATION_PLACEHOLDER_RE.sub(lambda m: _citation_link(m, bib_by_id), escaped)
        return FIGURE_MENTION_PLACEHOLDER_RE.sub(_figure_mention_link, escaped)

    return annotate


def _citation_link(match: re.Match, bib_by_id: dict[str, dict]) -> str:
    # match.group(1) is usually one bib_id, but plan/05-a merges GROBID's
    # split combined citations ("[1, 16]") into one placeholder carrying
    # multiple comma-joined ids -- the first one is used as the single
    # representative link target (one <a> can only point at one place).
    bib_id = match.group(1).split(",")[0]
    label = match.group(2)
    entry = bib_by_id.get(bib_id)
    href = entry["url"] if entry and entry.get("url") else f"#bib-{bib_id}"
    return f'<a class="citation" href="{html.escape(href, quote=True)}">{label}</a>'


def _figure_mention_link(match: re.Match) -> str:
    # Reuses the .figure-jump class/click-handler (reader.js) that already
    # drives the desktop panel-scroll / mobile-modal behavior -- plan/05-b
    # removed the old manually-inserted "figure-jump" button, so this
    # inline mention is now the only place that class is emitted from.
    figure_id, label = match.group(1), match.group(2)
    return f'<a class="figure-jump" href="#{html.escape(figure_id, quote=True)}">{label}</a>'

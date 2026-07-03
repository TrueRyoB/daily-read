"""Wires the independent stages together: resolve source -> extract ->
normalize layout -> glossary -> persist. This is the only module that
knows about all of them; pipeline-level policy (id generation, word count,
reading-time estimate, title guessing) lives here, not in the stages.

Two public entry points per source type (plan/05-f):
  - process_upload/process_url: synchronous, fully blocking, return once
    the paper is completely processed. Used by tests and anything that
    wants one call -> one finished paper.
  - start_upload_processing/start_url_processing: return almost
    immediately (id allocated, a "processing" row inserted) and do the
    actual work in a background thread. This is what main.py's real
    upload/URL routes use, so the request handler never blocks on a slow
    GROBID call.
Both share _process_pdf, the actual GROBID/parse/glossary/persist work,
which is deliberately agnostic to how its result gets written into the
`papers` table (INSERT for the sync path, UPDATE for the background path).

A plain threading.Thread (not FastAPI's BackgroundTasks) runs the
background path deliberately: TestClient drives BackgroundTasks to
completion as part of the same ASGI call, which would make the
"processing" intermediate state unobservable in tests; a bare thread keeps
running independently of the request/response lifecycle, which is also
just what's needed here (single-user, one paper at a time, no scaling
concerns).
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app import db, storage
from app.glossary.factory import get_extractor
from app.ingestion.source_resolver import ResolvedSource, resolve_upload, resolve_url
from app.models import CITATION_PLACEHOLDER_RE, FIGURE_MENTION_PLACEHOLDER_RE, Figure, NormalizedDocument, PaperContent
from app.pdf.grobid_client import extract_tei
from app.pdf.tei_parse import parse_tei

_WORDS_PER_MINUTE = 200


def process_upload(filename: str, pdf_bytes: bytes) -> str:
    """Synchronous, fully blocking."""
    resolved = resolve_upload(filename, pdf_bytes)
    return _run_pipeline_sync(resolved.pdf_bytes, resolved.source_label)


def process_url(url: str) -> str:
    """Synchronous, fully blocking."""
    resolved = resolve_url(url)
    return _run_pipeline_sync(resolved.pdf_bytes, resolved.source_label)


def _run_pipeline_sync(pdf_bytes: bytes, source_label: str) -> str:
    paper_id = uuid.uuid4().hex[:12]
    storage.paper_dir(paper_id).mkdir(parents=True, exist_ok=True)
    title, word_count, est_minutes = _process_pdf(paper_id, pdf_bytes)

    conn = db.get_connection()
    try:
        db.insert_paper(
            conn,
            paper_id=paper_id,
            title=title,
            source=source_label,
            created_at=datetime.now(timezone.utc).isoformat(),
            word_count=word_count,
            est_minutes=est_minutes,
        )  # status defaults to "done"
    finally:
        conn.close()

    return paper_id


def start_upload_processing(filename: str, pdf_bytes: bytes) -> str:
    """Fast: returns a paper_id almost immediately; the real work happens
    in a background thread. Poll GET /papers/{id}/status."""
    return _start_processing(source_label=filename, resolve=lambda: resolve_upload(filename, pdf_bytes))


def start_url_processing(url: str) -> str:
    return _start_processing(source_label=url, resolve=lambda: resolve_url(url))


def _start_processing(source_label: str, resolve: Callable[[], ResolvedSource]) -> str:
    paper_id = uuid.uuid4().hex[:12]
    storage.paper_dir(paper_id).mkdir(parents=True, exist_ok=True)

    conn = db.get_connection()
    try:
        db.insert_paper(
            conn,
            paper_id=paper_id,
            title=source_label,  # placeholder; replaced by the real title once parsed
            source=source_label,
            created_at=datetime.now(timezone.utc).isoformat(),
            word_count=0,
            est_minutes=0,
            status="processing",
        )
    finally:
        conn.close()

    threading.Thread(target=_process_in_background, args=(paper_id, resolve), daemon=True).start()
    return paper_id


def _process_in_background(paper_id: str, resolve: Callable[[], ResolvedSource]) -> None:
    """Runs off the request thread. Must never let an exception escape
    uncaught: nothing is watching this thread, so an uncaught exception
    here would leave the paper stuck at status="processing" forever with
    the UI spinning indefinitely instead of showing an error."""
    try:
        resolved = resolve()
        title, word_count, est_minutes = _process_pdf(paper_id, resolved.pdf_bytes)
        conn = db.get_connection()
        try:
            db.mark_paper_done(conn, paper_id, title=title, word_count=word_count, est_minutes=est_minutes)
        finally:
            conn.close()
    except Exception as exc:
        conn = db.get_connection()
        try:
            db.mark_paper_error(conn, paper_id, str(exc))
        finally:
            conn.close()


def _process_pdf(paper_id: str, pdf_bytes: bytes) -> tuple[str, int, int]:
    """The actual GROBID/parse/glossary/persist work for an
    already-allocated paper_id. Deliberately does not touch the `papers`
    table itself -- returns (title, word_count, est_minutes) for the
    caller to persist however fits its flow (INSERT vs UPDATE)."""
    pdf_path = storage.original_pdf_path(paper_id)
    pdf_path.write_bytes(pdf_bytes)

    tei_xml = extract_tei(str(pdf_path))
    storage.tei_xml_path(paper_id).write_text(tei_xml, encoding="utf-8")
    normalized = parse_tei(tei_xml, str(pdf_path))
    _write_figures(paper_id, normalized.figures)

    # Joined with ". " (not just " "): a plain space would let a heading's
    # trailing word glue onto the next paragraph's opening acronym
    # definition (e.g. "1 Introduction" + "Graph Neural Network (GNN)..."),
    # which makes heuristic.py's greedy phrase-before-"(ABBR)" regex pull
    # "Introduction" into the phrase and silently reject the whole match
    # (initials no longer equal the acronym). A hard separator keeps each
    # unit's text from bleeding into its neighbor for that regex.
    #
    # Citation and figure-mention placeholders (plan/03-c, plan/05-b) are
    # unwrapped to their plain label ("[1]", "1") before joining: the raw
    # "\x00CITE:b0\x00...\x00/CITE\x00"/"\x00FIGREF:...\x00...\x00/FIGREF\x00"
    # wrappers contain the literal words "CITE"/"FIGREF" surrounded by word
    # boundaries, which would otherwise get counted as frequent capitalized
    # candidate terms by the glossary heuristic (one paper can easily have
    # 50+ citations/figure mentions, all matching "CITE"/"FIGREF").
    full_text = ". ".join(
        _strip_placeholders(u.text) for u in normalized.units if u.kind in ("heading", "paragraph")
    )
    known_names = list(normalized.authors) + [name for entry in normalized.bibliography for name in entry.authors]
    glossary = get_extractor().extract(full_text, known_names)

    title = normalized.title or _guess_title(normalized)
    word_count = len(full_text.split())
    est_minutes = max(1, round(word_count / _WORDS_PER_MINUTE))

    content = PaperContent(
        title=title,
        units=normalized.units,
        figures=normalized.figures,
        glossary=glossary,
        word_count=word_count,
        est_minutes=est_minutes,
        authors=normalized.authors,
        abstract=normalized.abstract,
        bibliography=normalized.bibliography,
    )
    storage.content_json_path(paper_id).write_text(
        json.dumps(_content_to_json(content), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return title, word_count, est_minutes


def _write_figures(paper_id: str, figures: list[Figure]) -> None:
    if not figures:
        return
    figures_dir = storage.figures_dir(paper_id)
    figures_dir.mkdir(parents=True, exist_ok=True)
    for figure in figures:
        (figures_dir / Path(figure.image_path).name).write_bytes(figure.image_bytes)


def _strip_placeholders(text: str) -> str:
    return FIGURE_MENTION_PLACEHOLDER_RE.sub(r"\2", CITATION_PLACEHOLDER_RE.sub(r"\2", text))


def _guess_title(normalized: NormalizedDocument) -> str:
    for unit in normalized.units:
        if unit.kind == "heading":
            return _strip_placeholders(unit.text)
    for unit in normalized.units:
        if unit.kind == "paragraph" and unit.text:
            return _strip_placeholders(unit.text)[:80]
    return "Untitled paper"


def _content_to_json(content: PaperContent) -> dict:
    data = asdict(content)
    for figure in data["figures"]:
        figure.pop("image_bytes", None)
    return data

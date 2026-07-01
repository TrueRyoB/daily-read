"""Wires the independent stages together: resolve source -> extract ->
normalize layout -> glossary -> persist. This is the only module that
knows about all of them; pipeline-level policy (id generation, word count,
reading-time estimate, title guessing) lives here, not in the stages.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app import db, storage
from app.glossary.factory import get_extractor
from app.ingestion.source_resolver import resolve_upload, resolve_url
from app.models import Figure, NormalizedDocument, PaperContent
from app.pdf.extraction import extract_pages
from app.pdf.layout import normalize_pages

_WORDS_PER_MINUTE = 200


def process_upload(filename: str, pdf_bytes: bytes) -> str:
    resolved = resolve_upload(filename, pdf_bytes)
    return _run_pipeline(resolved.pdf_bytes, resolved.source_label)


def process_url(url: str) -> str:
    resolved = resolve_url(url)
    return _run_pipeline(resolved.pdf_bytes, resolved.source_label)


def _run_pipeline(pdf_bytes: bytes, source_label: str) -> str:
    paper_id = uuid.uuid4().hex[:12]
    paper_data_dir = storage.paper_dir(paper_id)
    paper_data_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = storage.original_pdf_path(paper_id)
    pdf_path.write_bytes(pdf_bytes)

    pages = extract_pages(str(pdf_path))
    normalized = normalize_pages(pages)
    _write_figures(paper_id, normalized.figures)

    full_text = " ".join(u.text for u in normalized.units if u.kind in ("heading", "paragraph"))
    glossary = get_extractor().extract(full_text)

    title = _guess_title(normalized)
    word_count = len(full_text.split())
    est_minutes = max(1, round(word_count / _WORDS_PER_MINUTE))

    content = PaperContent(
        title=title,
        units=normalized.units,
        figures=normalized.figures,
        glossary=glossary,
        word_count=word_count,
        est_minutes=est_minutes,
    )
    storage.content_json_path(paper_id).write_text(
        json.dumps(_content_to_json(content), ensure_ascii=False, indent=2), encoding="utf-8"
    )

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
        )
    finally:
        conn.close()

    return paper_id


def _write_figures(paper_id: str, figures: list[Figure]) -> None:
    if not figures:
        return
    figures_dir = storage.figures_dir(paper_id)
    figures_dir.mkdir(parents=True, exist_ok=True)
    for figure in figures:
        (figures_dir / Path(figure.image_path).name).write_bytes(figure.image_bytes)


def _guess_title(normalized: NormalizedDocument) -> str:
    for unit in normalized.units:
        if unit.kind == "heading":
            return unit.text
    for unit in normalized.units:
        if unit.kind == "paragraph" and unit.text:
            return unit.text[:80]
    return "Untitled paper"


def _content_to_json(content: PaperContent) -> dict:
    data = asdict(content)
    for figure in data["figures"]:
        figure.pop("image_bytes", None)
    return data

"""FastAPI app: history list + upload form + reading view.

Single-user, localhost-only personal tool -- no auth, no multi-tenant
concerns. Processing runs in a background thread (plan/05-f): GROBID calls
can take anywhere from seconds to minutes depending on PDF size, so
submit_paper returns almost immediately (paper allocated, status
"processing") and the reading-view route itself renders a small
processing/status page until the background thread flips the paper to
"done" (or "error"). See pipeline.py's module docstring for why a plain
threading.Thread is used instead of FastAPI's BackgroundTasks.
"""

from __future__ import annotations

import calendar as _calendar_module
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import db, i18n, pipeline, rendering, storage, version

_APP_DIR = Path(__file__).parent
_LOCALE_COOKIE = "lang"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
logger.info("daily-read starting at commit %s", version.VERSION_LABEL)

app = FastAPI(title="daily-read")
templates = Jinja2Templates(directory=str(_APP_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(_APP_DIR / "static")), name="static")


def _locale_context(request: Request) -> tuple[str, dict]:
    """Resolve the UI locale (plan/05-h): an explicit `?lang=` query param
    wins and is persisted to a cookie for subsequent requests (most links
    in the app don't carry `?lang=` themselves); otherwise the cookie is
    used; otherwise Japanese."""
    query_lang = request.query_params.get("lang")
    locale = i18n.resolve_locale(query_lang or request.cookies.get(_LOCALE_COOKIE))
    return locale, {"locale": locale, "t": i18n.translator(locale)}


def _render(request: Request, template_name: str, context: dict) -> HTMLResponse:
    locale, locale_ctx = _locale_context(request)
    response = templates.TemplateResponse(request, template_name, {**context, **locale_ctx})
    if request.query_params.get("lang"):
        response.set_cookie(_LOCALE_COOKIE, locale, max_age=60 * 60 * 24 * 365)
    return response


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    conn = db.get_connection()
    try:
        papers = db.list_papers(conn)
    finally:
        conn.close()
    return _render(request, "index.html", {"papers": papers})


@app.get("/calendar", response_class=HTMLResponse)
def calendar_view(request: Request, month: str | None = None) -> HTMLResponse:
    """Interpretation-log entries grouped by the date the reader logged
    them, calendar-grid style (plan/07-troubleshooting-backlog.md#b-4改訂).
    Deliberately keyed by `interpretations.date`, not `papers.created_at`:
    parsing a PDF isn't the same as having read/understood it. `?month=
    YYYY-MM` navigates; defaults to the current month."""
    now = datetime.now(timezone.utc)
    year, month_num = now.year, now.month
    if month:
        try:
            year, month_num = (int(part) for part in month.split("-", 1))
        except ValueError:
            pass  # malformed ?month= -- fall back to the current month

    conn = db.get_connection()
    try:
        interpretations = db.list_interpretations_in_month(conn, year, month_num)
        papers = db.list_papers(conn)
    finally:
        conn.close()

    calendar_data = rendering.build_calendar_month(interpretations, year, month_num)
    prev_year, prev_month = (year - 1, 12) if month_num == 1 else (year, month_num - 1)
    next_year, next_month = (year + 1, 1) if month_num == 12 else (year, month_num + 1)

    return _render(
        request,
        "calendar.html",
        {
            "calendar": calendar_data,
            "month_name": _calendar_module.month_name[month_num],
            "prev_month": f"{prev_year:04d}-{prev_month:02d}",
            "next_month": f"{next_year:04d}-{next_month:02d}",
            "papers": papers,  # populates the "related papers" picker in the create form
            "interpretations_json": rendering.interpretations_json(interpretations),
        },
    )


@app.post("/interpretations")
def create_interpretation(
    date: str = Body(..., embed=True),
    memo: str = Body("", embed=True),
    paper_ids: list[str] = Body([], embed=True),
    links: list[str] = Body([], embed=True),
) -> dict:
    """A reading/interpretation log entry (plan/07-troubleshooting-
    backlog.md#b-4改訂). `date` is free-form user input, deliberately
    never validated against "today" or any range: this is a self-
    contained personal log, not something shown to anyone else. A "just
    musings" entry with zero papers attached is explicitly allowed."""
    if not date.strip():
        raise HTTPException(status_code=400, detail="dateは必須です。")
    cleaned_links = [link.strip() for link in links if link.strip()]
    conn = db.get_connection()
    try:
        return db.create_interpretation(
            conn, date=date.strip(), memo=memo.strip(), paper_ids=paper_ids, links=cleaned_links
        )
    finally:
        conn.close()


@app.delete("/interpretations/{interpretation_id}")
def remove_interpretation(interpretation_id: int) -> dict:
    conn = db.get_connection()
    try:
        deleted = db.delete_interpretation(conn, interpretation_id)
    finally:
        conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="記録が見つかりません")
    return {"status": "ok"}


@app.post("/papers")
async def submit_paper(
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
) -> RedirectResponse:
    # Both start_*_processing calls return almost immediately (id
    # allocated, a "processing" row inserted) -- the actual GROBID/parse
    # work happens in a background thread. Failures during that work show
    # up as status="error" on the processing page, not as an HTTP error
    # here (plan/05-f).
    if file is not None and file.filename:
        pdf_bytes = await file.read()
        # plan/07-troubleshooting-backlog.md#b-3: a byte-for-byte duplicate
        # of an already-processed (or in-progress) upload is redirected to
        # the existing paper instead of paying for another GROBID call.
        # Upload-only for now: an equivalent check for URL submissions
        # would need resolving the URL synchronously here (defeating the
        # point of the background-thread design) or a more involved
        # "duplicate found mid-processing" state, neither implemented yet.
        existing_paper_id = pipeline.find_existing_paper_id(pdf_bytes)
        paper_id = existing_paper_id or pipeline.start_upload_processing(file.filename, pdf_bytes)
    elif url:
        paper_id = pipeline.start_url_processing(url)
    else:
        raise HTTPException(status_code=400, detail="PDFファイルまたはURLのどちらかを指定してください。")

    return RedirectResponse(url=f"/papers/{paper_id}", status_code=303)


@app.get("/papers/{paper_id}", response_class=HTMLResponse)
def read_paper(request: Request, paper_id: str) -> HTMLResponse:
    conn = db.get_connection()
    try:
        paper = db.get_paper(conn, paper_id)
        known_term_keys = db.known_term_keys(conn)
    finally:
        conn.close()
    if paper is None:
        raise HTTPException(status_code=404, detail="論文が見つかりません")

    if paper["status"] != "done":
        # Still processing, or failed -- content.json doesn't exist yet
        # (or never will, for "error"). processing.js polls
        # GET /papers/{id}/status and reloads this page once it flips to
        # "done" (plan/05-f).
        return _render(request, "processing.html", {"paper": paper, "paper_id": paper_id})

    content = json.loads(storage.content_json_path(paper_id).read_text(encoding="utf-8"))
    content.setdefault("bibliography", [])  # absent in content.json written before plan/03-c
    content["glossary"] = rendering.filter_known_terms(content["glossary"], known_term_keys)
    rendered_units = rendering.render_units(content["units"], content["glossary"], content["bibliography"])
    toc_entries = rendering.table_of_contents(rendered_units)
    # "concordance" entries are frequent terms the paper never defines and
    # no bundled dictionary covers either -- surface them as a pre-reading
    # checklist instead of only reactively, inline (plan/04-c).
    preread_terms = [e for e in content["glossary"] if e["source"] == "concordance"]

    # Annotations live entirely in SQLite (plan/05-g), independent of
    # content.json, so they're re-matched against whatever units currently
    # exist on every read rather than being baked in at pipeline time.
    conn = db.get_connection()
    try:
        annotations = db.list_annotations(conn, paper_id)
    finally:
        conn.close()
    unit_matches, matched_ids = rendering.match_annotations(content["units"], annotations)
    for annotation in annotations:
        annotation["found"] = annotation["id"] in matched_ids
    for unit_index, annotation_ids in unit_matches.items():
        rendered_units[unit_index]["annotation_ids"] = annotation_ids

    locale, _ = _locale_context(request)
    return _render(
        request,
        "paper.html",
        {
            "paper": paper,
            "paper_id": paper_id,
            "content": content,
            "rendered_units": rendered_units,
            "glossary_json": rendering.glossary_json(content["glossary"]),
            "figures_json": rendering.figures_json(content["figures"], paper_id),
            "bibliography_json": rendering.bibliography_json(content["bibliography"]),
            "preread_terms": preread_terms,
            "toc_entries": toc_entries,
            "search_url": rendering.search_url,
            "annotations": annotations,
            "annotations_json": rendering.annotations_json(annotations),
            "i18n_json": json.dumps(i18n.js_translations(locale), ensure_ascii=False),
        },
    )


@app.get("/papers/{paper_id}/status")
def paper_status(paper_id: str) -> dict:
    """Polled by processing.js every ~2s (plan/05-f). elapsed_seconds is
    computed from created_at, not tracked client-side, so reloading the
    processing page mid-wait still shows the correct elapsed time instead
    of resetting to 0."""
    conn = db.get_connection()
    try:
        paper = db.get_paper(conn, paper_id)
    finally:
        conn.close()
    if paper is None:
        raise HTTPException(status_code=404, detail="論文が見つかりません")

    if paper["status"] == "error":
        return {"status": "error", "error_message": paper["error_message"]}
    if paper["status"] == "done":
        return {"status": "done"}

    created_at = datetime.fromisoformat(paper["created_at"])
    elapsed_seconds = max(0, int((datetime.now(timezone.utc) - created_at).total_seconds()))
    return {"status": "processing", "elapsed_seconds": elapsed_seconds}


@app.post("/papers/{paper_id}/annotations")
def create_annotation(
    paper_id: str,
    quote: str = Body(..., embed=True),
    prefix: str = Body("", embed=True),
    suffix: str = Body("", embed=True),
    note: str = Body(..., embed=True),
) -> dict:
    """Personal margin note anchored to a quoted substring (plan/05-g)."""
    if not quote.strip() or not note.strip():
        raise HTTPException(status_code=400, detail="quoteとnoteは必須です。")
    conn = db.get_connection()
    try:
        if db.get_paper(conn, paper_id) is None:
            raise HTTPException(status_code=404, detail="論文が見つかりません")
        return db.create_annotation(conn, paper_id=paper_id, quote=quote, prefix=prefix, suffix=suffix, note=note)
    finally:
        conn.close()


@app.put("/papers/{paper_id}/annotations/{annotation_id}")
def edit_annotation(paper_id: str, annotation_id: int, note: str = Body(..., embed=True)) -> dict:
    if not note.strip():
        raise HTTPException(status_code=400, detail="noteは必須です。")
    conn = db.get_connection()
    try:
        updated = db.update_annotation_note(conn, annotation_id, paper_id, note)
    finally:
        conn.close()
    if updated is None:
        raise HTTPException(status_code=404, detail="メモが見つかりません")
    return updated


@app.delete("/papers/{paper_id}/annotations/{annotation_id}")
def remove_annotation(paper_id: str, annotation_id: int) -> dict:
    conn = db.get_connection()
    try:
        deleted = db.delete_annotation(conn, annotation_id, paper_id)
    finally:
        conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="メモが見つかりません")
    return {"status": "ok"}


@app.post("/glossary/known-terms")
def mark_known_term(term: str = Body(..., embed=True)) -> dict:
    """Record that the reader already knows `term` (plan/04-b). Applies
    immediately across every paper -- see rendering.filter_known_terms."""
    conn = db.get_connection()
    try:
        db.mark_term_known(conn, term)
    finally:
        conn.close()
    return {"status": "ok"}


@app.get("/papers/{paper_id}/figures/{filename}")
def paper_figure(paper_id: str, filename: str) -> FileResponse:
    path = storage.figures_dir(paper_id) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="図が見つかりません")
    return FileResponse(path)

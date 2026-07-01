"""FastAPI app: history list + upload form + reading view.

Single-user, localhost-only personal tool -- no auth, no multi-tenant
concerns. Processing runs synchronously in the request handler: the
default heuristic pipeline does no network/LLM calls and finishes in well
under a second for a typical paper, so a background task queue would be
needless complexity today. Revisit if GLOSSARY_STRATEGY=llm ever makes
processing slow enough to want that.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import db, pipeline, rendering, storage

_APP_DIR = Path(__file__).parent

app = FastAPI(title="daily-read")
templates = Jinja2Templates(directory=str(_APP_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(_APP_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    conn = db.get_connection()
    try:
        papers = db.list_papers(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "index.html", {"papers": papers})


@app.post("/papers")
async def submit_paper(
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
) -> RedirectResponse:
    if file is not None and file.filename:
        pdf_bytes = await file.read()
        try:
            paper_id = pipeline.process_upload(file.filename, pdf_bytes)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"PDFの処理に失敗しました: {exc}") from exc
    elif url:
        try:
            paper_id = pipeline.process_url(url)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"URLの取得に失敗しました: {exc}") from exc
    else:
        raise HTTPException(status_code=400, detail="PDFファイルまたはURLのどちらかを指定してください。")

    return RedirectResponse(url=f"/papers/{paper_id}", status_code=303)


@app.get("/papers/{paper_id}", response_class=HTMLResponse)
def read_paper(request: Request, paper_id: str) -> HTMLResponse:
    conn = db.get_connection()
    try:
        paper = db.get_paper(conn, paper_id)
    finally:
        conn.close()
    if paper is None:
        raise HTTPException(status_code=404, detail="論文が見つかりません")

    content = json.loads(storage.content_json_path(paper_id).read_text(encoding="utf-8"))
    rendered_units = rendering.render_units(content["units"], content["glossary"])
    figures_by_id = {fig["figure_id"]: fig for fig in content["figures"]}

    return templates.TemplateResponse(
        request,
        "paper.html",
        {
            "paper": paper,
            "paper_id": paper_id,
            "content": content,
            "rendered_units": rendered_units,
            "figures_by_id": figures_by_id,
            "glossary_json": rendering.glossary_json(content["glossary"]),
        },
    )


@app.get("/papers/{paper_id}/figures/{filename}")
def paper_figure(paper_id: str, filename: str) -> FileResponse:
    path = storage.figures_dir(paper_id) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="図が見つかりません")
    return FileResponse(path)

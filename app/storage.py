"""Filesystem layout for processed papers.

data/
  daily-read.db            <- SQLite index (db.py): title, date, reading time
  papers/<id>/
    original.pdf
    tei.xml                <- raw GROBID response, kept for debugging (plan/03-b)
    content.json           <- normalized units + glossary + figure metadata
    figures/<figure_id>.<ext>
"""

from __future__ import annotations

from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PAPERS_DIR = DATA_DIR / "papers"


def paper_dir(paper_id: str) -> Path:
    return PAPERS_DIR / paper_id


def figures_dir(paper_id: str) -> Path:
    return paper_dir(paper_id) / "figures"


def original_pdf_path(paper_id: str) -> Path:
    return paper_dir(paper_id) / "original.pdf"


def tei_xml_path(paper_id: str) -> Path:
    return paper_dir(paper_id) / "tei.xml"


def content_json_path(paper_id: str) -> Path:
    return paper_dir(paper_id) / "content.json"

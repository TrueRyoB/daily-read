"""Shared test helpers -- plain functions, not pytest fixtures.

Kept separate from conftest.py because conftest is for fixtures pytest
auto-discovers; these are ordinary functions test modules import directly.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


def blank_pdf(tmp_path, width: int = 600, height: int = 800, pages: int = 1) -> str:
    """Write a synthetic multi-page PDF and return its path.

    Used instead of a committed binary PDF fixture so figure-cropping code
    (which needs a real, openable PDF at the coords' page number) can be
    exercised without shipping/licensing a real paper's PDF.
    """
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=width, height=height)
    path = tmp_path / "sample.pdf"
    doc.save(str(path))
    doc.close()
    return str(path)


def load_golden_tei() -> str:
    """Load the hand-authored GROBID TEI fixture (see the file's own header
    comment for what it covers and its accuracy caveats)."""
    return (_FIXTURES_DIR / "sample_fulltext.tei.xml").read_text(encoding="utf-8")

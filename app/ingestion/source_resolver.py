"""Resolve a user-provided PDF file or URL into raw PDF bytes.

Kept deliberately narrow: this module's only job is "get me the PDF bytes
and where they came from." PyMuPDF and the layout/glossary modules never
see a URL, only local bytes/paths -- title detection also happens later,
in pipeline.py, from the extracted content itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

_PDF_CONTENT_TYPE = "application/pdf"
_REQUEST_TIMEOUT = 20.0
_USER_AGENT = "daily-read/0.1 (personal reading-habit tool)"

_ARXIV_ABS_RE = re.compile(r"^https?://arxiv\.org/abs/(?P<id>[\w.\-]+)", re.IGNORECASE)


@dataclass
class ResolvedSource:
    pdf_bytes: bytes
    source_label: str  # original URL or uploaded filename, stored as Paper.source


def resolve_upload(filename: str, pdf_bytes: bytes) -> ResolvedSource:
    return ResolvedSource(pdf_bytes=pdf_bytes, source_label=filename)


def resolve_url(url: str, client: httpx.Client | None = None) -> ResolvedSource:
    """Download the PDF at `url`, or find and download the PDF it links to.

    Handles three cases, cheapest first:
      1. `url` is already a direct .pdf link -> download it.
      2. `url` is an arXiv abstract page -> rewrite to the known PDF path.
      3. Anything else -> fetch the page and take the first link containing
         ".pdf" (generic landing-page fallback, e.g. journal pages).
    """
    owns_client = client is None
    client = client or httpx.Client(
        follow_redirects=True, timeout=_REQUEST_TIMEOUT, headers={"User-Agent": _USER_AGENT}
    )
    try:
        arxiv_match = _ARXIV_ABS_RE.match(url)
        direct_url = f"https://arxiv.org/pdf/{arxiv_match.group('id')}" if arxiv_match else url

        response = client.get(direct_url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")

        if _PDF_CONTENT_TYPE in content_type or direct_url.lower().split("?")[0].endswith(".pdf"):
            return ResolvedSource(pdf_bytes=response.content, source_label=url)

        pdf_url = _find_pdf_link(direct_url, response.text)
        pdf_response = client.get(pdf_url)
        pdf_response.raise_for_status()
        return ResolvedSource(pdf_bytes=pdf_response.content, source_label=url)
    finally:
        if owns_client:
            client.close()


def _find_pdf_link(base_url: str, html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if ".pdf" in href.lower():
            return urljoin(base_url, href)
    raise ValueError(f"Could not find a PDF link on page: {base_url}")

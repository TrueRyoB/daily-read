"""Raw PDF extraction via PyMuPDF only -- no other parsing dependency.

Pulls per-page text blocks (with bbox + font metadata, needed by layout.py
for column detection and heading detection) and embedded images (needed for
figure separation). Deliberately dumb: no column/reading-order logic here,
that lives in layout.py so the two concerns stay independently testable.
"""

from __future__ import annotations

import fitz  # PyMuPDF

from app.models import ImageBlock, PageContent, TextBlock

_BOLD_FLAG = 1 << 4  # fitz span flag bit for bold text
_MIN_IMAGE_SIDE = 30  # points; filters out bullet/logo-sized decorative images


def extract_pages(pdf_path: str) -> list[PageContent]:
    """Extract per-page text blocks and images from a PDF file on disk."""
    pages: list[PageContent] = []
    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc):
            page_number = page_index + 1
            pages.append(
                PageContent(
                    page_number=page_number,
                    width=page.rect.width,
                    height=page.rect.height,
                    text_blocks=_extract_text_blocks(page, page_number),
                    images=_extract_images(doc, page, page_number),
                )
            )
    return pages


def _extract_text_blocks(page: fitz.Page, page_number: int) -> list[TextBlock]:
    raw = page.get_text("dict")
    blocks: list[TextBlock] = []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:  # 0 = text block, 1 = image block
            continue
        spans = [span for line in block.get("lines", []) for span in line.get("spans", [])]
        if not spans:
            continue
        text = " ".join("".join(span["text"] for span in spans).split())
        if not text:
            continue
        sizes = [span["size"] for span in spans]
        bold = sum(1 for span in spans if span["flags"] & _BOLD_FLAG) > len(spans) / 2
        blocks.append(
            TextBlock(
                page_number=page_number,
                bbox=tuple(block["bbox"]),
                text=text,
                font_size=sum(sizes) / len(sizes),
                bold=bold,
            )
        )
    return blocks


def _extract_images(doc: fitz.Document, page: fitz.Page, page_number: int) -> list[ImageBlock]:
    images: list[ImageBlock] = []
    for img in page.get_images(full=True):
        xref = img[0]
        rects = page.get_image_rects(xref)
        if not rects:
            continue
        try:
            extracted = doc.extract_image(xref)
        except Exception:
            continue
        for rect in rects:
            if rect.width < _MIN_IMAGE_SIDE or rect.height < _MIN_IMAGE_SIDE:
                continue
            images.append(
                ImageBlock(
                    page_number=page_number,
                    bbox=(rect.x0, rect.y0, rect.x1, rect.y1),
                    image_bytes=extracted["image"],
                    ext=extracted["ext"],
                )
            )
    return images

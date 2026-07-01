"""Layout normalization: two-column -> one-column, headings, figure separation.

Pure heuristic, no ML/OCR/external service. Operates on the already-extracted
PageContent objects from extraction.py, so this module is independently
testable with synthetic bbox fixtures (see tests/test_layout.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union

from app.models import ContentUnit, Figure, ImageBlock, NormalizedDocument, PageContent, TextBlock

_CAPTION_RE = re.compile(r"^(figure|fig\.?|table)\s*\d+", re.IGNORECASE)
_FULL_WIDTH_RATIO = 0.55  # block spans >= this fraction of page width -> not column-bound
_HEADER_FOOTER_MARGIN = 0.06  # fraction of page height treated as running header/footer zone
_MAX_HEADER_FOOTER_WORDS = 4
_MAX_CAPTION_GAP = 60  # points; max vertical distance between an image and its caption
_MAX_HEADING_WORDS = 15  # longer bold/large lines are emphasis, not section headings


@dataclass
class _PositionedItem:
    bbox: tuple[float, float, float, float]
    kind: str  # "text" | "image"
    payload: Union[TextBlock, ImageBlock]


def normalize_pages(pages: list[PageContent]) -> NormalizedDocument:
    """Flatten multi-column pages into one reading-order stream + figure list."""
    median_size = _median_font_size([b for p in pages for b in p.text_blocks])

    units: list[ContentUnit] = []
    figures: list[Figure] = []
    figure_counter = 0

    for page in pages:
        items = _order_page_items(page)
        image_indices = [i for i, it in enumerate(items) if it.kind == "image"]
        caption_used: set[int] = set()
        pairings: dict[int, int] = {}
        for img_idx in image_indices:
            cap_idx = _find_caption(items, img_idx, caption_used)
            if cap_idx is not None:
                pairings[img_idx] = cap_idx
                caption_used.add(cap_idx)

        for i, item in enumerate(items):
            if item.kind == "image":
                figure_counter += 1
                figure_id = f"figure-{figure_counter}"
                image: ImageBlock = item.payload
                caption_text = ""
                if i in pairings:
                    caption_text = items[pairings[i]].payload.text
                label = _short_label(caption_text) or f"Figure {figure_counter}"
                figures.append(
                    Figure(
                        figure_id=figure_id,
                        label=label,
                        caption=caption_text,
                        image_path=f"figures/{figure_id}.{image.ext}",
                        page_number=image.page_number,
                        image_bytes=image.image_bytes,
                    )
                )
                units.append(ContentUnit(kind="figure_ref", figure_id=figure_id))
                continue

            if i in caption_used:
                continue  # already attached to a figure above; don't duplicate in the flow

            block: TextBlock = item.payload
            is_heading = _is_heading(block, median_size)
            # Headings are legitimate structure even when they sit near a page's top/
            # bottom margin (e.g. a page-1 title, or a section heading right after a
            # page break) -- only apply the header/footer noise filter to non-headings.
            if not is_heading and _looks_like_header_or_footer(block, page):
                continue

            if is_heading:
                units.append(
                    ContentUnit(kind="heading", text=block.text, level=_heading_level(block, median_size))
                )
            else:
                units.append(ContentUnit(kind="paragraph", text=block.text))

    return NormalizedDocument(units=units, figures=figures)


def _order_page_items(page: PageContent) -> list[_PositionedItem]:
    """Reading order for one page: full-width preamble, then left column top-to-
    bottom, then right column top-to-bottom, then full-width postamble.

    Falls back to plain top-to-bottom when nothing is column-bound, which
    naturally also handles single-column pages/papers correctly.
    """
    items = [_PositionedItem(b.bbox, "text", b) for b in page.text_blocks]
    items += [_PositionedItem(im.bbox, "image", im) for im in page.images]

    mid_x = page.width / 2 if page.width else 0
    full: list[_PositionedItem] = []
    left: list[_PositionedItem] = []
    right: list[_PositionedItem] = []
    for item in items:
        x0, _, x1, _ = item.bbox
        width_ratio = (x1 - x0) / page.width if page.width else 1
        if width_ratio >= _FULL_WIDTH_RATIO:
            full.append(item)
        elif (x0 + x1) / 2 < mid_x:
            left.append(item)
        else:
            right.append(item)

    if not left and not right:
        return sorted(full, key=lambda it: it.bbox[1])

    col_start = min(it.bbox[1] for it in left + right)
    col_end = max(it.bbox[3] for it in left + right)

    def _y_center(it: _PositionedItem) -> float:
        return (it.bbox[1] + it.bbox[3]) / 2

    pre = sorted((it for it in full if _y_center(it) <= col_start), key=lambda it: it.bbox[1])
    mid = sorted(
        (it for it in full if col_start < _y_center(it) < col_end), key=lambda it: it.bbox[1]
    )
    post = sorted((it for it in full if _y_center(it) >= col_end), key=lambda it: it.bbox[1])
    left_sorted = sorted(left, key=lambda it: it.bbox[1])
    right_sorted = sorted(right, key=lambda it: it.bbox[1])

    return pre + left_sorted + mid + right_sorted + post


def _median_font_size(blocks: list[TextBlock]) -> float:
    if not blocks:
        return 10.0
    sizes = sorted(b.font_size for b in blocks)
    mid = len(sizes) // 2
    if len(sizes) % 2:
        return sizes[mid]
    return (sizes[mid - 1] + sizes[mid]) / 2


def _is_heading(block: TextBlock, median_size: float) -> bool:
    if len(block.text.split()) > _MAX_HEADING_WORDS:
        return False
    if median_size <= 0:
        return False
    return block.font_size >= median_size * 1.15 or (block.bold and block.font_size >= median_size * 1.05)


def _heading_level(block: TextBlock, median_size: float) -> int:
    ratio = block.font_size / median_size if median_size else 1
    if ratio >= 1.6:
        return 1
    if ratio >= 1.35:
        return 2
    return 3


def _looks_like_header_or_footer(block: TextBlock, page: PageContent) -> bool:
    _, y0, _, y1 = block.bbox
    near_top = y0 <= page.height * _HEADER_FOOTER_MARGIN
    near_bottom = y1 >= page.height * (1 - _HEADER_FOOTER_MARGIN)
    if not (near_top or near_bottom):
        return False
    return len(block.text.split()) <= _MAX_HEADER_FOOTER_WORDS


def _find_caption(
    items: list[_PositionedItem], img_idx: int, caption_used: set[int]
) -> int | None:
    ix0, iy0, ix1, iy1 = items[img_idx].bbox
    best_idx: int | None = None
    best_dist: float | None = None
    for j, it in enumerate(items):
        if it.kind != "text" or j in caption_used:
            continue
        if not _CAPTION_RE.match(it.payload.text.strip()):
            continue
        jx0, jy0, jx1, jy1 = it.bbox
        if jy0 >= iy1:
            dist = jy0 - iy1  # caption below the image
        elif jy1 <= iy0:
            dist = iy0 - jy1  # caption above the image (common for tables)
        else:
            continue  # vertically overlaps the image itself; not a plausible caption
        if dist > _MAX_CAPTION_GAP:
            continue
        if best_dist is None or dist < best_dist:
            best_dist, best_idx = dist, j
    return best_idx


def _short_label(caption: str) -> str | None:
    match = _CAPTION_RE.match(caption.strip())
    if not match:
        return None
    return match.group(0).strip().rstrip(":").capitalize()

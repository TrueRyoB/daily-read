"""Shared data structures passed between pipeline stages.

Kept as plain dataclasses (not pydantic) because these objects never cross
a network/serialization boundary directly -- pipeline.py converts the final
result to JSON explicitly before writing it to disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TextBlock:
    """One PyMuPDF text block on a single page, with layout metadata."""

    page_number: int
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1)
    text: str
    font_size: float
    bold: bool


@dataclass
class ImageBlock:
    """One embedded image on a page, before caption pairing."""

    page_number: int
    bbox: tuple[float, float, float, float]
    image_bytes: bytes
    ext: str


@dataclass
class PageContent:
    """Raw extraction output for a single page."""

    page_number: int
    width: float
    height: float
    text_blocks: list[TextBlock] = field(default_factory=list)
    images: list[ImageBlock] = field(default_factory=list)


@dataclass
class Figure:
    """A figure/table pulled out of the reading flow into its own panel."""

    figure_id: str  # e.g. "figure-1"
    label: str  # e.g. "Figure 1"
    caption: str
    image_path: str  # relative path under the paper's data dir, e.g. "figures/figure-1.png"
    page_number: int
    image_bytes: bytes = field(default=b"", repr=False, compare=False)
    """Raw image bytes for pipeline.py to write to disk; never serialized to content.json."""


@dataclass
class ContentUnit:
    """One item in the normalized, single-column reading-order stream."""

    kind: str  # "heading" | "paragraph" | "figure_ref"
    text: str = ""
    level: int = 0  # heading level, 0 for non-headings
    figure_id: str | None = None  # set when kind == "figure_ref"


@dataclass
class GlossaryEntry:
    term: str
    definition: str | None
    contexts: list[str]
    source: str  # "in_text_definition" | "bundled_dictionary" | "concordance"


@dataclass
class NormalizedDocument:
    """Output of layout normalization: a flat, single-column reading order."""

    units: list[ContentUnit]
    figures: list[Figure]


@dataclass
class PaperContent:
    """Everything the reading view template needs, serialized to content.json."""

    title: str
    units: list[ContentUnit]
    figures: list[Figure]
    glossary: list[GlossaryEntry]
    word_count: int
    est_minutes: int

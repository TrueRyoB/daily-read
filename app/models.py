"""Shared data structures passed between pipeline stages.

Kept as plain dataclasses (not pydantic) because these objects never cross
a network/serialization boundary directly -- pipeline.py converts the final
result to JSON explicitly before writing it to disk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Wire format for an in-text citation ref, embedded directly into
# ContentUnit.text by tei_parse.py and decoded back out by rendering.py's
# HTML annotator (plan/03-c). Kept here (not in tei_parse.py or
# rendering.py) so producer and consumer can't drift out of sync with each
# other. Uses NUL-byte delimiters: they survive html.escape() untouched
# (unlike "<"/">") and never occur in real paper text, so they can't be
# confused with content the paper actually contains.
CITATION_PLACEHOLDER_RE = re.compile(r"\x00CITE:([^\x00]+)\x00(.*?)\x00/CITE\x00", re.DOTALL)


def citation_placeholder(bib_ids: str | list[str], label: str) -> str:
    """bib_ids is usually a single id, but GROBID sometimes splits one
    combined citation like "[1, 16]" into multiple adjacent <ref> elements
    (plan/05-a) -- tei_parse.py merges those into one placeholder carrying
    all of their ids, comma-joined."""
    ids = bib_ids if isinstance(bib_ids, str) else ",".join(bib_ids)
    return f"\x00CITE:{ids}\x00{label}\x00/CITE\x00"


# Separate wire format (not reusing CITATION_PLACEHOLDER_RE) for in-text
# mentions of a figure/table ("as shown in Figure 3"), so rendering.py can
# tell the two apart without guessing from the id's shape (plan/05-b).
FIGURE_MENTION_PLACEHOLDER_RE = re.compile(r"\x00FIGREF:([^\x00]+)\x00(.*?)\x00/FIGREF\x00", re.DOTALL)


def figure_mention_placeholder(figure_id: str, label: str) -> str:
    return f"\x00FIGREF:{figure_id}\x00{label}\x00/FIGREF\x00"


@dataclass
class BibliographyEntry:
    """One entry in the paper's reference list, parsed from text/back."""

    bib_id: str  # matches a <ref type="bibr" target="#bib_id"> in body text
    index: int  # 1-indexed position in the reference list, for display (e.g. "[3]")
    authors: list[str]
    title: str
    year: str | None
    url: str | None  # DOI resolved to https://doi.org/... if GROBID found one, else None


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
    title: str | None = None  # from teiHeader; None if GROBID's header parse found nothing
    authors: list[str] = field(default_factory=list)
    abstract: str | None = None
    bibliography: list[BibliographyEntry] = field(default_factory=list)


@dataclass
class PaperContent:
    """Everything the reading view template needs, serialized to content.json."""

    title: str
    units: list[ContentUnit]
    figures: list[Figure]
    glossary: list[GlossaryEntry]
    word_count: int
    est_minutes: int
    authors: list[str] = field(default_factory=list)
    abstract: str | None = None
    bibliography: list[BibliographyEntry] = field(default_factory=list)

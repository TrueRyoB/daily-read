"""Parse GROBID's TEI XML output into the pipeline's NormalizedDocument.

Replaces the old PyMuPDF-heuristic column/caption logic (formerly
app/pdf/layout.py) now that GROBID's layout model already emits body text
in document reading order and separates figure/table captions as distinct
TEI elements. PyMuPDF is still used here, but only to rasterize the pixel
region GROBID reports via `coords` -- GROBID itself doesn't extract raster
images.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import fitz  # PyMuPDF

from app.models import (
    BibliographyEntry,
    ContentUnit,
    Figure,
    NormalizedDocument,
    citation_placeholder,
    figure_mention_placeholder,
)

_TEI_NS = "{http://www.tei-c.org/ns/1.0}"
_XML_NS = "{http://www.w3.org/XML/1998/namespace}"
_MIN_IMAGE_SIDE = 30  # points; skip slivers GROBID mis-detected as figures
_ZOOM = 2.0  # render figures at ~144dpi instead of PyMuPDF's 72dpi default
_NUMBERING_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s")


def parse_tei(tei_xml: str, pdf_path: str) -> NormalizedDocument:
    """Build a NormalizedDocument from GROBID's TEI output.

    Two passes over the clustered body items (not one), because inline
    mentions like "as shown in Figure 3 below" (plan/05-b) can appear
    *before* the actual <figure> element they refer to in reading order.
    Pass 1 builds every figure and records GROBID's own xml:id -> our
    figure_id mapping; pass 2 builds the unit stream, now able to resolve
    any inline figure/table mention regardless of where it falls relative
    to the figure itself.
    """
    root = ET.fromstring(tei_xml)
    title, authors, abstract = _parse_header(root)
    bibliography = _parse_bibliography(root)
    body = root.find(f".//{_TEI_NS}text/{_TEI_NS}body")

    units: list[ContentUnit] = []
    figures: list[Figure] = []

    if body is None:
        return NormalizedDocument(
            units=units, figures=figures, title=title, authors=authors, abstract=abstract, bibliography=bibliography
        )

    clustered = _cluster_adjacent_duplicate_figures(list(_walk_body(body)))

    figure_counter = 0
    built_figures: dict[int, Figure | None] = {}
    grobid_id_to_figure_id: dict[str, str] = {}
    with fitz.open(pdf_path) as doc:
        for idx, (_depth, item, _has_p) in enumerate(clustered):
            if not isinstance(item, list):
                continue
            figure_counter += 1
            figure = _build_figure(item, figure_counter, doc)
            built_figures[idx] = figure
            if figure is not None:
                figures.append(figure)
                for elem in item:
                    grobid_id = elem.get(f"{_XML_NS}id")
                    if grobid_id:
                        grobid_id_to_figure_id[grobid_id] = figure.figure_id

    in_stray_diagram_run = False
    for idx, (depth, item, has_paragraph_sibling) in enumerate(clustered):
        if isinstance(item, list):
            in_stray_diagram_run = False
            figure = built_figures[idx]
            if figure is not None:
                units.append(ContentUnit(kind="figure_ref", figure_id=figure.figure_id))
            else:
                caption = _figure_caption_text(item[0])
                if caption:
                    units.append(ContentUnit(kind="paragraph", text=caption))
            continue

        tag = _localname(item.tag)
        if tag == "head":
            # A diagram's *last* box label can end up sharing its <div>
            # with the diagram's own real caption paragraph (observed on
            # the real "Model"/"Fig 2: DAD..." pair) -- that paragraph
            # sibling would otherwise let it slip past the base
            # _is_stray_diagram_label check. Once a run of stray labels
            # has started, any further unnumbered head is treated as part
            # of the same run regardless of its own paragraph sibling;
            # the paragraph itself is unaffected, it's a separate stream
            # item processed on its own next.
            if _is_stray_diagram_label(item, has_paragraph_sibling) or (in_stray_diagram_run and not item.get("n")):
                in_stray_diagram_run = True
                continue
            in_stray_diagram_run = False
            text = _merge_adjacent_citations(_clean_text(item, grobid_id_to_figure_id))
            if text:
                units.append(ContentUnit(kind="heading", text=text, level=_infer_level(text, depth)))
        elif tag == "p":
            in_stray_diagram_run = False
            text = _merge_adjacent_citations(_clean_text(item, grobid_id_to_figure_id))
            if text:
                units.append(ContentUnit(kind="paragraph", text=text))

    return NormalizedDocument(
        units=units,
        figures=figures,
        title=title,
        authors=authors,
        abstract=abstract,
        bibliography=bibliography,
        unresolved_figure_ref_count=_count_unresolved_figure_refs(body, grobid_id_to_figure_id),
    )


def _parse_bibliography(root: ET.Element) -> list[BibliographyEntry]:
    """Read text/back's reference list -- GROBID's own bibliography
    parsing, not something to re-derive from body text ourselves. Index is
    each entry's 1-indexed position in the list, used as its display
    number (e.g. "[3]") since GROBID doesn't otherwise hand us one."""
    entries = []
    biblstructs = root.findall(f".//{_TEI_NS}text/{_TEI_NS}back//{_TEI_NS}listBibl/{_TEI_NS}biblStruct")
    for index, bibl in enumerate(biblstructs, start=1):
        bib_id = bibl.get(f"{_XML_NS}id") or f"b{index - 1}"

        title_elem = bibl.find(f"{_TEI_NS}analytic/{_TEI_NS}title")
        if title_elem is None:
            title_elem = bibl.find(f"{_TEI_NS}monogr/{_TEI_NS}title")
        title = _clean_text(title_elem) if title_elem is not None else ""

        authors = [
            name
            for p in bibl.findall(f"{_TEI_NS}analytic/{_TEI_NS}author/{_TEI_NS}persName")
            if (name := _person_name(p))
        ]

        date_elem = bibl.find(f"{_TEI_NS}monogr/{_TEI_NS}imprint/{_TEI_NS}date")
        year = date_elem.get("when") if date_elem is not None else None

        doi_elem = bibl.find(f"{_TEI_NS}idno[@type='DOI']")
        url = f"https://doi.org/{doi_elem.text.strip()}" if doi_elem is not None and doi_elem.text else None

        entries.append(
            BibliographyEntry(bib_id=bib_id, index=index, authors=authors, title=title, year=year, url=url)
        )
    return entries


def _cluster_adjacent_duplicate_figures(
    items: list[tuple[int, ET.Element, bool]],
) -> list[tuple[int, ET.Element | list[ET.Element], bool]]:
    """Group consecutive <figure> elements that share the same non-empty
    caption into one cluster.

    GROBID's own figure/caption association model sometimes detects a
    multi-panel figure as several adjacent <figure> elements and assigns
    each of them the identical full caption text (observed empirically:
    a real processed paper had 61 <figure> elements but only 47 distinct
    captions, with one caption reused 11 times). Rather than emitting one
    wrong-looking duplicate per panel, treat a run of identical-caption
    figures as sub-panels of a single logical figure. Figures with no
    caption at all are never clustered this way (nothing to compare), to
    avoid accidentally merging genuinely unrelated uncaptioned figures.

    The third tuple element (div_has_paragraph, see _walk_body) is passed
    through unchanged -- irrelevant to figures, only used by parse_tei's
    own head-vs-diagram-label check.
    """
    clustered: list[tuple[int, ET.Element | list[ET.Element], bool]] = []
    i, n = 0, len(items)
    while i < n:
        depth, elem, has_p = items[i]
        if _localname(elem.tag) != "figure":
            clustered.append((depth, elem, has_p))
            i += 1
            continue
        cluster = [elem]
        caption = _figure_caption_text(elem)
        j = i + 1
        while (
            j < n
            and _localname(items[j][1].tag) == "figure"
            and caption
            and _figure_caption_text(items[j][1]) == caption
        ):
            cluster.append(items[j][1])
            j += 1
        clustered.append((depth, cluster, has_p))
        i = j
    return clustered


def _parse_header(root: ET.Element) -> tuple[str | None, list[str], str | None]:
    """Read title/authors/abstract from teiHeader -- GROBID's own header
    extraction model, not a heuristic we should be re-deriving ourselves.
    Returns (None, [], None) piece-wise for whatever teiHeader doesn't have,
    so pipeline.py can fall back to its own title guess only where needed.
    """
    header = root.find(f"{_TEI_NS}teiHeader")
    if header is None:
        return None, [], None

    title_elem = header.find(
        f"{_TEI_NS}fileDesc/{_TEI_NS}titleStmt/{_TEI_NS}title"
    )
    title = _clean_text(title_elem) if title_elem is not None else None
    title = title or None

    authors: list[str] = []
    for pers_name in header.findall(
        f"{_TEI_NS}fileDesc/{_TEI_NS}sourceDesc/{_TEI_NS}biblStruct/{_TEI_NS}analytic/{_TEI_NS}author/{_TEI_NS}persName"
    ):
        name = _person_name(pers_name)
        if name:
            authors.append(name)

    abstract_elem = header.find(f"{_TEI_NS}profileDesc/{_TEI_NS}abstract")
    abstract = _clean_text(abstract_elem) if abstract_elem is not None else None
    abstract = abstract or None

    return title, authors, abstract


def _person_name(pers_name: ET.Element) -> str:
    """Join forename(s)+surname with a space.

    Not routed through _clean_text: TEI often serializes persName's child
    elements with no whitespace between the closing/opening tags (e.g.
    "<forename>Ada</forename><surname>Nakamura</surname>"), and
    _clean_text's flatten-then-join would glue them into "AdaNakamura".
    """
    parts = []
    for child in pers_name:
        if _localname(child.tag) in ("forename", "surname") and child.text:
            parts.append(child.text.strip())
    return " ".join(p for p in parts if p)


def _walk_body(elem: ET.Element, depth: int = 0):
    """Yield (div_nesting_depth, element, div_has_paragraph) for
    head/p/figure/etc. descendants in document order, flattening arbitrary
    <div> nesting (GROBID's divs are usually flat, but nested subsections
    do occur). depth is how many <div> ancestors an element has, starting
    at 1 for a body's direct child div's contents -- used by _infer_level
    as a fallback signal for headings that have no numbering text of
    their own. div_has_paragraph is whether `elem` (this child's own,
    immediate parent <div>) has any direct <p> child at all -- used by
    parse_tei to tell a real (if unnumbered) heading like "ACKNOWLEDGMENTS"
    apart from a mis-segmented diagram-label fragment sharing an otherwise
    empty <div> (plan/07-troubleshooting-backlog.md)."""
    has_paragraph = any(_localname(c.tag) == "p" for c in elem)
    for child in elem:
        if _localname(child.tag) == "div":
            yield from _walk_body(child, depth + 1)
        else:
            yield depth, child, has_paragraph


def _localname(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _clean_text(elem: ET.Element, fig_id_map: dict[str, str] | None = None) -> str:
    """Flatten an element's text, treating <lb/> as an explicit space so
    that line-wrap boundaries never glue two words together.

    <ref type="bibr"> citation markers are replaced with a placeholder
    token (see app.models.citation_placeholder) instead of being flattened
    to plain text, so rendering.py can turn them into links later without
    ContentUnit.text stopping being a plain string (plan/03-c).

    <ref type="figure"/"table"> inline mentions ("as shown in Figure 3")
    get the same placeholder treatment when `fig_id_map` (GROBID xml:id ->
    our figure_id, built in parse_tei's first pass) resolves the target;
    otherwise the mention is left as plain text (e.g. the figure failed to
    crop, or was never actually detected as a figure) -- plan/05-b.
    """
    parts: list[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        localname = _localname(child.tag)
        ref_type = child.get("type") if localname == "ref" else None
        bib_id = _bib_target_id(child) if ref_type == "bibr" else None
        figure_id = None
        if ref_type in ("figure", "table") and fig_id_map:
            grobid_id = _bib_target_id(child)
            figure_id = fig_id_map.get(grobid_id) if grobid_id else None
        if localname == "lb":
            parts.append(" ")
        elif bib_id is not None:
            parts.append(citation_placeholder(bib_id, _clean_text(child) or f"[{bib_id}]"))
        elif figure_id is not None:
            parts.append(figure_mention_placeholder(figure_id, _clean_text(child) or figure_id))
        else:
            parts.append(_clean_text(child, fig_id_map))
        if child.tail:
            parts.append(child.tail)
    return " ".join("".join(parts).split())


def _bib_target_id(ref_elem: ET.Element) -> str | None:
    target = ref_elem.get("target")
    if target and target.startswith("#"):
        return target[1:]
    return None


def _count_unresolved_figure_refs(body: ET.Element, fig_id_map: dict[str, str]) -> int:
    """Counts <ref type="figure"|"table"> mentions ("as shown in Figure 2")
    that GROBID itself could not resolve to an extracted figure (plan/07-
    troubleshooting-backlog.md#b-11) -- either because the ref has no
    `target` at all (GROBID never even attempted a match, real example:
    `<ref type="figure">2</ref>` with no target attribute, from a diagram
    GROBID failed to segment into a <figure> element in the first place),
    or its target points at a <figure> that ultimately failed to crop
    (excluded from `fig_id_map`, which _build_figure only populates on
    success).

    This is a direct, GROBID-native signal -- more precise than
    re-deriving the same fact by regex-scanning prose for "Figure N",
    since GROBID has already done the reference-resolution work for us
    and we're just reading its answer.
    """
    count = 0
    for ref in body.iter(f"{_TEI_NS}ref"):
        if ref.get("type") not in ("figure", "table"):
            continue
        target_id = _bib_target_id(ref)
        if target_id is None or target_id not in fig_id_map:
            count += 1
    return count


_CITATION_TOKEN_RE = re.compile(r"\x00CITE:([^\x00]+)\x00(.*?)\x00/CITE\x00", re.DOTALL)


def _merge_adjacent_citations(text: str) -> str:
    """Merge runs of citation placeholders that have nothing (or only
    whitespace-free adjacency) between them into one combined placeholder.

    GROBID sometimes splits one combined citation like "[1, 16]" into
    multiple adjacent <ref type="bibr"> elements, each carrying only a
    fragment of the visible label (observed in real output: "[1," and
    "16]" as two separate <ref> elements) -- see plan/05-a. Left alone,
    this renders as two separate, broken-looking links; this merges them
    into one link covering all of the referenced entries.
    """
    matches = list(_CITATION_TOKEN_RE.finditer(text))
    if len(matches) < 2:
        return text

    pieces: list[str] = []
    last_end = 0
    i = 0
    while i < len(matches):
        run = [matches[i]]
        j = i + 1
        while j < len(matches) and text[matches[j - 1].end() : matches[j].start()] == "":
            run.append(matches[j])
            j += 1
        pieces.append(text[last_end : run[0].start()])
        if len(run) == 1:
            pieces.append(run[0].group(0))
        else:
            ids = [m.group(1) for m in run]
            label = "".join(m.group(2) for m in run)
            pieces.append(citation_placeholder(ids, label))
        last_end = run[-1].end()
        i = j
    pieces.append(text[last_end:])
    return "".join(pieces)


def _is_stray_diagram_label(head: ET.Element, div_has_paragraph: bool) -> bool:
    """Detects a <head> that is almost certainly a mis-segmented text
    fragment from a figure (a flowchart/diagram made of short text boxes
    and arrows -- Mermaid-style diagrams are a common source, since their
    box labels are short, isolated, and heading-shaped) rather than a
    real section heading (plan/07-troubleshooting-backlog.md, real-world
    example: a Deep Adaptive Design paper's Figure 2 pipeline diagram
    surfaced "Offline training"/"Deploy"/"Live experiment"/"Model" as
    four separate top-level headings, breaking the reading flow).

    GROBID's layout model occasionally fails to recognize such a diagram
    as one figure block and instead segments its box labels as their own
    <div><head>...</head></div> elements with no body text at all.

    Two conditions must BOTH hold, confirmed empirically against a real
    processed paper: every genuine body-section heading GROBID emits
    carries its own `n="..."` numbering attribute once inside the body
    text (from "1." down to "4.1.2" etc.); genuine unnumbered headings
    that DO occur (e.g. "ACKNOWLEDGMENTS", "FUNDING") always still have
    real paragraph content in their own <div> -- a bare, paragraph-less
    div is not how GROBID represents a real (if unnumbered) section.
    Requiring both keeps every real heading, numbered or not.
    """
    return not head.get("n") and not div_has_paragraph


def _infer_level(text: str, nesting_depth: int) -> int:
    """Numbering text (e.g. "1.2.3") is the primary signal when present --
    GROBID often flattens <div> nesting even for logically deep sections
    (see _walk_body), so a numbered heading's own text is more reliable
    than div depth. For headings with no numbering at all (e.g. "Abstract",
    "Related Work"), div nesting depth is the only structural signal left,
    instead of always defaulting to level 1 regardless of real nesting."""
    match = _NUMBERING_RE.match(text)
    if match:
        return min(match.group(1).count(".") + 1, 3)
    return max(1, min(nesting_depth, 3))


def _figure_caption_text(elem: ET.Element) -> str:
    desc = elem.find(f"{_TEI_NS}figDesc")
    if desc is not None:
        return _clean_text(desc)
    return _clean_text(elem)


def _build_figure(elems: list[ET.Element], index: int, doc: fitz.Document) -> Figure | None:
    """Build one Figure from a cluster of 1+ <figure> elements (see
    _cluster_adjacent_duplicate_figures) by cropping the union of their
    coordinate boxes -- a single sub-panel's box for an ordinary figure,
    or the combined bounding box spanning all panels for a detected
    multi-panel cluster."""
    image_bytes = _crop_image(elems, doc)
    if image_bytes is None:
        return None

    primary = elems[0]
    is_table = primary.get("type") == "table"
    head = primary.find(f"{_TEI_NS}head")
    label = _clean_text(head) if head is not None else ""
    if not label:
        label = f"Table {index}" if is_table else f"Figure {index}"

    figure_id = f"figure-{index}"
    return Figure(
        figure_id=figure_id,
        label=label,
        caption=_figure_caption_text(primary),
        image_path=f"figures/{figure_id}.png",
        page_number=_page_from_coords(elems),
        image_bytes=image_bytes,
    )


def _figure_coords(elem: ET.Element) -> str | None:
    """Coords for cropping: prefer <figure>'s own coords attribute (what
    this project's `teiCoordinates=figure` request parameter populates),
    falling back to the nested <graphic> child's coords -- the shape
    GROBID's own documentation shows for other extraction modes, in case a
    given GROBID version/config attaches it there instead."""
    coords = elem.get("coords")
    if coords:
        return coords
    graphic = elem.find(f"{_TEI_NS}graphic")
    return graphic.get("coords") if graphic is not None else None


def _crop_image(elems: list[ET.Element], doc: fitz.Document) -> bytes | None:
    boxes = [box for elem in elems for box in _parse_coords(_figure_coords(elem))]
    if not boxes:
        return None

    page_number = boxes[0][0]
    boxes = [b for b in boxes if b[0] == page_number]  # ignore stray cross-page coords defensively
    x0 = min(b[1] for b in boxes)
    y0 = min(b[2] for b in boxes)
    x1 = max(b[1] + b[3] for b in boxes)
    y1 = max(b[2] + b[4] for b in boxes)
    if (x1 - x0) < _MIN_IMAGE_SIDE or (y1 - y0) < _MIN_IMAGE_SIDE:
        return None
    if page_number < 1 or page_number > doc.page_count:
        return None

    page = doc[page_number - 1]
    rect = fitz.Rect(x0, y0, x1, y1) & page.rect
    if rect.is_empty:
        return None
    pixmap = page.get_pixmap(clip=rect, matrix=fitz.Matrix(_ZOOM, _ZOOM))
    return pixmap.tobytes("png")


def _page_from_coords(elems: list[ET.Element]) -> int:
    for elem in elems:
        boxes = _parse_coords(_figure_coords(elem))
        if boxes:
            return boxes[0][0]
    return 1


def _parse_coords(coords: str | None) -> list[tuple[int, float, float, float, float]]:
    if not coords:
        return []
    boxes = []
    for box in coords.split(";"):
        parts = box.split(",")
        if len(parts) != 5:
            continue
        page, x, y, w, h = parts
        boxes.append((int(float(page)), float(x), float(y), float(w), float(h)))
    return boxes

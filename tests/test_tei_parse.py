from app.models import ContentUnit
from app.pdf.tei_parse import parse_tei
from tests.helpers import blank_pdf as _blank_pdf

_TEI_NS = "http://www.tei-c.org/ns/1.0"


def _wrap_body(body_xml: str) -> str:
    return f'<TEI xmlns="{_TEI_NS}"><text><body>{body_xml}</body></text></TEI>'


def test_heading_and_paragraph_preserve_document_order(tmp_path):
    tei = _wrap_body(
        """
        <div>
          <head>1. Introduction</head>
          <p>First paragraph.</p>
          <div>
            <head>1.1 Background</head>
            <p>Nested paragraph.</p>
          </div>
          <p>Second top-level paragraph.</p>
        </div>
        """
    )
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    kinds_and_text = [(u.kind, u.text) for u in normalized.units]
    assert kinds_and_text == [
        ("heading", "1. Introduction"),
        ("paragraph", "First paragraph."),
        ("heading", "1.1 Background"),
        ("paragraph", "Nested paragraph."),
        ("paragraph", "Second top-level paragraph."),
    ]


def test_heading_level_inferred_from_numbering(tmp_path):
    tei = _wrap_body(
        """
        <div><head>1 Introduction</head><p>a</p></div>
        <div><head>1.2.3 Deep subsection</head><p>b</p></div>
        <div><head>Abstract</head><p>c</p></div>
        """
    )
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    headings = [u for u in normalized.units if u.kind == "heading"]
    assert headings[0].level == 1
    assert headings[1].level == 3
    assert headings[2].level == 1  # no numbering -> default level 1


def test_line_break_does_not_glue_words_together(tmp_path):
    tei = _wrap_body("<div><p>wordone<lb/>wordtwo</p></div>")
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    assert normalized.units[0].text == "wordone wordtwo"


_STRAY_DIAGRAM_LABEL_BODY = """
<div><head n="4.1">Deep Adaptive Design</head><p>intro text</p></div>
<div><head>Offline training</head></div>
<div><head>Deploy</head></div>
<div><head>Live experiment</head></div>
<div><head>Model</head><p>Fig 2 : DAD pipeline diagram.</p><p>Continuing prose about the pipeline.</p></div>
<div><head n="4.2">Learning Policies</head><p>next section</p></div>
"""


def test_stray_diagram_label_heads_are_not_treated_as_headings(tmp_path):
    # plan/07-troubleshooting-backlog.md: a real processed paper's Figure 2
    # pipeline diagram (flowchart-style, Mermaid-like box labels) surfaced
    # "Offline training"/"Deploy"/"Live experiment"/"Model" as four
    # separate top-level headings -- GROBID's layout model failed to
    # recognize the diagram as one figure block and instead segmented its
    # box labels as their own <div><head>...</head></div> elements with no
    # body text at all.
    normalized = parse_tei(_wrap_body(_STRAY_DIAGRAM_LABEL_BODY), _blank_pdf(tmp_path))
    headings = [u.text for u in normalized.units if u.kind == "heading"]
    assert headings == ["Deep Adaptive Design", "Learning Policies"]
    # ordinary prose that just happens to share a div with the run's last
    # head is unaffected -- only the caption-shaped paragraph right after
    # the run gets absorbed (see the next test).
    paragraphs = [u.text for u in normalized.units if u.kind == "paragraph"]
    assert "Continuing prose about the pipeline." in paragraphs
    assert "intro text" in paragraphs


def test_stray_diagram_label_run_is_surfaced_as_a_figure_fallback_unit(tmp_path):
    # plan/07-troubleshooting-backlog.md#b-11: rather than silently
    # dropping the detected run, it's surfaced as its own unit (raw,
    # un-prosified fragments) instead of either vanishing entirely or
    # masquerading as headings that break the section structure. The
    # figure's own caption paragraph ("Fig 2 : ...", emitted as an
    # ordinary <p> once GROBID ran out of head-shaped fragments) is
    # absorbed into the same run -- a real-world gap found after the
    # initial fix shipped: the run's last head can share a <div> with its
    # own caption paragraph, which used to be left behind in the body as
    # if it were independent prose.
    normalized = parse_tei(_wrap_body(_STRAY_DIAGRAM_LABEL_BODY), _blank_pdf(tmp_path))
    fallback_units = [u for u in normalized.units if u.kind == "figure_fallback"]
    assert len(fallback_units) == 1
    assert fallback_units[0].text == "Offline training\nDeploy\nLive experiment\nModel\nFig 2 : DAD pipeline diagram."

    # the paragraph that does NOT look like a caption opening is left as
    # ordinary prose, not swept in just because it shares a div with the
    # absorbed caption.
    paragraphs = [u.text for u in normalized.units if u.kind == "paragraph"]
    assert "Continuing prose about the pipeline." in paragraphs

    # it sits in reading order right where the stray run occurred -- after
    # "intro text", before "next section".
    kinds_in_order = [(u.kind, u.text) for u in normalized.units]
    intro_idx = kinds_in_order.index(("paragraph", "intro text"))
    next_section_idx = kinds_in_order.index(("paragraph", "next section"))
    fallback_idx = next(i for i, (k, _) in enumerate(kinds_in_order) if k == "figure_fallback")
    assert intro_idx < fallback_idx < next_section_idx

    # never pollutes the table of contents
    assert all(u.kind != "heading" for u in fallback_units)


def test_figure_caption_elsewhere_is_not_absorbed_without_an_active_run(tmp_path):
    # A "Figure 3: ..." caption that appears with no preceding stray-head
    # run at all is ordinary, correctly-placed prose (or a real figure's
    # own caption paragraph) and must never be swept into a fallback unit
    # just because of how it opens.
    tei = _wrap_body(
        """
        <div><head n="1">Results</head>
          <p>Fig 3 : An unrelated, perfectly normal figure caption.</p>
        </div>
        """
    )
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    assert not any(u.kind == "figure_fallback" for u in normalized.units)
    paragraphs = [u.text for u in normalized.units if u.kind == "paragraph"]
    assert "Fig 3 : An unrelated, perfectly normal figure caption." in paragraphs


def test_figure_fallback_flushed_at_end_of_document(tmp_path):
    # A stray run that runs all the way to the end of the body (no
    # trailing paragraph/heading to trigger the flush) must still surface,
    # not get silently lost.
    tei = _wrap_body(
        """
        <div><head n="1">Intro</head><p>text</p></div>
        <div><head>Offline training</head></div>
        <div><head>Deploy</head></div>
        """
    )
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    fallback_units = [u for u in normalized.units if u.kind == "figure_fallback"]
    assert len(fallback_units) == 1
    assert fallback_units[0].text == "Offline training\nDeploy"


def test_unnumbered_heading_with_its_own_paragraph_is_kept(tmp_path):
    # Real, if unnumbered, sections like "ACKNOWLEDGMENTS" always still
    # have real paragraph content in their own <div> -- only a bare,
    # paragraph-less div is treated as a stray diagram-label fragment.
    tei = _wrap_body("<div><head>ACKNOWLEDGMENTS</head><p>Thanks to everyone.</p></div>")
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    headings = [u.text for u in normalized.units if u.kind == "heading"]
    assert headings == ["ACKNOWLEDGMENTS"]


def test_numbered_heading_with_no_paragraph_in_its_own_div_is_kept(tmp_path):
    # A section that's purely an umbrella for subsections (all its content
    # lives in nested sub-divs) can legitimately have no <p> directly in
    # its own div -- GROBID's own n="..." numbering is what distinguishes
    # this from a stray diagram-label fragment, not paragraph presence
    # alone.
    tei = _wrap_body(
        """
        <div>
          <head n="3">Methods</head>
          <div><head n="3.1">Setup</head><p>a</p></div>
        </div>
        """
    )
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    headings = [u.text for u in normalized.units if u.kind == "heading"]
    assert headings == ["Methods", "Setup"]


def test_figure_is_cropped_from_coords_and_removed_from_flow(tmp_path):
    pdf_path = _blank_pdf(tmp_path)
    tei = _wrap_body(
        """
        <div>
          <p>Paragraph before the figure.</p>
          <figure coords="1,50.0,50.0,500.0,250.0">
            <head>Figure 1</head>
            <figDesc>A diagram of the architecture.</figDesc>
          </figure>
          <p>Paragraph after the figure.</p>
        </div>
        """
    )
    normalized = parse_tei(tei, pdf_path)
    kinds = [u.kind for u in normalized.units]
    assert kinds == ["paragraph", "figure_ref", "paragraph"]

    assert len(normalized.figures) == 1
    figure = normalized.figures[0]
    assert figure.label == "Figure 1"
    assert figure.caption == "A diagram of the architecture."
    assert figure.image_path == "figures/figure-1.png"
    assert figure.image_bytes.startswith(b"\x89PNG")


def test_inline_figure_mention_is_linked_to_matching_figure_id(tmp_path):
    pdf_path = _blank_pdf(tmp_path)
    tei = _wrap_body(
        """
        <div xmlns:xml="http://www.w3.org/XML/1998/namespace">
          <p>As shown in Figure <ref type="figure" target="#fig_0">1</ref>, the pipeline works.</p>
          <figure xml:id="fig_0" coords="1,50.0,50.0,500.0,250.0">
            <head>Figure 1</head>
            <figDesc>A diagram of the architecture.</figDesc>
          </figure>
        </div>
        """
    )
    normalized = parse_tei(tei, pdf_path)
    paragraph = next(u for u in normalized.units if u.kind == "paragraph")
    figure_id = normalized.figures[0].figure_id
    assert f"\x00FIGREF:{figure_id}\x001\x00/FIGREF\x00" in paragraph.text


def test_inline_figure_mention_before_the_figure_element_is_still_resolved(tmp_path):
    # "as shown below" -- the inline mention appears in reading order
    # *before* the actual <figure> element it points to (plan/05-b's
    # reason for the two-pass parse).
    pdf_path = _blank_pdf(tmp_path)
    tei = _wrap_body(
        """
        <div xmlns:xml="http://www.w3.org/XML/1998/namespace">
          <p>As shown in Figure <ref type="figure" target="#fig_0">1</ref> below.</p>
          <p>Some other paragraph in between.</p>
          <figure xml:id="fig_0" coords="1,50.0,50.0,500.0,250.0">
            <figDesc>A diagram.</figDesc>
          </figure>
        </div>
        """
    )
    normalized = parse_tei(tei, pdf_path)
    first_paragraph = normalized.units[0]
    figure_id = normalized.figures[0].figure_id
    assert f"\x00FIGREF:{figure_id}\x00" in first_paragraph.text


def test_figure_mention_with_no_resolvable_target_stays_plain_text(tmp_path):
    pdf_path = _blank_pdf(tmp_path)
    tei = _wrap_body(
        """
        <div xmlns:xml="http://www.w3.org/XML/1998/namespace">
          <p>As shown in Figure <ref type="figure" target="#fig_missing">3</ref>.</p>
        </div>
        """
    )
    normalized = parse_tei(tei, pdf_path)
    assert normalized.units[0].text == "As shown in Figure 3."
    assert "FIGREF" not in normalized.units[0].text


def test_unresolved_figure_ref_count_is_zero_when_nothing_is_missing(tmp_path):
    tei = _wrap_body("<div><p>Just plain text, no figure mentions at all.</p></div>")
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    assert normalized.unresolved_figure_ref_count == 0


def test_unresolved_figure_ref_count_flags_a_ref_with_no_target_at_all(tmp_path):
    # Real-world shape (plan/07-troubleshooting-backlog.md#b-11): GROBID
    # marks a mention as type="figure" but emits no target attribute at
    # all when it never resolved a <figure> element for it in the first
    # place (as opposed to a target pointing at a real-but-failed-to-crop
    # figure, covered by the next test).
    tei = _wrap_body('<div><p>See Figure <ref type="figure">2</ref> for details.</p></div>')
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    assert normalized.unresolved_figure_ref_count == 1


def test_unresolved_figure_ref_count_flags_a_target_that_never_resolved(tmp_path):
    tei = _wrap_body(
        """
        <div xmlns:xml="http://www.w3.org/XML/1998/namespace">
          <p>As shown in Figure <ref type="figure" target="#fig_missing">3</ref>.</p>
        </div>
        """
    )
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    assert normalized.unresolved_figure_ref_count == 1


def test_unresolved_figure_ref_count_excludes_successfully_resolved_refs(tmp_path):
    tei = _wrap_body(
        """
        <div xmlns:xml="http://www.w3.org/XML/1998/namespace">
          <p>As shown in Figure <ref type="figure" target="#fig_0">1</ref>.</p>
          <figure xml:id="fig_0" coords="1,50.0,50.0,500.0,250.0">
            <head>Figure 1</head>
            <figDesc>A real figure.</figDesc>
          </figure>
        </div>
        """
    )
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    assert len(normalized.figures) == 1
    assert normalized.unresolved_figure_ref_count == 0


def test_unresolved_figure_ref_count_counts_tables_too(tmp_path):
    tei = _wrap_body('<div><p>See Table <ref type="table">2</ref>.</p></div>')
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    assert normalized.unresolved_figure_ref_count == 1


def test_table_gets_default_label_when_no_head(tmp_path):
    pdf_path = _blank_pdf(tmp_path)
    tei = _wrap_body(
        """
        <div>
          <figure type="table" coords="1,50.0,50.0,500.0,250.0">
            <figDesc>Table caption text.</figDesc>
          </figure>
        </div>
        """
    )
    normalized = parse_tei(tei, pdf_path)
    assert normalized.figures[0].label == "Table 1"


def test_figure_without_coords_falls_back_to_caption_paragraph(tmp_path):
    pdf_path = _blank_pdf(tmp_path)
    tei = _wrap_body(
        """
        <div>
          <figure>
            <figDesc>Caption with no bounding box available.</figDesc>
          </figure>
        </div>
        """
    )
    normalized = parse_tei(tei, pdf_path)
    assert normalized.figures == []
    assert normalized.units == [
        ContentUnit(kind="paragraph", text="Caption with no bounding box available.")
    ]


def test_unnumbered_heading_level_falls_back_to_div_nesting_depth(tmp_path):
    tei = _wrap_body(
        """
        <div>
          <head>1 Introduction</head>
          <p>a</p>
          <div>
            <head>Related Work</head>
            <p>b</p>
          </div>
        </div>
        """
    )
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    headings = {u.text: u.level for u in normalized.units if u.kind == "heading"}
    assert headings["1 Introduction"] == 1
    assert headings["Related Work"] == 2  # nested one level, no numbering to go on


def test_numbering_text_still_wins_over_depth_for_flat_divs(tmp_path):
    # Regression guard: GROBID commonly emits flat (non-nested) sibling
    # divs even for a logically deep numbered heading. Numbering text must
    # stay authoritative here -- depth alone would wrongly flatten this to
    # level 1 for every heading, since all three divs are siblings.
    tei = _wrap_body(
        """
        <div><head>1 Introduction</head><p>a</p></div>
        <div><head>1.2.3 Deep subsection</head><p>b</p></div>
        <div><head>Abstract</head><p>c</p></div>
        """
    )
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    headings = {u.text: u.level for u in normalized.units if u.kind == "heading"}
    assert headings["1 Introduction"] == 1
    assert headings["1.2.3 Deep subsection"] == 3
    assert headings["Abstract"] == 1  # unnumbered, but also unnested -> depth 1


def test_figure_coords_falls_back_to_nested_graphic_element(tmp_path):
    pdf_path = _blank_pdf(tmp_path)
    tei = _wrap_body(
        """
        <div>
          <figure>
            <head>Figure 1</head>
            <figDesc>A diagram with coords on the graphic child.</figDesc>
            <graphic coords="1,50.0,50.0,500.0,250.0" type="bitmap"/>
          </figure>
        </div>
        """
    )
    normalized = parse_tei(tei, pdf_path)
    assert len(normalized.figures) == 1
    assert normalized.figures[0].caption == "A diagram with coords on the graphic child."
    assert normalized.figures[0].image_bytes.startswith(b"\x89PNG")


def test_adjacent_figures_with_identical_caption_are_merged(tmp_path):
    # Reproduces an empirically observed GROBID quirk: a multi-panel figure
    # detected as several adjacent <figure> elements, each assigned the
    # same full caption text.
    pdf_path = _blank_pdf(tmp_path)
    tei = _wrap_body(
        """
        <div>
          <figure coords="1,50.0,50.0,200.0,150.0"><figDesc>Shared caption for all panels.</figDesc></figure>
          <figure coords="1,260.0,50.0,200.0,150.0"><figDesc>Shared caption for all panels.</figDesc></figure>
          <figure coords="1,50.0,220.0,200.0,150.0"><figDesc>Shared caption for all panels.</figDesc></figure>
        </div>
        """
    )
    normalized = parse_tei(tei, pdf_path)
    assert len(normalized.figures) == 1
    kinds = [u.kind for u in normalized.units]
    assert kinds == ["figure_ref"]  # not three duplicate figure_refs


def test_adjacent_figures_without_captions_are_not_merged(tmp_path):
    pdf_path = _blank_pdf(tmp_path)
    tei = _wrap_body(
        """
        <div>
          <figure coords="1,50.0,50.0,200.0,150.0"></figure>
          <figure coords="1,260.0,50.0,200.0,150.0"></figure>
        </div>
        """
    )
    normalized = parse_tei(tei, pdf_path)
    assert len(normalized.figures) == 2


def test_header_fields_are_none_when_teiheader_is_absent(tmp_path):
    normalized = parse_tei(_wrap_body("<div><p>a</p></div>"), _blank_pdf(tmp_path))
    assert normalized.title is None
    assert normalized.authors == []
    assert normalized.abstract is None


def _wrap_full(header_xml: str, body_xml: str = "<div><p>body.</p></div>") -> str:
    return (
        f'<TEI xmlns="{_TEI_NS}"><teiHeader>{header_xml}</teiHeader>'
        f"<text><body>{body_xml}</body></text></TEI>"
    )


def test_title_and_authors_and_abstract_read_from_teiheader(tmp_path):
    tei = _wrap_full(
        """
        <fileDesc>
          <titleStmt><title level="a" type="main">Attention Is All You Need</title></titleStmt>
          <sourceDesc>
            <biblStruct>
              <analytic>
                <author><persName><forename type="first">Ada</forename><surname>Nakamura</surname></persName></author>
                <author><persName><forename type="first">Kenji</forename><surname>Ito</surname></persName></author>
              </analytic>
            </biblStruct>
          </sourceDesc>
        </fileDesc>
        <profileDesc>
          <abstract><p>We propose a new architecture.</p></abstract>
        </profileDesc>
        """
    )
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    assert normalized.title == "Attention Is All You Need"
    # Regression guard: forename/surname have no whitespace between the
    # closing/opening tags, so a naive flatten would glue them together.
    assert normalized.authors == ["Ada Nakamura", "Kenji Ito"]
    assert normalized.abstract == "We propose a new architecture."


def test_empty_title_element_falls_back_to_none(tmp_path):
    tei = _wrap_full('<fileDesc><titleStmt><title level="a" type="main"></title></titleStmt></fileDesc>')
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    assert normalized.title is None


def test_adjacent_split_citation_refs_are_merged_into_one_placeholder(tmp_path):
    # Reproduces a real GROBID quirk (plan/05-a): a combined citation like
    # "[1, 16]" is split into two adjacent <ref> elements, each carrying
    # only a fragment of the visible label ("[1," and "16]").
    tei = _wrap_body(
        """
        <div>
          <p>Prior work <ref type="bibr" target="#b0">[1,</ref><ref type="bibr" target="#b15">16]</ref> studied this.</p>
        </div>
        """
    )
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    text = normalized.units[0].text
    assert "\x00CITE:b0,b15\x00[1,16]\x00/CITE\x00" in text
    # Not two separate placeholders.
    assert text.count("\x00CITE:") == 1


def test_non_adjacent_citation_refs_are_not_merged(tmp_path):
    tei = _wrap_body(
        """
        <div>
          <p>See <ref type="bibr" target="#b0">[1]</ref> and later <ref type="bibr" target="#b1">[2]</ref>.</p>
        </div>
        """
    )
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    text = normalized.units[0].text
    assert text.count("\x00CITE:") == 2
    assert "\x00CITE:b0\x00[1]\x00/CITE\x00" in text
    assert "\x00CITE:b1\x00[2]\x00/CITE\x00" in text


def test_et_al_author_year_leadin_is_replaced_by_the_citation_marker(tmp_path):
    # plan/07-troubleshooting-backlog.md: names/dates the reader didn't ask
    # for are noise once a numbered reference already exists right next
    # to them (real example: "Foster et al. (2020) [44] introduced...").
    tei = _wrap_body(
        """
        <div>
          <p>Foster et al. (2020) <ref type="bibr" target="#b43">[44]</ref> introduced this.</p>
        </div>
        """
    )
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    text = normalized.units[0].text
    assert "Foster" not in text
    assert text.startswith("\x00CITE:b43\x00[44]\x00/CITE\x00 introduced this.")


def test_two_author_and_leadin_is_replaced_by_the_citation_marker(tmp_path):
    tei = _wrap_body(
        """
        <div>
          <p>Huan and Marzouk (2016) <ref type="bibr" target="#b69">[70]</ref> proposed this.</p>
        </div>
        """
    )
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    text = normalized.units[0].text
    assert "Huan" not in text
    assert "Marzouk" not in text
    assert text.startswith("\x00CITE:b69\x00[70]\x00/CITE\x00 proposed this.")


def test_single_author_leadin_is_replaced_by_the_citation_marker(tmp_path):
    tei = _wrap_body(
        """
        <div>
          <p>As shown by Smith (2019) <ref type="bibr" target="#b5">[6]</ref>, the result holds.</p>
        </div>
        """
    )
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    text = normalized.units[0].text
    assert "Smith" not in text
    assert "As shown by \x00CITE:b5\x00[6]\x00/CITE\x00, the result holds." == text


def test_author_year_leadin_stripping_does_not_touch_unrelated_earlier_text(tmp_path):
    # Only the mention immediately adjacent to the upcoming citation
    # marker is touched -- an author's name mentioned earlier in the same
    # sentence with no citation marker right after it is left alone.
    tei = _wrap_body(
        """
        <div>
          <p>Foster is a researcher. Separately, Smith (2019) <ref type="bibr" target="#b5">[6]</ref> showed this.</p>
        </div>
        """
    )
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    text = normalized.units[0].text
    assert "Foster is a researcher." in text
    assert "Smith" not in text


def test_author_name_with_no_following_citation_marker_is_untouched(tmp_path):
    tei = _wrap_body("<div><p>Adam Foster is a Senior Researcher at Microsoft.</p></div>")
    normalized = parse_tei(tei, _blank_pdf(tmp_path))
    assert normalized.units[0].text == "Adam Foster is a Senior Researcher at Microsoft."

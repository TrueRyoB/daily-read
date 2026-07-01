from app.models import ImageBlock, PageContent, TextBlock
from app.pdf.layout import normalize_pages


def _block(x0, y0, x1, y1, text, font_size=10.0, bold=False, page_number=1):
    return TextBlock(page_number=page_number, bbox=(x0, y0, x1, y1), text=text, font_size=font_size, bold=bold)


def test_two_column_page_flattens_left_then_right():
    # A page 400pt wide: left column blocks on the left half, right column on the right half.
    page = PageContent(
        page_number=1,
        width=400,
        height=800,
        text_blocks=[
            _block(20, 20, 380, 50, "Title spans the page", font_size=18, bold=True),
            _block(20, 80, 190, 120, "Left column, first paragraph."),
            _block(20, 140, 190, 180, "Left column, second paragraph."),
            _block(210, 80, 380, 120, "Right column, first paragraph."),
            _block(210, 140, 380, 180, "Right column, second paragraph."),
        ],
        images=[],
    )
    normalized = normalize_pages([page])
    texts = [u.text for u in normalized.units]
    assert texts == [
        "Title spans the page",
        "Left column, first paragraph.",
        "Left column, second paragraph.",
        "Right column, first paragraph.",
        "Right column, second paragraph.",
    ]


def test_single_column_page_stays_top_to_bottom():
    page = PageContent(
        page_number=1,
        width=400,
        height=800,
        text_blocks=[
            _block(20, 20, 380, 50, "First paragraph spans full width."),
            _block(20, 60, 380, 90, "Second paragraph spans full width."),
        ],
        images=[],
    )
    normalized = normalize_pages([page])
    texts = [u.text for u in normalized.units]
    assert texts == ["First paragraph spans full width.", "Second paragraph spans full width."]


def test_heading_detected_by_relative_font_size():
    page = PageContent(
        page_number=1,
        width=400,
        height=800,
        text_blocks=[
            _block(20, 20, 380, 50, "1. Introduction", font_size=16, bold=True),
            _block(20, 60, 380, 200, "Body text at normal size explaining the paper.", font_size=10),
            _block(20, 210, 380, 220, "Body text at normal size explaining the paper.", font_size=10),
        ],
        images=[],
    )
    normalized = normalize_pages([page])
    assert normalized.units[0].kind == "heading"
    assert normalized.units[0].text == "1. Introduction"
    assert normalized.units[1].kind == "paragraph"


def test_header_and_footer_are_dropped():
    page = PageContent(
        page_number=1,
        width=400,
        height=800,
        text_blocks=[
            _block(20, 5, 380, 15, "Running Header"),  # near top, few words -> dropped
            _block(20, 100, 380, 400, "A real paragraph with plenty of words in the body."),
            _block(20, 790, 380, 798, "12"),  # page number near bottom -> dropped
        ],
        images=[],
    )
    normalized = normalize_pages([page])
    texts = [u.text for u in normalized.units]
    assert texts == ["A real paragraph with plenty of words in the body."]


def test_image_is_separated_with_caption_and_marker_left_in_flow():
    page = PageContent(
        page_number=1,
        width=400,
        height=800,
        text_blocks=[
            _block(20, 120, 380, 150, "Paragraph before the figure."),
            _block(20, 360, 380, 380, "Figure 1: A diagram of the architecture."),
            _block(20, 400, 380, 430, "Paragraph after the figure."),
        ],
        images=[
            ImageBlock(page_number=1, bbox=(20, 200, 380, 350), image_bytes=b"fakepng", ext="png"),
        ],
    )
    normalized = normalize_pages([page])
    kinds = [u.kind for u in normalized.units]
    assert kinds == ["paragraph", "figure_ref", "paragraph"]

    assert len(normalized.figures) == 1
    figure = normalized.figures[0]
    assert figure.label == "Figure 1"
    assert figure.caption == "Figure 1: A diagram of the architecture."
    assert figure.image_path == "figures/figure-1.png"
    assert figure.image_bytes == b"fakepng"

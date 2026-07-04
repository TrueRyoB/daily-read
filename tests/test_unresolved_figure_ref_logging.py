"""plan/07-troubleshooting-backlog.md#b-11: when GROBID references a
figure/table it never resolved into an extracted image (e.g. a diagram it
failed to segment as a <figure> block at all), that gap was previously
completely silent -- the reader just saw an unlinked "Figure 2" with no
image and no indication anything was missing. pipeline.py now logs a
warning so it's at least visible for troubleshooting.
"""

from __future__ import annotations

import logging

from app import pipeline
from tests.helpers import blank_pdf, load_golden_tei

_TEI_NS = "http://www.tei-c.org/ns/1.0"

_TEI_WITH_UNRESOLVED_FIGURE_REF = f"""<?xml version="1.0"?>
<TEI xmlns="{_TEI_NS}">
  <text><body>
    <div>
      <head n="1">Introduction</head>
      <p>See Figure <ref type="figure">2</ref> for the overview diagram.</p>
    </div>
  </body></text>
</TEI>
"""


def test_warns_when_a_figure_ref_never_resolved(isolated_data_dir, tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: _TEI_WITH_UNRESOLVED_FIGURE_REF)
    pdf_path = blank_pdf(tmp_path, pages=1)
    with caplog.at_level(logging.WARNING, logger="app.pipeline"):
        pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("could not resolve to an extracted image" in m for m in warnings)


def test_no_warning_when_every_figure_resolves(isolated_data_dir, tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pdf_path = blank_pdf(tmp_path, pages=2)
    with caplog.at_level(logging.WARNING, logger="app.pipeline"):
        pipeline.process_upload("sample.pdf", open(pdf_path, "rb").read())

    warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert not any("could not resolve to an extracted image" in m for m in warnings)

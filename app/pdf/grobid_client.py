"""Thin client for the GROBID service -- the only place that knows GROBID's
REST API shape. GROBID runs as a separate local service (see README), not
an in-process dependency; this module just does the HTTP call and turns
connection failures into an actionable error message.
"""

from __future__ import annotations

import os

import httpx

_DEFAULT_BASE_URL = "http://localhost:8070"
_ENDPOINT = "/api/processFulltextDocument"
# Consolidation adds external CrossRef/biblio-glutton lookups per header and
# per reference, so a plain extraction can get noticeably slower once it's on
# (plan/06-performance-investigation.md -- this was the confirmed cause of
# real timeouts and is now off by default via docker-compose.yml).
_DEFAULT_REQUEST_TIMEOUT = 180.0
_CONSOLIDATE_ENV_VAR = "GROBID_CONSOLIDATE"
# Configurable (plan/07-troubleshooting-backlog.md#a-4) rather than a fixed
# constant: if disabling consolidation doesn't fully eliminate occasional
# slow GROBID runs for some paper, this can be tuned without a code change.
_TIMEOUT_ENV_VAR = "GROBID_TIMEOUT_SECONDS"


def _request_timeout() -> float:
    raw = os.environ.get(_TIMEOUT_ENV_VAR)
    if not raw:
        return _DEFAULT_REQUEST_TIMEOUT
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_REQUEST_TIMEOUT


def extract_tei(pdf_path: str, base_url: str | None = None) -> str:
    """Send a PDF to GROBID and return the TEI XML response body."""
    base_url = base_url or os.environ.get("GROBID_URL", _DEFAULT_BASE_URL)
    url = base_url.rstrip("/") + _ENDPOINT
    request_timeout = _request_timeout()

    # consolidateHeader/consolidateCitations ask GROBID to enrich title,
    # authors, and bibliography entries (incl. DOIs) via external lookup
    # (CrossRef/biblio-glutton) instead of us re-deriving that ourselves.
    # Requires the GROBID container to have outbound internet access; set
    # GROBID_CONSOLIDATE=0 to fall back to purely local extraction.
    consolidate = "0" if os.environ.get(_CONSOLIDATE_ENV_VAR, "1") == "0" else "1"

    with open(pdf_path, "rb") as f:
        try:
            response = httpx.post(
                url,
                files={"input": ("document.pdf", f, "application/pdf")},
                data={
                    "teiCoordinates": "figure",
                    "consolidateHeader": consolidate,
                    "consolidateCitations": consolidate,
                    "generateIDs": "1",
                },
                timeout=request_timeout,
            )
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"GROBIDサービス({base_url})に接続できません。"
                "先に次のコマンドでGROBIDを起動してください: "
                "docker run --rm --init --ulimit core=0 -p 8070:8070 grobid/grobid:0.9.0-crf"
            ) from exc
        except httpx.TimeoutException as exc:
            # plan/05-f: previously uncaught -- a slow/large PDF would raise
            # a raw httpx exception all the way out of the (now background)
            # processing thread instead of a clear, actionable message.
            raise RuntimeError(
                f"GROBIDの処理が{request_timeout:.0f}秒以内に完了しませんでした。"
                "論文が大きい、またはGROBIDの負荷が高い可能性があります。"
                f"（{_TIMEOUT_ENV_VAR}環境変数で調整できます）"
            ) from exc

    if response.status_code != 200:
        raise RuntimeError(
            f"GROBIDがPDFの処理に失敗しました(status={response.status_code}): {response.text[:500]}"
        )
    return response.text

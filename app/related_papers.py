"""OpenAlex-based related-paper suggestions (ticket 07 B-7, v1/lightweight
scope). Opt-in and background-run: the reader presses a button after
finishing a paper, this module resolves the current paper on OpenAlex by
title, gathers candidates from a handful of cheap signals, and scores them.

v1 deliberately limits candidate generation to signals that OpenAlex
answers directly (no per-pair cross-referencing of other papers' own
reference lists, which Bibliographic Coupling/Co-citation would need --
that's a real latency/complexity cost, deferred to a later version):

  - reference: papers Current itself cites (from content.bibliography,
    resolved against OpenAlex on a best-effort basis so unresolved
    references just don't contribute a citation_count)
  - direct_citation: papers that cite Current (OpenAlex `cites:` filter)
  - same_author: other papers by one of Current's authors
  - same_venue: other papers in the same venue as Current

`reference` and `direct_citation` are two directions of the same citation
edge, so they share a weight. Scoring is a placeholder-tunable weighted sum
plus a log(citation_count) tie-break (a pure citation-count sort would
just surface famous papers regardless of actual relatedness).

OpenAlex has no paid tier at all -- this feature has $0 cost either way
(plan/07-troubleshooting-backlog.md#b-7). Set OPENALEX_MAILTO to join the
"polite pool" for more consistent rate limits (optional, not required).
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app import storage

logger = logging.getLogger(__name__)

_OPENALEX_BASE = "https://api.openalex.org"
_REQUEST_TIMEOUT = 15.0
_TOP_N = 10
# Bounds the number of per-reference OpenAlex lookups for signal (A): a
# paper with an unusually long bibliography shouldn't turn one click into
# hundreds of sequential HTTP calls.
_MAX_REFERENCES_RESOLVED = 60
_TITLE_MATCH_OVERLAP_THRESHOLD = 0.6

_SCORE_CITATION_EDGE = 50  # reference or direct_citation
_SCORE_SAME_AUTHOR = 15
_SCORE_SAME_VENUE = 10


def _user_agent() -> str:
    mailto = os.environ.get("OPENALEX_MAILTO")
    base = "daily-read/1.0 (https://github.com/TrueRyoB/daily-read)"
    return f"{base}; mailto:{mailto}" if mailto else base


def _http_get(path: str, params: dict) -> dict | None:
    """The only network seam in this module -- tests monkeypatch this
    directly instead of hitting the real OpenAlex API."""
    try:
        response = httpx.get(
            f"{_OPENALEX_BASE}{path}", params=params, headers={"User-Agent": _user_agent()}, timeout=_REQUEST_TIMEOUT
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        logger.warning("OpenAlex request failed (%s %s): %s", path, params, exc)
        return None


def _normalize_title(title: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9]+", " ", title.lower()).strip().split())


def resolve_work(title: str) -> dict | None:
    """Best-effort title search. Returns None rather than a wrong anchor
    when nothing close enough is found -- OpenAlex's free-text `search`
    always returns *a* top result, even for an unrelated query, so a word-
    overlap sanity check guards against silently resolving to the wrong
    paper (plan/07-troubleshooting-backlog.md#b-7: many papers processed by
    this app have no self-DOI, so title search is the primary path, not a
    fallback)."""
    if not title or not title.strip():
        return None
    data = _http_get("/works", {"search": title, "per-page": 1})
    if not data or not data.get("results"):
        return None
    candidate = data["results"][0]
    query_words = _normalize_title(title)
    candidate_words = _normalize_title(candidate.get("title") or "")
    if not query_words or not candidate_words:
        return None
    overlap = len(query_words & candidate_words) / len(query_words)
    if overlap < _TITLE_MATCH_OVERLAP_THRESHOLD:
        return None
    return candidate


def _short_work(work: dict) -> dict:
    authorships = work.get("authorships") or []
    location = work.get("primary_location") or {}
    return {
        "openalex_id": work.get("id"),
        "title": work.get("title") or "",
        "authors": [a["author"]["display_name"] for a in authorships if a.get("author", {}).get("display_name")],
        "year": work.get("publication_year"),
        "citation_count": work.get("cited_by_count") or 0,
        "url": location.get("landing_page_url") or work.get("doi"),
    }


def _fetch_list(params: dict, limit: int) -> list[dict]:
    data = _http_get("/works", {**params, "per-page": min(limit, 200)})
    if not data:
        return []
    return data.get("results") or []


def generate_candidates(current_work: dict | None, bibliography: list[dict]) -> dict[str, dict]:
    """Returns {openalex_id: candidate} deduped across all signals, each
    candidate carrying which signals matched it (a paper can legitimately
    match more than one -- e.g. a co-author's paper that also cites
    Current)."""
    candidates: dict[str, dict] = {}
    current_id = (current_work or {}).get("id")

    def add(work: dict, **flags: bool) -> None:
        short = _short_work(work)
        key = short["openalex_id"]
        if not key or key == current_id:
            return
        entry = candidates.setdefault(
            key, {**short, "reference": False, "direct_citation": False, "same_author": False, "same_venue": False}
        )
        for flag, value in flags.items():
            if value:
                entry[flag] = True

    if current_work and current_id:
        for work in _fetch_list({"filter": f"cites:{current_id}"}, 50):
            add(work, direct_citation=True)

        author_ids = [
            a["author"]["id"] for a in (current_work.get("authorships") or []) if a.get("author", {}).get("id")
        ]
        for author_id in author_ids:
            for work in _fetch_list({"filter": f"author.id:{author_id}"}, 25):
                add(work, same_author=True)

        source_id = ((current_work.get("primary_location") or {}).get("source") or {}).get("id")
        if source_id:
            for work in _fetch_list({"filter": f"primary_location.source.id:{source_id}"}, 25):
                add(work, same_venue=True)

    for entry in (bibliography or [])[:_MAX_REFERENCES_RESOLVED]:
        title = entry.get("title") if isinstance(entry, dict) else None
        if not title:
            continue
        resolved = resolve_work(title)
        if resolved:
            add(resolved, reference=True)

    return candidates


def score_candidates(candidates: dict[str, dict]) -> list[dict]:
    """Weighted-sum placeholder (plan/07-troubleshooting-backlog.md#b-7:
    weights are a starting point, tuned later against real usage), with
    log(citation_count) as a secondary tie-break so equally-related
    candidates still surface the more-cited one first without letting raw
    citation count alone dominate the ranking."""
    scored = []
    for entry in candidates.values():
        score = 0.0
        if entry["reference"] or entry["direct_citation"]:
            score += _SCORE_CITATION_EDGE
        if entry["same_author"]:
            score += _SCORE_SAME_AUTHOR
        if entry["same_venue"]:
            score += _SCORE_SAME_VENUE
        score += math.log(entry["citation_count"] + 1)
        scored.append({**entry, "score": round(score, 3)})
    scored.sort(key=lambda e: e["score"], reverse=True)
    return scored[:_TOP_N]


def find_related_papers(title: str, bibliography: list[dict]) -> list[dict]:
    current_work = resolve_work(title)
    candidates = generate_candidates(current_work, bibliography)
    return score_candidates(candidates)


def run_and_store(paper_id: str, title: str, bibliography: list[dict]) -> None:
    """Runs off the request thread (same reasoning as
    pipeline._process_in_background: must never let an exception escape
    uncaught, or the job would look stuck at "processing" forever)."""
    path = storage.related_papers_json_path(paper_id)
    try:
        results = find_related_papers(title, bibliography)
        _write_status(path, {"status": "done", "results": results, "generated_at": _now_iso()})
    except Exception as exc:
        logger.error("related-papers job failed for paper %s: %s", paper_id, exc)
        _write_status(path, {"status": "error", "error_message": str(exc)})


def _write_status(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

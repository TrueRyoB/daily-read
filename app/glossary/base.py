"""The swappable-strategy contract for glossary extraction.

Any glossary strategy (today: heuristic.py, later: possibly llm.py) must
satisfy this Protocol and nothing more. pipeline.py only ever depends on
this interface (via factory.py), never on a concrete implementation, so
changing strategy is a factory/config change, not a pipeline rewrite.
"""

from __future__ import annotations

from typing import Protocol

from app.models import GlossaryEntry


class GlossaryExtractor(Protocol):
    def extract(self, full_text: str, known_names: list[str] | None = None) -> list[GlossaryEntry]:
        """Return glossary entries for the terms worth surfacing in this
        text. known_names (plan/05-c) are proper nouns already known from
        this paper's own metadata (its authors + its reference list's
        authors) that should never be treated as undefined jargon."""
        ...


def normalize_term_key(term: str) -> str:
    """Normalize a term for cross-variant matching (e.g. "GNN" and "GNNs"
    should be treated as the same term).

    Deliberately simple -- lowercase + strip a single trailing "s" -- not a
    real stemmer. Good enough for the acronyms and short noun phrases this
    glossary ever surfaces, and cheap to reason about.

    Lives here (not in heuristic.py) because it's shared across strategy
    boundaries: heuristic.py uses it to dedup within one paper's extraction,
    and db.py's known-terms store (plan/04-b) uses the same key so a term
    marked "known" under one strategy is still recognized if the strategy
    is ever swapped (e.g. GLOSSARY_STRATEGY=llm).
    """
    key = term.strip().lower()
    if len(key) > 3 and key.endswith("s") and not key.endswith("ss"):
        key = key[:-1]
    return key

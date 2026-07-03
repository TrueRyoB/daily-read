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
    def extract(
        self,
        full_text: str,
        known_names: list[str] | None = None,
        heading_texts: list[str] | None = None,
    ) -> list[GlossaryEntry]:
        """Return glossary entries for the terms worth surfacing in this
        text. known_names (plan/05-c) are proper nouns already known from
        this paper's own metadata (its authors + its reference list's
        authors) that should never be treated as undefined jargon.
        heading_texts (plan/07-troubleshooting-backlog.md#a-3) are this
        paper's own section headings: a frequent term also named in a
        heading is assumed to be explained somewhere in that section, even
        when no explicit in-text definition pattern matched it -- papers
        dedicate headings to concepts they go on to explain in prose we
        have no cheap way to detect directly."""
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
    # >2, not >3 (plan/07-troubleshooting-backlog.md#b-1 bugfix): the guard
    # compares the *unstripped* length, so it must allow the stripped
    # result to be as short as 2 chars -- otherwise a 2-letter acronym's
    # plural ("ID"/"IDs", "UI"/"UIs") is exactly 3 chars unstripped, fails
    # a ">3" check, and silently never merges with its singular form.
    if len(key) > 2 and key.endswith("s") and not key.endswith("ss"):
        key = key[:-1]
    return key

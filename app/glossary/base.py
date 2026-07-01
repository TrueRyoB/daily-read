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
    def extract(self, full_text: str) -> list[GlossaryEntry]:
        """Return glossary entries for the terms worth surfacing in this text."""
        ...

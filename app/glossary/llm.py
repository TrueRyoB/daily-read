"""Placeholder for a future LLM-backed GlossaryExtractor.

Not implemented today: the user chose the fully local, $0-cost heuristic
strategy (heuristic.py) as the default. This module exists purely so that
switching strategies later is a single new file, not a pipeline redesign.

Expected implementation shape when this is built:
  - Model: a cheap model (e.g. Claude Haiku) to keep per-paper cost low --
    this is a glossary lookup task, not one requiring frontier reasoning.
  - Input: candidate terms narrowed by heuristic.py's frequency/pattern
    filters first, not the raw full text, to bound cost and latency.
  - Output: the same GlossaryEntry shape HeuristicGlossaryExtractor
    produces, with source="llm_generated" so the UI can label confidence
    differently from the free heuristic entries.
  - Config: an API key read from an environment variable (e.g.
    ANTHROPIC_API_KEY), never hardcoded.
  - Caching: cache by a hash of the input text so reprocessing the same
    paper doesn't re-bill the API.

To activate once implemented: set GLOSSARY_STRATEGY=llm (see factory.py).
"""

from __future__ import annotations

from app.models import GlossaryEntry


class LLMGlossaryExtractor:
    def extract(self, full_text: str, known_names: list[str] | None = None) -> list[GlossaryEntry]:
        raise NotImplementedError(
            "LLM-backed glossary extraction is not implemented yet. "
            "Use GLOSSARY_STRATEGY=heuristic (the default), or implement "
            "this class -- see the module docstring for the expected shape."
        )

"""Selects a GlossaryExtractor implementation.

This is the seam the user asked for: switching glossary strategies later
(e.g. to an LLM-backed one, if the free heuristic proves unsatisfying)
means setting GLOSSARY_STRATEGY, not touching pipeline.py.
"""

from __future__ import annotations

import os

from app.glossary.base import GlossaryExtractor
from app.glossary.heuristic import HeuristicGlossaryExtractor

_DEFAULT_STRATEGY = "heuristic"


def get_extractor(strategy: str | None = None) -> GlossaryExtractor:
    strategy = (strategy or os.environ.get("GLOSSARY_STRATEGY", _DEFAULT_STRATEGY)).lower()
    if strategy == "heuristic":
        return HeuristicGlossaryExtractor()
    if strategy == "llm":
        from app.glossary.llm import LLMGlossaryExtractor  # lazy: keeps this an optional path

        return LLMGlossaryExtractor()
    raise ValueError(f"Unknown GLOSSARY_STRATEGY: {strategy!r} (expected 'heuristic' or 'llm')")

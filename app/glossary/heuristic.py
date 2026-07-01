"""Free, fully local glossary strategy: no LLM calls, no network access.

Two techniques, in priority order:
  1. In-text definitions: papers almost always spell out an acronym on
     first use ("Support Vector Machine (SVM)"). This is the single most
     reliable, zero-cost signal available, so it always wins over #2.
  2. Concordance: for terms that recur often but the paper never defines
     in-line, we can't invent a definition for free -- instead we
     aggregate every sentence the term appears in, so the reader sees all
     of its usage context in one place instead of re-deriving the meaning
     each time they hit the term deep in the paper. The UI must label
     these as "usage examples", not authoritative definitions.

See base.py for the swappable-strategy contract this satisfies.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from app.models import GlossaryEntry

_DEFINITION_RE = re.compile(
    r"\b((?:[A-Z][A-Za-z\-]*\s+){1,6}[A-Z][A-Za-z\-]*)\s*\(([A-Z]{2,10})\)"
)
_CANDIDATE_RE = re.compile(r"\b(?:[A-Z][a-zA-Z\-]{2,}(?:\s+[A-Z][a-zA-Z\-]{2,}){0,3})\b")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_INITIAL_STOPWORDS = {"of", "and", "the", "for", "in", "on", "with", "a", "an", "to", "as", "at", "or"}
_STRUCTURAL_WORDS = {
    "figure", "table", "section", "chapter", "appendix", "equation",
    "introduction", "conclusion", "abstract", "references", "acknowledgments",
    "acknowledgements",
}
# Sentence-initial capitalization (or the article before a proper noun) makes common
# words look like part of a candidate term ("The Transformer Model"), which fragments
# frequency counts across "The Transformer Model" / "Transformer Model" / etc. Strip
# these from the front of a candidate before counting.
_LEADING_COMMON_WORDS = {
    "the", "this", "that", "these", "those", "our", "its", "a", "an",
    "in", "on", "at", "if", "when", "we", "you", "they", "he", "she",
    "as", "for", "with", "and", "or", "but", "so", "such", "some",
    "many", "most", "each", "every", "any", "all", "here", "there",
}

_MIN_CONCORDANCE_FREQUENCY = 3
_MAX_CONTEXT_SENTENCES = 3
_MAX_ENTRIES = 30

_DICTIONARY_PATH = Path(__file__).parent / "dictionaries" / "common_abbreviations.json"


class HeuristicGlossaryExtractor:
    """Default GlossaryExtractor: pattern-based, no external calls, $0 cost."""

    def __init__(self) -> None:
        self._bundled_dictionary = _load_bundled_dictionary()

    def extract(self, full_text: str) -> list[GlossaryEntry]:
        sentences = _SENTENCE_SPLIT_RE.split(full_text)
        entries: list[GlossaryEntry] = []
        seen_keys: set[str] = set()

        for phrase, acronym in self._find_in_text_definitions(full_text):
            key = acronym.upper()
            if key in seen_keys:
                continue
            seen_keys.add(key)
            entries.append(
                GlossaryEntry(
                    term=acronym,
                    definition=phrase,
                    contexts=_sentences_mentioning(sentences, acronym, _MAX_CONTEXT_SENTENCES),
                    source="in_text_definition",
                )
            )

        for term, count in self._frequent_candidates(full_text).items():
            if count < _MIN_CONCORDANCE_FREQUENCY or len(entries) >= _MAX_ENTRIES:
                continue
            key, initials_key = term.upper(), _initials(term)
            if key in seen_keys or initials_key in seen_keys:
                continue  # already covered by an in-text-defined acronym for this same term
            seen_keys.add(key)
            bundled_definition = self._bundled_dictionary.get(key)
            entries.append(
                GlossaryEntry(
                    term=term,
                    definition=bundled_definition,
                    contexts=_sentences_mentioning(sentences, term, _MAX_CONTEXT_SENTENCES),
                    source="bundled_dictionary" if bundled_definition else "concordance",
                )
            )

        return entries

    @staticmethod
    def _find_in_text_definitions(full_text: str) -> list[tuple[str, str]]:
        found = []
        for match in _DEFINITION_RE.finditer(full_text):
            phrase, acronym = match.group(1).strip(), match.group(2).strip()
            if _initials(phrase) == acronym.upper():
                found.append((phrase, acronym))
        return found

    @staticmethod
    def _frequent_candidates(full_text: str) -> "Counter[str]":
        counts: Counter[str] = Counter()
        for match in _CANDIDATE_RE.finditer(full_text):
            candidate = _strip_leading_common_words(match.group(0).strip())
            if not candidate:
                continue
            first_word = candidate.split()[0].lower()
            if first_word in _STRUCTURAL_WORDS or candidate.lower() in _STRUCTURAL_WORDS:
                continue
            counts[candidate] += 1
        return Counter(dict(counts.most_common()))  # most-frequent-first so _MAX_ENTRIES keeps the best


def _strip_leading_common_words(candidate: str) -> str | None:
    words = candidate.split()
    while len(words) > 1 and words[0].lower() in _LEADING_COMMON_WORDS:
        words = words[1:]
    if len(words) == 1 and words[0].lower() in _LEADING_COMMON_WORDS:
        return None
    return " ".join(words)


def _initials(phrase: str) -> str:
    words = [w for w in re.split(r"[\s\-]+", phrase) if w]
    letters = [w[0] for w in words if w.lower() not in _INITIAL_STOPWORDS and w[0].isalpha()]
    return "".join(letters).upper()


def _sentences_mentioning(sentences: list[str], term: str, limit: int) -> list[str]:
    pattern = re.compile(rf"\b{re.escape(term)}\b")
    return [s.strip() for s in sentences if pattern.search(s)][:limit]


def _load_bundled_dictionary() -> dict[str, str]:
    if not _DICTIONARY_PATH.exists():
        return {}
    with _DICTIONARY_PATH.open(encoding="utf-8") as f:
        return json.load(f)

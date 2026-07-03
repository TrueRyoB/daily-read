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

from app.glossary.base import normalize_term_key
from app.models import GlossaryEntry

_DEFINITION_RE = re.compile(
    r"\b((?:[A-Z][A-Za-z\-]*\s+){1,6}[A-Z][A-Za-z\-]*)\s*\(([A-Z]{2,10})\)"
)
# The reverse order ("SVM (Support Vector Machine)") is at least as common
# in papers as "Support Vector Machine (SVM)" -- plan/07-troubleshooting-
# backlog.md#a-3: terms defined this way were being missed entirely and
# wrongly surfaced as "undefined" in the pre-reading column.
_DEFINITION_RE_REVERSED = re.compile(
    r"\b([A-Z]{2,10})\s*\(((?:[A-Z][A-Za-z\-]*\s+){0,5}[A-Z][A-Za-z\-]*)\)"
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
_COMMON_WORDS_PATH = Path(__file__).parent / "dictionaries" / "common_english_words.txt"
_VENUE_NAMES_PATH = Path(__file__).parent / "dictionaries" / "academic_venue_names.txt"

# Proper nouns are excluded from single-word candidates entirely (plan/07-
# troubleshooting-backlog.md#b-1): person/place/organization names are
# essentially never worth defining, and unlike common-word filtering this
# can't be solved by a static list (the set of possible names is
# unbounded -- "Earth" today, some other never-listed place/person name
# tomorrow). NER via spaCy's small English model generalizes instead of
# requiring per-incident list maintenance.
#
# This deliberately only ever removes single-word candidates (see the
# `len(words) == 1` guard at the call site): a multi-word candidate built
# from a proper-noun-derived adjective ("Bayesian Inference", "Markov
# Chain") is still legitimate domain jargon, exactly like the existing
# common-word filter already protects multi-word candidates built from
# ordinary words ("Random Forest"). It also skips ALL-CAPS candidates
# ("GCN", "IEEE"): spaCy sometimes tags a short acronym as an
# organization, but an all-caps single word is far more likely to be
# legitimate domain jargon than an actual org name, and known venues/
# authors are already handled by their own dedicated mechanisms.
_NER_EXCLUDE_LABELS = {"PERSON", "NORP", "FAC", "ORG", "GPE", "LOC"}

# Lazily loaded (~1s the first time) and cached at module level so it's
# paid once per process, not once per paper. Sentinel string (not None)
# distinguishes "not attempted yet" from "attempted and unavailable" so a
# missing/uninstalled model degrades to skipping this filter instead of
# retrying (and failing) on every single paper.
_nlp = "unloaded"

# Per-word judgment cache (plan/07-troubleshooting-backlog.md follow-up):
# a full spaCy pass over one paper's full_text measured ~0.5-1.3s, and
# without this cache that cost was paid again on *every* paper even for
# words ("Earth", a recurring author's surname not in known_names, etc.)
# already judged before. Keyed by lowercase word -> True (excluded, judged
# a proper noun) or False (checked, not one) so a "not a proper noun"
# result is remembered too and never re-asked, not just positive hits.
# Process-lifetime only (not persisted to disk): the model itself is
# already only in-memory, and this is bounded by the same tradeoff.
_ner_judgment_cache: dict[str, bool] = {}


class HeuristicGlossaryExtractor:
    """Default GlossaryExtractor: pattern-based, no external calls, $0 cost."""

    def __init__(self) -> None:
        self._bundled_dictionary = _load_bundled_dictionary()

    def extract(
        self,
        full_text: str,
        known_names: list[str] | None = None,
        heading_texts: list[str] | None = None,
    ) -> list[GlossaryEntry]:
        """known_names (plan/05-c): the paper's own authors plus its
        reference list's authors, already parsed by tei_parse.py. Frequent
        candidates matching one of these are excluded -- e.g. "Ward" or
        "Guo" showing up as an "undefined term" because a cited author's
        surname happens to recur, rather than because it's real jargon.

        heading_texts (plan/07-troubleshooting-backlog.md#a-3): this
        paper's own section headings. A frequent candidate also named in a
        heading is assumed to be explained in that section even though no
        explicit in-text definition pattern matched -- this is the main
        lever for not wrongly claiming a term is "undefined" (papers
        define concepts in far more ways than a parenthetical acronym
        expansion, and enumerating every natural-language definition style
        as a regex doesn't converge)."""
        sentences = _SENTENCE_SPLIT_RE.split(full_text)
        entries: list[GlossaryEntry] = []
        seen_keys: set[str] = set()
        excluded_full_names, excluded_name_tokens = _build_name_exclusion_sets(known_names or [])
        excluded_ner_tokens = _build_ner_exclusion_tokens(full_text)

        for phrase, acronym in self._find_in_text_definitions(full_text):
            key = normalize_term_key(acronym)
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

        candidates = self._frequent_candidates(
            full_text, excluded_full_names, excluded_name_tokens, excluded_ner_tokens, heading_texts or []
        )
        for term, count in candidates.items():
            if count < _MIN_CONCORDANCE_FREQUENCY or len(entries) >= _MAX_ENTRIES:
                continue
            key, initials_key = normalize_term_key(term), normalize_term_key(_initials(term))
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
        for match in _DEFINITION_RE_REVERSED.finditer(full_text):
            acronym, phrase = match.group(1).strip(), match.group(2).strip()
            if _initials(phrase) == acronym.upper():
                found.append((phrase, acronym))
        return found

    @staticmethod
    def _frequent_candidates(
        full_text: str,
        excluded_full_names: set[str],
        excluded_name_tokens: set[str],
        excluded_ner_tokens: set[str],
        heading_texts: list[str],
    ) -> "Counter[str]":
        counts: Counter[str] = Counter()
        for match in _CANDIDATE_RE.finditer(full_text):
            candidate = _strip_leading_common_words(match.group(0).strip())
            if not candidate:
                continue
            words = candidate.split()
            first_word = words[0].lower()
            if first_word in _STRUCTURAL_WORDS or candidate.lower() in _STRUCTURAL_WORDS:
                continue
            # Only single-word candidates are checked against the common-word
            # list: a multi-word phrase built from ordinary words (e.g.
            # "Random Forest", "Neural Network") is still legitimate domain
            # jargon and must not be filtered just because its parts are
            # common on their own.
            if len(words) == 1 and first_word in _COMMON_ENGLISH_WORDS:
                continue
            # Publication venue/publisher names leak in from reference-list
            # text that GROBID sometimes classifies as body content instead
            # of back matter (plan/04-e) -- unlike common words, the whole
            # candidate (not just single words) is checked, since a venue
            # name is exactly the thing to block, not a component of a
            # larger legitimate term.
            if candidate.lower() in _ACADEMIC_VENUE_NAMES:
                continue
            # Proper nouns (plan/05-c): the paper's own authors and its
            # reference list's authors are known in advance (already parsed
            # elsewhere), so an exact full-name match, or a single-word
            # candidate matching one name component (surname/forename), is
            # excluded.
            if candidate.lower() in excluded_full_names:
                continue
            if len(words) == 1 and first_word in excluded_name_tokens:
                continue
            # General proper-noun detection via NER (plan/07-troubleshooting-
            # backlog.md#b-1) -- single-word, non-acronym-shaped only; see
            # the module-level comment on _NER_EXCLUDE_LABELS for why.
            if len(words) == 1 and not candidate.isupper() and first_word in excluded_ner_tokens:
                continue
            counts[candidate] += 1

        # Heading opt-out (plan/07-troubleshooting-backlog.md#a-3), applied
        # once per unique surviving candidate rather than per occurrence: a
        # paper has only a handful of headings to check against, however
        # many times the candidate itself recurs in the body.
        for candidate in list(counts.keys()):
            if _heading_contains_term(heading_texts, candidate):
                del counts[candidate]

        return Counter(dict(counts.most_common()))  # most-frequent-first so _MAX_ENTRIES keeps the best


def _build_name_exclusion_sets(known_names: list[str]) -> tuple[set[str], set[str]]:
    """Split each known name (e.g. "Thomas Kipf") into a lowercase full-name
    set (for matching a candidate like "Thomas Kipf") and a single-word
    token set (for matching a bare surname like "Kipf") -- plan/05-c."""
    full_names = {name.lower() for name in known_names if name}
    tokens = {word.lower() for name in known_names for word in name.split()}
    return full_names, tokens


def _get_nlp():
    """Lazy-loaded, process-wide spaCy pipeline for proper-noun detection
    (plan/07-troubleshooting-backlog.md#b-1). Returns None (never raises)
    if spaCy or its English model isn't installed, so a missing optional
    dependency degrades to "skip this filter" instead of breaking glossary
    extraction entirely."""
    global _nlp
    if _nlp == "unloaded":
        try:
            import spacy

            _nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])
        except Exception:
            _nlp = None
    return _nlp


def _collect_single_word_ner_candidates(full_text: str) -> set[str]:
    """Cheap pre-scan (plain regex, no spaCy) for which single-word,
    non-acronym-shaped words could possibly need a proper-noun judgment --
    computed first so _build_ner_exclusion_tokens can tell whether a fresh
    spaCy pass is even necessary, without running it just to find out."""
    words: set[str] = set()
    for match in _CANDIDATE_RE.finditer(full_text):
        candidate = _strip_leading_common_words(match.group(0).strip())
        if candidate and len(candidate.split()) == 1 and not candidate.isupper():
            words.add(candidate.lower())
    return words


def _build_ner_exclusion_tokens(full_text: str) -> set[str]:
    candidate_words = _collect_single_word_ner_candidates(full_text)
    uncached = {w for w in candidate_words if w not in _ner_judgment_cache}

    if uncached:
        nlp = _get_nlp()
        if nlp is None:
            # Model unavailable: fail open (never excludes) rather than
            # retrying every paper -- cache the negative result too.
            for word in uncached:
                _ner_judgment_cache[word] = False
        else:
            found_entities: set[str] = set()
            for ent in nlp(full_text).ents:
                if ent.label_ in _NER_EXCLUDE_LABELS:
                    found_entities.update(w.lower() for w in ent.text.split())
            for word in uncached:
                _ner_judgment_cache[word] = word in found_entities
            # Opportunistic: cache any other entity tokens this same pass
            # happened to find too (free, since the pass already ran) --
            # a later paper mentioning them then needs no pass of its own.
            for word in found_entities:
                _ner_judgment_cache.setdefault(word, True)

    return {w for w in candidate_words if _ner_judgment_cache.get(w)}


def _heading_contains_term(heading_texts: list[str], term: str) -> bool:
    """True if `term` (allowing a trailing plural "s") appears in any of
    this paper's own section headings (plan/07-troubleshooting-
    backlog.md#a-3)."""
    if not heading_texts:
        return False
    pattern = re.compile(rf"\b{re.escape(term)}s?\b", re.IGNORECASE)
    return any(pattern.search(heading) for heading in heading_texts)


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
        raw = json.load(f)
    # Keyed through normalize_term_key so lookups stay consistent with the
    # normalized keys used everywhere else in extract() (the file itself
    # still reads as a plain {"LSTM": "..."} mapping on disk).
    return {normalize_term_key(k): v for k, v in raw.items()}


def _load_wordlist(path: Path) -> frozenset[str]:
    """Load a '# comment'-friendly, one-entry-per-line, lowercase-normalized
    wordlist file. Shared by common_english_words.txt (04-a) and
    academic_venue_names.txt (04-e)."""
    if not path.exists():
        return frozenset()
    words = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            words.add(line.lower())
    return frozenset(words)


_COMMON_ENGLISH_WORDS = _load_wordlist(_COMMON_WORDS_PATH)
_ACADEMIC_VENUE_NAMES = _load_wordlist(_VENUE_NAMES_PATH)

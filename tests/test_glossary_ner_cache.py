"""plan/07-troubleshooting-backlog.md follow-up: a real spaCy pass over one
paper's full_text measured ~0.5-1.3s. Without a persistent per-word cache,
that cost was paid again for every paper, even for words ("Earth", etc.)
already judged in a previous one. These tests use a fake spaCy-shaped
object (not the real model) so they can assert exactly how many times the
expensive pass actually runs, deterministically and fast.
"""

from __future__ import annotations

from app.glossary import heuristic


class _FakeEnt:
    def __init__(self, text, label):
        self.text = text
        self.label_ = label


class _FakeDoc:
    def __init__(self, ents):
        self.ents = ents


class _FakeNLP:
    """entities_by_text maps the exact input text to the list of
    (entity_text, label) pairs a real spaCy call would have found in it."""

    def __init__(self, entities_by_text):
        self.call_count = 0
        self._entities_by_text = entities_by_text

    def __call__(self, text):
        self.call_count += 1
        return _FakeDoc([_FakeEnt(t, label) for t, label in self._entities_by_text.get(text, [])])


def test_second_call_with_already_judged_word_skips_spacy_entirely(monkeypatch):
    text1 = "Earth is large. Earth is round. Earth is old."
    fake_nlp = _FakeNLP({text1: [("Earth", "LOC")]})
    monkeypatch.setattr(heuristic, "_get_nlp", lambda: fake_nlp)

    tokens1 = heuristic._build_ner_exclusion_tokens(text1)
    assert tokens1 == {"earth"}
    assert fake_nlp.call_count == 1

    text2 = "Earth is discussed here too, again and again."
    tokens2 = heuristic._build_ner_exclusion_tokens(text2)
    assert tokens2 == {"earth"}
    assert fake_nlp.call_count == 1  # no second pass -- "earth" was already judged


def test_negative_judgment_is_also_cached_and_not_rechecked(monkeypatch):
    # "not a proper noun" must be remembered too, not just positive hits --
    # otherwise every paper mentioning a common, already-cleared word would
    # still trigger a fresh pass just to reconfirm it isn't one.
    text1 = "Widgets are used throughout the study. Widgets are configurable easily."
    fake_nlp = _FakeNLP({text1: []})  # "widgets" -> not an entity
    monkeypatch.setattr(heuristic, "_get_nlp", lambda: fake_nlp)

    tokens1 = heuristic._build_ner_exclusion_tokens(text1)
    assert tokens1 == set()
    assert fake_nlp.call_count == 1

    # "Widgets" is the only capitalized (candidate) word here -- no other
    # sentence-initial capitalization to accidentally introduce a second,
    # not-yet-cached candidate.
    text2 = "Widgets remain useful in later sections of this work as well."
    tokens2 = heuristic._build_ner_exclusion_tokens(text2)
    assert tokens2 == set()
    assert fake_nlp.call_count == 1


def test_a_genuinely_new_word_still_triggers_a_fresh_pass(monkeypatch):
    text1 = "Earth is large."
    text2 = "Mars is red. Mars is small."
    fake_nlp = _FakeNLP({text1: [("Earth", "LOC")], text2: [("Mars", "LOC")]})
    monkeypatch.setattr(heuristic, "_get_nlp", lambda: fake_nlp)

    heuristic._build_ner_exclusion_tokens(text1)
    assert fake_nlp.call_count == 1

    tokens2 = heuristic._build_ner_exclusion_tokens(text2)
    assert tokens2 == {"mars"}
    assert fake_nlp.call_count == 2  # "mars" wasn't cached yet -- a real pass was required


def test_mixed_cached_and_new_words_only_runs_once_more(monkeypatch):
    text1 = "Earth is large."
    fake_nlp = _FakeNLP({})
    monkeypatch.setattr(heuristic, "_get_nlp", lambda: fake_nlp)
    fake_nlp._entities_by_text[text1] = [("Earth", "LOC")]
    heuristic._build_ner_exclusion_tokens(text1)
    assert fake_nlp.call_count == 1

    # "earth" is already cached; "mars" is new -- one pass still covers both.
    text2 = "Mars and Earth are both discussed in this paper repeatedly."
    fake_nlp._entities_by_text[text2] = [("Mars", "LOC")]
    tokens2 = heuristic._build_ner_exclusion_tokens(text2)
    assert tokens2 == {"earth", "mars"}
    assert fake_nlp.call_count == 2


def test_opportunistic_caching_of_incidental_entities_from_the_same_pass(monkeypatch):
    # A pass triggered to judge "pluto" incidentally also finds "neptune" in
    # the same text -- caching that too means a later paper mentioning only
    # "neptune" needs no pass of its own.
    text1 = "Pluto is small. Neptune is farther away in this discussion."
    fake_nlp = _FakeNLP({text1: [("Pluto", "LOC"), ("Neptune", "LOC")]})
    monkeypatch.setattr(heuristic, "_get_nlp", lambda: fake_nlp)

    heuristic._build_ner_exclusion_tokens(text1)
    assert fake_nlp.call_count == 1
    assert heuristic._ner_judgment_cache.get("neptune") is True

    text2 = "Neptune is mentioned again here, several more times."
    tokens2 = heuristic._build_ner_exclusion_tokens(text2)
    assert tokens2 == {"neptune"}
    assert fake_nlp.call_count == 1  # still just the one pass from text1


def test_missing_spacy_model_fails_open_and_is_cached(monkeypatch):
    monkeypatch.setattr(heuristic, "_get_nlp", lambda: None)
    tokens = heuristic._build_ner_exclusion_tokens("Earth is large. Earth is round. Earth is old.")
    assert tokens == set()
    assert heuristic._ner_judgment_cache.get("earth") is False

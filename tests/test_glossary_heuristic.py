from app.glossary.heuristic import HeuristicGlossaryExtractor


def test_in_text_definition_is_detected_and_prioritized():
    text = (
        "We use a Support Vector Machine (SVM) for classification. "
        "The SVM is trained on labeled data. "
        "Later we compare the SVM against a baseline. "
        "The SVM achieves higher accuracy than the baseline."
    )
    entries = HeuristicGlossaryExtractor().extract(text)
    svm_entries = [e for e in entries if e.term == "SVM"]
    assert len(svm_entries) == 1
    entry = svm_entries[0]
    assert entry.definition == "Support Vector Machine"
    assert entry.source == "in_text_definition"
    assert any("SVM" in c for c in entry.contexts)

    # The full phrase itself should not also show up as a separate, redundant entry.
    assert not any(e.term == "Support Vector Machine" for e in entries)


def test_frequent_undefined_term_becomes_concordance_entry():
    text = (
        "The Transformer Model processes the input sequence. "
        "We fine-tune the Transformer Model on our dataset. "
        "Results show the Transformer Model outperforms prior work. "
        "This section analyzes why the Transformer Model succeeds."
    )
    entries = HeuristicGlossaryExtractor().extract(text)
    matches = [e for e in entries if e.term == "Transformer Model"]
    assert len(matches) == 1
    entry = matches[0]
    assert entry.source == "concordance"
    assert entry.definition is None
    assert len(entry.contexts) > 0


def test_infrequent_term_is_not_included():
    text = "The Random Widget appears exactly once in this paper and nowhere else."
    entries = HeuristicGlossaryExtractor().extract(text)
    assert not any(e.term == "Random Widget" for e in entries)


def test_bundled_dictionary_supplies_definition_for_known_abbreviation():
    text = (
        "This work applies NLP techniques to the task. "
        "Our NLP pipeline includes tokenization and parsing. "
        "The NLP model is evaluated on a held-out set."
    )
    entries = HeuristicGlossaryExtractor().extract(text)
    matches = [e for e in entries if e.term == "NLP"]
    assert len(matches) == 1
    assert matches[0].source == "bundled_dictionary"
    assert matches[0].definition == "Natural Language Processing"


def test_structural_words_like_figure_are_excluded():
    text = "See Figure 1 for details. Figure 1 shows the pipeline. Figure 1 is referenced again here."
    entries = HeuristicGlossaryExtractor().extract(text)
    assert not any(e.term.lower().startswith("figure") for e in entries)


def test_common_single_word_is_excluded_even_when_frequent():
    text = (
        "Various results are shown below. Various methods were tried. "
        "Various configurations were tested. Various outcomes were observed."
    )
    entries = HeuristicGlossaryExtractor().extract(text)
    assert not any(e.term == "Various" for e in entries)


def test_multiword_phrase_of_common_words_is_not_excluded():
    # "Random" and "Forest" are both ordinary English words individually,
    # but the combined phrase is legitimate domain jargon and must survive
    # the common-word filter, which only ever looks at single-word candidates.
    text = (
        "Random Forest is used as a baseline. Random Forest performs well. "
        "We tune Random Forest hyperparameters. Random Forest results follow."
    )
    entries = HeuristicGlossaryExtractor().extract(text)
    assert any(e.term == "Random Forest" for e in entries)


def test_academic_venue_names_are_excluded_even_when_frequent():
    # Reproduces reference-list noise observed in real data (plan/04-e):
    # venue/publisher names leaking into body text GROBID classified as
    # content rather than back matter. Sentences constructed so "IEEE"
    # appears as a clean standalone single-word candidate (not merged into
    # a leading-word run like "The IEEE" before stripping) at least 3 times.
    text = (
        "The IEEE standard is used here. Our results follow IEEE guidelines. "
        "IEEE remains the reference standard. This work follows IEEE conventions."
    )
    entries = HeuristicGlossaryExtractor().extract(text)
    assert not any(e.term == "IEEE" for e in entries)


def test_singular_and_plural_forms_are_not_counted_as_separate_terms():
    # Each variant is repeated 3+ times on its own (independently clearing
    # the frequency threshold) to reproduce the real-world bug: without
    # normalization, "GNN" and "GNNs" each qualify individually and both
    # end up as separate, near-duplicate glossary entries.
    text = (
        "GNN models are widely used. GNN methods scale poorly to large graphs. "
        "GNN variants exist in the literature. GNNs have known limitations. "
        "GNNs are popular in practice. GNNs are studied extensively here."
    )
    entries = HeuristicGlossaryExtractor().extract(text)
    matching = [e for e in entries if e.term.rstrip("s").upper() == "GNN"]
    assert len(matching) == 1


def test_missed_academic_common_words_are_now_excluded():
    # plan/05-c: reported as still slipping through -- e.g. "PhD" and
    # "Marked" (a passive-voice participle) were flagged as undefined terms.
    text = (
        "The PhD student marked each sample by hand. Every sample was "
        "marked twice for consistency. The marked samples were reviewed. "
        "Marked errors were corrected before analysis."
    )
    entries = HeuristicGlossaryExtractor().extract(text)
    assert not any(e.term.lower() == "phd" for e in entries)
    assert not any(e.term.lower() == "marked" for e in entries)


def test_known_author_names_are_excluded_from_candidates():
    # plan/05-c: proper nouns (cited authors' names) were being flagged as
    # undefined terms. known_names comes from the paper's own teiHeader
    # authors plus its reference list's authors (already parsed elsewhere).
    text = (
        "Ward and colleagues proposed this approach. Ward later refined it. "
        "The method by Ward remains influential. Ward's results were replicated."
    )
    entries = HeuristicGlossaryExtractor().extract(text, known_names=["Ian R Ward"])
    assert not any(e.term == "Ward" for e in entries)


def test_full_name_match_also_excludes_the_whole_phrase():
    text = (
        "Jane Smith introduced this model. Jane Smith later extended it. "
        "The framework by Jane Smith is widely cited. Jane Smith remains active."
    )
    entries = HeuristicGlossaryExtractor().extract(text, known_names=["Jane Smith"])
    assert not any(e.term == "Jane Smith" for e in entries)


def test_definition_immediately_after_heading_without_punctuation_is_missed():
    # Documents a real fragility in the greedy phrase-before-"(ABBR)" regex
    # (found via tests/test_pipeline_golden_fixture.py): if the acronym
    # definition is glued directly onto a preceding capitalized word with
    # no punctuation between them (e.g. a heading joined to body text with
    # a plain space), the regex greedily pulls that word into the phrase
    # and the initials no longer match the acronym, so the match is
    # silently dropped. pipeline.py works around this by joining units
    # with ". " instead of a plain space (plan/04-g) -- this test guards
    # the regex behavior itself so that workaround stays necessary/correct.
    glued = "1 Introduction Graph Neural Network (GNN) models are widely used."
    assert not any(e.term == "GNN" for e in HeuristicGlossaryExtractor().extract(glued))

    with_boundary = "1 Introduction. Graph Neural Network (GNN) models are widely used."
    gnn = next(e for e in HeuristicGlossaryExtractor().extract(with_boundary) if e.term == "GNN")
    assert gnn.source == "in_text_definition"

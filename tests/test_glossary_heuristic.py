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

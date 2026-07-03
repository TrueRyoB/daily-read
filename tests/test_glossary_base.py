from __future__ import annotations

from app.glossary.base import normalize_term_key


def test_normal_plural_is_merged_with_singular():
    assert normalize_term_key("GNNs") == normalize_term_key("GNN")


def test_two_letter_acronym_plural_is_merged_with_singular():
    # plan/07-troubleshooting-backlog.md#b-1 bugfix: the guard used to
    # compare the *unstripped* length against > 3, so a 2-letter acronym's
    # plural ("IDs", 3 chars unstripped) failed the check and never merged
    # with its singular ("ID").
    assert normalize_term_key("IDs") == normalize_term_key("ID")
    assert normalize_term_key("UIs") == normalize_term_key("UI")


def test_short_word_ending_in_s_is_not_over_stripped():
    # "as"/"is" should not become single, nonsensical letters.
    assert normalize_term_key("as") == "as"
    assert normalize_term_key("is") == "is"


def test_double_s_ending_is_not_stripped():
    assert normalize_term_key("class") == "class"

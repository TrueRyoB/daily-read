from __future__ import annotations

from app import db, rendering


def test_mark_term_known_and_lookup_key(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.mark_term_known(conn, "GNN")
        assert db.known_term_keys(conn) == {"gnn"}
    finally:
        conn.close()


def test_mark_term_known_matches_singular_plural_variants(isolated_data_dir):
    # Same normalization key as plan/04-f, so marking "GNN" known also
    # suppresses "GNNs" without a second call.
    conn = db.get_connection()
    try:
        db.mark_term_known(conn, "GNN")
        keys = db.known_term_keys(conn)
        from app.glossary.base import normalize_term_key

        assert normalize_term_key("GNNs") in keys
    finally:
        conn.close()


def test_marking_the_same_term_twice_does_not_duplicate(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.mark_term_known(conn, "GNN")
        db.mark_term_known(conn, "gnn")  # different casing, same key
        assert len(db.known_term_keys(conn)) == 1
    finally:
        conn.close()


def test_filter_known_terms_drops_matching_entries():
    glossary = [
        {"term": "GNN", "definition": None, "contexts": [], "source": "concordance"},
        {"term": "LSTM", "definition": "Long Short-Term Memory", "contexts": [], "source": "bundled_dictionary"},
    ]
    filtered = rendering.filter_known_terms(glossary, {"gnn"})
    assert [e["term"] for e in filtered] == ["LSTM"]


def test_filter_known_terms_is_noop_with_empty_known_set():
    glossary = [{"term": "GNN", "definition": None, "contexts": [], "source": "concordance"}]
    assert rendering.filter_known_terms(glossary, set()) == glossary

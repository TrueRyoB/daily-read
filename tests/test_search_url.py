from __future__ import annotations

from app import rendering


def test_search_url_includes_term_and_paper_title_as_context():
    url = rendering.search_url("GAT", "Graph Attention Networks for Retrieval")
    assert url.startswith("https://www.google.com/search?q=")
    assert "GAT" in url
    assert "Graph+Attention+Networks" in url or "Graph%20Attention%20Networks" in url


def test_search_url_uses_env_var_template_when_set(monkeypatch):
    monkeypatch.setenv("SEARCH_ENGINE_URL_TEMPLATE", "https://duckduckgo.com/?q={query}")
    url = rendering.search_url("GAT", "Some Paper")
    assert url.startswith("https://duckduckgo.com/?q=")


def test_search_url_falls_back_to_google_when_env_var_unset(monkeypatch):
    monkeypatch.delenv("SEARCH_ENGINE_URL_TEMPLATE", raising=False)
    url = rendering.search_url("GAT", "Some Paper")
    assert url.startswith("https://www.google.com/search?q=")


def test_search_url_truncates_title_to_first_clause_before_colon():
    # plan/07-troubleshooting-backlog.md#a-3: the full title over-narrowed
    # the query; the part before a colon/dash subtitle separator is usually
    # the general topic.
    url = rendering.search_url(
        "GAT", "Attention-Based Graph Neural Networks: A Case Study on Sparse Retrieval Benchmarks"
    )
    assert "A+Case+Study" not in url and "A%20Case%20Study" not in url
    assert "Attention-Based+Graph+Neural+Networks" in url or "Attention-Based%20Graph%20Neural%20Networks" in url


def test_search_url_truncates_long_title_without_separator_to_first_few_words():
    url = rendering.search_url(
        "GAT", "A Long Academic Title With Many Words That Keeps Going Well Past Six Words Total"
    )
    assert "Well+Past+Six+Words+Total" not in url and "Well%20Past%20Six%20Words%20Total" not in url
    assert "A+Long+Academic+Title+With+Many" in url or "A%20Long%20Academic%20Title%20With%20Many" in url


def test_search_url_leaves_short_title_unchanged():
    url = rendering.search_url("GAT", "Graph Attention Networks for Retrieval")
    assert "Graph+Attention+Networks+for+Retrieval" in url or "Graph%20Attention%20Networks%20for%20Retrieval" in url

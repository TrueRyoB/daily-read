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

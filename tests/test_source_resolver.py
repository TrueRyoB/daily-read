import pytest

from app.ingestion.source_resolver import resolve_url


class FakeResponse:
    def __init__(self, content=b"", text="", headers=None, status_code=200):
        self.content = content
        self.text = text
        self.headers = headers or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    """Stands in for httpx.Client so tests never touch the network."""

    def __init__(self, responses: dict):
        self._responses = responses
        self.requested_urls: list[str] = []

    def get(self, url):
        self.requested_urls.append(url)
        return self._responses[url]

    def close(self):
        pass


def test_direct_pdf_url_downloads_immediately():
    url = "https://example.com/paper.pdf"
    client = FakeClient({url: FakeResponse(content=b"%PDF fake", headers={"content-type": "application/pdf"})})

    resolved = resolve_url(url, client=client)

    assert resolved.pdf_bytes == b"%PDF fake"
    assert resolved.source_label == url
    assert client.requested_urls == [url]


def test_arxiv_abstract_page_is_rewritten_to_pdf_path():
    abs_url = "https://arxiv.org/abs/2401.12345"
    pdf_url = "https://arxiv.org/pdf/2401.12345"
    client = FakeClient({pdf_url: FakeResponse(content=b"%PDF arxiv", headers={"content-type": "application/pdf"})})

    resolved = resolve_url(abs_url, client=client)

    assert resolved.pdf_bytes == b"%PDF arxiv"
    assert resolved.source_label == abs_url  # original URL preserved for the history list
    assert client.requested_urls == [pdf_url]


def test_generic_landing_page_falls_back_to_first_pdf_link():
    page_url = "https://example.com/paper-landing"
    pdf_url = "https://example.com/files/paper.pdf"
    html = f'<html><body><a href="{pdf_url}">Download PDF</a></body></html>'
    client = FakeClient(
        {
            page_url: FakeResponse(text=html, headers={"content-type": "text/html"}),
            pdf_url: FakeResponse(content=b"%PDF landing", headers={"content-type": "application/pdf"}),
        }
    )

    resolved = resolve_url(page_url, client=client)

    assert resolved.pdf_bytes == b"%PDF landing"
    assert client.requested_urls == [page_url, pdf_url]


def test_relative_pdf_link_is_resolved_against_base_url():
    page_url = "https://example.com/journal/article123"
    absolute_pdf_url = "https://example.com/files/download.pdf"
    html = '<html><body><a href="/files/download.pdf">PDF</a></body></html>'
    client = FakeClient(
        {
            page_url: FakeResponse(text=html, headers={"content-type": "text/html"}),
            absolute_pdf_url: FakeResponse(content=b"%PDF relative", headers={"content-type": "application/pdf"}),
        }
    )

    resolved = resolve_url(page_url, client=client)

    assert resolved.pdf_bytes == b"%PDF relative"


def test_no_pdf_link_found_raises():
    page_url = "https://example.com/no-pdf-here"
    html = "<html><body>No downloads available.</body></html>"
    client = FakeClient({page_url: FakeResponse(text=html, headers={"content-type": "text/html"})})

    with pytest.raises(ValueError):
        resolve_url(page_url, client=client)

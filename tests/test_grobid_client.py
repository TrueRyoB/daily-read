from __future__ import annotations

import httpx
import pytest

from app.pdf import grobid_client


class _FakeResponse:
    status_code = 200
    text = "<TEI/>"


def test_consolidation_enabled_by_default(tmp_path, monkeypatch):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    captured = {}

    def fake_post(url, *, files, data, timeout):
        captured["data"] = data
        return _FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.delenv(grobid_client._CONSOLIDATE_ENV_VAR, raising=False)

    grobid_client.extract_tei(str(pdf_path))

    assert captured["data"]["consolidateHeader"] == "1"
    assert captured["data"]["consolidateCitations"] == "1"
    assert captured["data"]["generateIDs"] == "1"
    assert captured["data"]["teiCoordinates"] == "figure"


def test_consolidation_can_be_disabled_via_env_var(tmp_path, monkeypatch):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    captured = {}

    def fake_post(url, *, files, data, timeout):
        captured["data"] = data
        return _FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setenv(grobid_client._CONSOLIDATE_ENV_VAR, "0")

    grobid_client.extract_tei(str(pdf_path))

    assert captured["data"]["consolidateHeader"] == "0"
    assert captured["data"]["consolidateCitations"] == "0"
    # generateIDs is local (no external lookup), stays on regardless.
    assert captured["data"]["generateIDs"] == "1"


def test_timeout_is_turned_into_a_clear_runtime_error(tmp_path, monkeypatch):
    # plan/05-f: previously uncaught, this would raise a raw httpx exception
    # out of the (now background) processing thread instead of a message a
    # reader could act on.
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    def fake_post(url, *, files, data, timeout):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(RuntimeError, match="秒以内"):
        grobid_client.extract_tei(str(pdf_path))


def test_timeout_is_configurable_via_env_var(tmp_path, monkeypatch):
    # plan/07-troubleshooting-backlog.md#a-4: tunable without a code change
    # in case disabling consolidation doesn't fully eliminate slow runs.
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    captured = {}

    def fake_post(url, *, files, data, timeout):
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setenv(grobid_client._TIMEOUT_ENV_VAR, "300")

    grobid_client.extract_tei(str(pdf_path))

    assert captured["timeout"] == 300.0


def test_timeout_falls_back_to_default_when_env_var_is_not_a_number(tmp_path, monkeypatch):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    captured = {}

    def fake_post(url, *, files, data, timeout):
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setenv(grobid_client._TIMEOUT_ENV_VAR, "not-a-number")

    grobid_client.extract_tei(str(pdf_path))

    assert captured["timeout"] == grobid_client._DEFAULT_REQUEST_TIMEOUT

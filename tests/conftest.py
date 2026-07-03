"""Shared pytest fixtures.

`storage.DATA_DIR`/`PAPERS_DIR` and `db.DB_PATH` are hardcoded to the real
repo `data/` directory (see app/storage.py, app/db.py) -- there is no env-var
seam. Any test that runs pipeline.py end-to-end must redirect these into a
tmp_path first, or it will write real files into and insert real rows into
the developer's actual data/daily-read.db. Request `isolated_data_dir`
explicitly in any test that calls into pipeline.py/storage.py/db.py.
"""

from __future__ import annotations

import pytest

from app import db, storage


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    papers_dir = tmp_path / "papers"
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "PAPERS_DIR", papers_dir)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "daily-read.db")
    return tmp_path

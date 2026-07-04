"""plan/07-troubleshooting-backlog.md#b-4改訂: the calendar is grouped by
when the reader logged an *interpretation* of a paper, not by when GROBID
happened to finish parsing it -- parsing a PDF isn't the same as having
read/understood it.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import db, rendering
from app.main import app


def _entry(date, **kwargs):
    base = {"id": 1, "date": date, "memo": "", "papers": [], "links": []}
    base.update(kwargs)
    return base


def test_build_calendar_month_places_entry_on_correct_day():
    entries = [_entry("2026-07-15", memo="thoughts")]
    result = rendering.build_calendar_month(entries, 2026, 7)
    assert result["year"] == 2026
    assert result["month"] == 7

    matching_cells = [cell for week in result["weeks"] for cell in week if cell is not None and cell["day"] == 15]
    assert len(matching_cells) == 1
    assert matching_cells[0]["entries"] == entries
    assert matching_cells[0]["overflow_count"] == 0


def test_build_calendar_month_days_outside_the_month_are_none():
    result = rendering.build_calendar_month([], 2026, 7)
    first_week = result["weeks"][0]
    # July 2026 starts on a Wednesday -- Sun/Mon/Tue of the first week
    # belong to June and must render as empty cells, not day 0.
    assert first_week[0] is None


def test_build_calendar_month_ignores_entries_from_other_months():
    entries = [_entry("2026-06-15", memo="wrong month")]
    result = rendering.build_calendar_month(entries, 2026, 7)
    all_entries = [e for week in result["weeks"] for cell in week if cell for e in cell["all_entries"]]
    assert all_entries == []


def test_build_calendar_month_groups_multiple_entries_on_the_same_day():
    entries = [_entry("2026-07-15", id=1), _entry("2026-07-15", id=2)]
    result = rendering.build_calendar_month(entries, 2026, 7)
    cell = next(cell for week in result["weeks"] for cell in week if cell and cell["day"] == 15)
    assert len(cell["all_entries"]) == 2


def test_build_calendar_month_caps_entries_shown_and_reports_overflow():
    # plan/07-troubleshooting-backlog.md#b-4改訂 bugfix: a real day in
    # production data had 12 entries, silently clipped by a fixed-height
    # CSS cell. The data layer now caps what's shown directly and reports
    # the rest via overflow_count instead.
    entries = [_entry("2026-07-15", id=i) for i in range(12)]
    result = rendering.build_calendar_month(entries, 2026, 7)
    cell = next(cell for week in result["weeks"] for cell in week if cell and cell["day"] == 15)
    assert len(cell["entries"]) == 3
    assert len(cell["all_entries"]) == 12
    assert cell["overflow_count"] == 9


def test_interpretations_json_groups_by_date():
    entries = [_entry("2026-07-15", id=1), _entry("2026-07-16", id=2), _entry("2026-07-15", id=3)]
    import json

    payload = json.loads(rendering.interpretations_json(entries))
    assert len(payload["2026-07-15"]) == 2
    assert len(payload["2026-07-16"]) == 1


def test_creating_an_interpretation_shows_up_on_the_calendar(isolated_data_dir):
    client = TestClient(app)
    response = client.post(
        "/interpretations",
        json={"date": "2026-07-15", "memo": "Key insight about GNNs", "paper_ids": [], "links": []},
    )
    assert response.status_code == 200

    html = client.get("/calendar?month=2026-07").text
    assert "Key insight about GNNs" in html
    assert "prev_month" not in html  # sanity: no leaked template var name
    assert "month=2026-06" in html  # prev-month nav link
    assert "month=2026-08" in html  # next-month nav link


def test_interpretation_with_no_papers_is_allowed(isolated_data_dir):
    # "just musings" entries are explicitly allowed -- no paper required.
    response = TestClient(app).post(
        "/interpretations", json={"date": "2026-07-15", "memo": "just a passing thought", "paper_ids": [], "links": []}
    )
    assert response.status_code == 200
    assert response.json()["papers"] == []


def test_interpretation_links_multiple_and_related_papers(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.insert_paper(
            conn, paper_id="p1", title="Related Paper", source="s.pdf",
            created_at="2026-07-01T00:00:00+00:00", word_count=1, est_minutes=1,
        )
    finally:
        conn.close()

    response = TestClient(app).post(
        "/interpretations",
        json={
            "date": "2026-07-15",
            "memo": "connects to prior work",
            "paper_ids": ["p1"],
            "links": ["https://example.com/a", "https://example.com/b"],
        },
    )
    body = response.json()
    assert body["papers"] == [{"id": "p1", "title": "Related Paper"}]
    assert body["links"] == ["https://example.com/a", "https://example.com/b"]


def test_interpretation_date_accepts_past_and_future_without_validation(isolated_data_dir):
    # Explicitly a self-contained personal log -- no min/max date checks.
    client = TestClient(app)
    past = client.post("/interpretations", json={"date": "1999-01-01", "memo": "old", "paper_ids": [], "links": []})
    future = client.post("/interpretations", json={"date": "2099-12-31", "memo": "future", "paper_ids": [], "links": []})
    assert past.status_code == 200
    assert future.status_code == 200


def test_create_interpretation_requires_a_date(isolated_data_dir):
    response = TestClient(app).post("/interpretations", json={"date": "  ", "memo": "no date", "paper_ids": [], "links": []})
    assert response.status_code == 400


def test_deleting_an_interpretation_removes_it_from_the_calendar(isolated_data_dir):
    client = TestClient(app)
    created = client.post(
        "/interpretations", json={"date": "2026-07-15", "memo": "to be deleted", "paper_ids": [], "links": []}
    ).json()

    delete_response = client.delete(f"/interpretations/{created['id']}")
    assert delete_response.status_code == 200

    html = client.get("/calendar?month=2026-07").text
    assert "to be deleted" not in html


def test_delete_nonexistent_interpretation_404s(isolated_data_dir):
    assert TestClient(app).delete("/interpretations/999999").status_code == 404


def test_calendar_route_defaults_to_current_month_on_malformed_param(isolated_data_dir):
    response = TestClient(app).get("/calendar?month=not-a-month")
    assert response.status_code == 200


def test_calendar_widget_embedded_on_index_page(isolated_data_dir):
    # plan/07-troubleshooting-backlog.md: a one-line nav link to /calendar
    # was easy to miss entirely -- the whole widget (grid + creation form)
    # is now embedded directly on the index page instead.
    html = TestClient(app).get("/").text
    assert 'class="calendar-view"' in html
    assert 'class="calendar-grid"' in html
    assert 'id="interpretation-form"' in html
    assert 'href="/calendar?month=' in html  # month-nav links still work for direct bookmarks


def test_calendar_nav_link_is_not_in_the_shared_header(isolated_data_dir):
    # plan/07-troubleshooting-backlog.md#b-4改訂: moved out of base.html's
    # header (no real rationale for being there) into index.html only.
    html = TestClient(app).get("/calendar").text
    header = html.split("</header>")[0]
    assert "/calendar" not in header


def test_interpretation_date_field_defaults_to_today(isolated_data_dir):
    import datetime as _dt

    html = TestClient(app).get("/calendar").text
    today = _dt.datetime.now(_dt.timezone.utc).date().isoformat()
    assert f'<input type="date" name="date" value="{today}" required />' in html


def test_interpretation_paper_picker_has_a_search_input(isolated_data_dir, tmp_path, monkeypatch):
    from app import pipeline
    from tests.helpers import blank_pdf, load_golden_tei

    monkeypatch.setattr(pipeline, "extract_tei", lambda pdf_path: load_golden_tei())
    pipeline.process_upload("sample.pdf", open(blank_pdf(tmp_path, pages=2), "rb").read())

    html = TestClient(app).get("/calendar").text
    assert 'data-role="paper-search"' in html
    assert 'data-role="paper-options"' in html

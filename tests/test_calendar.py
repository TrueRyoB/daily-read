"""plan/07-troubleshooting-backlog.md#b-4: papers grouped by the date they
were added, calendar-grid style.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import db, rendering
from app.main import app


def test_build_calendar_month_places_paper_on_correct_day():
    papers = [{"id": "p1", "title": "Paper One", "created_at": "2026-07-15T10:00:00+00:00"}]
    result = rendering.build_calendar_month(papers, 2026, 7)
    assert result["year"] == 2026
    assert result["month"] == 7

    matching_cells = [
        cell for week in result["weeks"] for cell in week if cell is not None and cell["day"] == 15
    ]
    assert len(matching_cells) == 1
    assert matching_cells[0]["papers"] == papers


def test_build_calendar_month_days_outside_the_month_are_none():
    result = rendering.build_calendar_month([], 2026, 7)
    first_week = result["weeks"][0]
    # July 2026 starts on a Wednesday -- Sun/Mon/Tue of the first week
    # belong to June and must render as empty cells, not day 0.
    assert first_week[0] is None


def test_build_calendar_month_ignores_papers_from_other_months():
    papers = [{"id": "p1", "title": "Wrong Month", "created_at": "2026-06-15T10:00:00+00:00"}]
    result = rendering.build_calendar_month(papers, 2026, 7)
    all_papers = [p for week in result["weeks"] for cell in week if cell for p in cell["papers"]]
    assert all_papers == []


def test_build_calendar_month_groups_multiple_papers_on_the_same_day():
    papers = [
        {"id": "p1", "title": "First", "created_at": "2026-07-15T09:00:00+00:00"},
        {"id": "p2", "title": "Second", "created_at": "2026-07-15T14:00:00+00:00"},
    ]
    result = rendering.build_calendar_month(papers, 2026, 7)
    cell = next(cell for week in result["weeks"] for cell in week if cell and cell["day"] == 15)
    assert len(cell["papers"]) == 2


def test_calendar_route_renders_papers_and_nav_links(isolated_data_dir):
    conn = db.get_connection()
    try:
        db.insert_paper(
            conn,
            paper_id="p1",
            title="A Test Paper",
            source="s.pdf",
            created_at="2026-07-15T10:00:00+00:00",
            word_count=100,
            est_minutes=1,
        )
    finally:
        conn.close()

    html = TestClient(app).get("/calendar?month=2026-07").text
    assert "A Test Paper" in html
    assert '/papers/p1' in html
    assert "prev_month" not in html  # sanity: no leaked template var name
    assert "month=2026-06" in html  # prev-month nav link
    assert "month=2026-08" in html  # next-month nav link


def test_calendar_route_defaults_to_current_month_on_malformed_param(isolated_data_dir):
    response = TestClient(app).get("/calendar?month=not-a-month")
    assert response.status_code == 200


def test_calendar_nav_link_present_on_index_page(isolated_data_dir):
    html = TestClient(app).get("/").text
    assert 'href="/calendar"' in html

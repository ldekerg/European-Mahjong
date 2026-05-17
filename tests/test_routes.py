"""
Integration tests for FastAPI routes.
Uses the in-memory test database defined in conftest.py.
"""

import pytest


# ── Home & Ranking ────────────────────────────────────────────────────────────

def test_home_200(client):
    r = client.get("/home")
    assert r.status_code == 200

def test_home_redirect(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (301, 302, 307, 308)

def test_ranking_200(client):
    r = client.get("/ranking")
    assert r.status_code == 200

def test_ranking_with_week(client):
    r = client.get("/ranking?week=2026-05-11")
    assert r.status_code == 200

def test_ranking_invalid_week(client):
    r = client.get("/ranking?week=not-a-date")
    assert r.status_code == 200  # falls back to today


# ── Players ───────────────────────────────────────────────────────────────────

def test_players_list_200(client):
    r = client.get("/players/")
    assert r.status_code == 200

def test_players_list_filter_mcr(client):
    r = client.get("/players/?rules=MCR")
    assert r.status_code == 200

def test_players_list_search(client):
    r = client.get("/players/?q=dupont")
    assert r.status_code == 200

def test_player_detail_200(client):
    r = client.get("/players/04290001")
    assert r.status_code == 200

def test_player_detail_not_found(client):
    r = client.get("/players/NONEXISTENT")
    assert r.status_code == 404

def test_player_apercu_200(client):
    r = client.get("/players/04290001/apercu?rules=MCR&week=2026-05-11")
    assert r.status_code == 200


# ── Tournaments ───────────────────────────────────────────────────────────────

def test_tournaments_list_200(client):
    r = client.get("/tournaments/")
    assert r.status_code == 200

def test_tournaments_list_mcr(client):
    r = client.get("/tournaments/?rules=MCR")
    assert r.status_code == 200

def test_calendar_200(client):
    r = client.get("/tournaments/calendar")
    assert r.status_code == 200

def test_tournament_detail_200(client):
    r = client.get("/tournaments/1")
    assert r.status_code == 200

def test_tournament_detail_by_ema_id(client):
    r = client.get("/tournaments/MCR_100", follow_redirects=True)
    assert r.status_code == 200

def test_tournament_detail_not_found(client):
    r = client.get("/tournaments/99999")
    assert r.status_code == 404


# ── Countries ─────────────────────────────────────────────────────────────────

def test_countries_list_200(client):
    r = client.get("/countries/")
    assert r.status_code == 200

def test_country_detail_200(client):
    r = client.get("/countries/FR")
    assert r.status_code == 200

def test_country_detail_not_found(client):
    r = client.get("/countries/ZZ")
    assert r.status_code == 404


# ── Hall of Fame ──────────────────────────────────────────────────────────────

def test_hof_200(client):
    r = client.get("/hof/")
    assert r.status_code == 200

def test_hof_medals_tab(client):
    r = client.get("/hof/?view=medals")
    assert r.status_code == 200

def test_hof_weeks_tab(client):
    r = client.get("/hof/?view=weeks")
    assert r.status_code == 200

def test_hof_records_tab(client):
    r = client.get("/hof/?view=records")
    assert r.status_code == 200


# ── Championships ─────────────────────────────────────────────────────────────

def test_championships_list_200(client):
    r = client.get("/championships/")
    assert r.status_code == 200

def test_championship_not_found(client):
    r = client.get("/championships/nonexistent-slug")
    assert r.status_code == 404

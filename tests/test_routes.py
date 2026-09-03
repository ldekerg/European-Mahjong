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


# ── MERS flag / EMA number (is_mers) ──────────────────────────────────────────

def _new_tournament_form(**overrides):
    """Minimal valid payload for POST /manage/tournaments/new."""
    data = {
        "name": "Local Cup 2026", "rules": "MCR", "tournament_type": "normal",
        "start_date": "2026-05-02", "end_date": "2026-05-03",
        "nb_players": "20", "country": "FR", "city_id": "1", "status": "actif",
    }
    data.update(overrides)
    return data


def _fetch(db, name):
    from app.models import Tournament
    db.expire_all()
    return db.query(Tournament).filter_by(name=name).first()


def test_create_tournament_no_ema_id_invented(admin_client, db_session):
    """A manually created tournament must not be given an EMA number."""
    admin_client.post("/manage/tournaments/new",
                      data=_new_tournament_form(name="No Invent 2026"),
                      follow_redirects=False)
    t = _fetch(db_session, "No Invent 2026")
    assert t is not None
    assert t.ema_id is None       # the collision bug: this used to be max+1
    assert t.is_mers is False     # checkbox absent from the payload


def test_create_tournament_mers_without_ema_id(admin_client, db_session):
    """is_mers=1 with no EMA number is legitimate and must reach the ranking."""
    from datetime import date
    from app.ranking import active_tournaments, week_monday

    admin_client.post("/manage/tournaments/new",
                      data=_new_tournament_form(name="Mers No Number 2026", is_mers="on"),
                      follow_redirects=False)
    t = _fetch(db_session, "Mers No Number 2026")
    assert t.ema_id is None
    assert t.is_mers is True

    ids = {x.id for x, _ in active_tournaments(db_session, week_monday(date(2026, 6, 1)), "MCR")}
    assert t.id in ids, "a MERS tournament without an EMA number must rank"


def test_mers_tournament_outside_window_does_not_rank(admin_client, db_session):
    """is_mers alone is not enough: the 104-week window still applies."""
    from datetime import date
    from app.ranking import active_tournaments, week_monday

    admin_client.post("/manage/tournaments/new",
                      data=_new_tournament_form(name="Old Mers 2015", is_mers="on",
                                                start_date="2015-05-02", end_date="2015-05-03"),
                      follow_redirects=False)
    t = _fetch(db_session, "Old Mers 2015")
    assert t.is_mers is True

    ids = {x.id for x, _ in active_tournaments(db_session, week_monday(date(2026, 6, 1)), "MCR")}
    assert t.id not in ids, "out of the 104-week window, it must not rank"


def test_create_tournament_duplicate_ema_id_rejected(admin_client, db_session):
    """A taken (ema_id, rules) pair is refused with a message, not a 500."""
    from app.models import Tournament

    r = admin_client.post("/manage/tournaments/new",
                          data=_new_tournament_form(name="Clash 2026", ema_id="100"),
                          follow_redirects=False)
    assert r.status_code == 302                     # redirect, not a crash
    assert _fetch(db_session, "Clash 2026") is None  # nothing written
    holder = db_session.query(Tournament).filter_by(ema_id=100, rules="MCR").one()
    assert holder.name == "Test Open MCR 2025"       # fixture t1 keeps its number


def test_manage_list_no_none_link(admin_client):
    """Rows without an EMA number must not render /tournaments/MCR_None."""
    r = admin_client.get("/manage/tournaments/")
    assert r.status_code == 200
    assert "_None" not in r.text

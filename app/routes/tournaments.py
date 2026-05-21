import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
from app.database import get_db
from app.models import Tournament, Result, AnonymousResult, Player
from app.ranking import week_monday, active_tournaments

router = APIRouter(prefix="/tournaments")
from app.i18n import templates, PAYS_EMA


def _incomplete_ids(db, tournament_ids: list) -> set:
    """IDs of tournaments with at least one anonymous European player without a name (unidentified EMA player)."""
    if not tournament_ids:
        return set()
    rows = db.query(AnonymousResult.tournament_id).filter(
        AnonymousResult.tournament_id.in_(tournament_ids),
        AnonymousResult.nationality.in_(PAYS_EMA),
        AnonymousResult.first_name.is_(None),
        AnonymousResult.last_name.is_(None),
    ).distinct().all()
    return {row.tournament_id for row in rows}


def _tournaments_tab(db, rules: str, view: str, sort: str, asc: int, city) -> dict:
    from sqlalchemy import func
    week = week_monday(date.today())
    active_ids = {t.id: c for t, c in active_tournaments(db, week, rules)}

    q = db.query(Tournament).filter(Tournament.rules == rules, Tournament.ema_id.isnot(None))
    if view == "actifs":
        q = q.filter(Tournament.id.in_(active_ids.keys()))
    elif view == "speciaux":
        q = q.filter(Tournament.tournament_type.in_(["wmc", "wrc", "oemc", "oerc"]))

    from app.models import City
    from sqlalchemy.orm import outerjoin
    q = q.outerjoin(City, Tournament.city_id == City.id)

    col_map = {"date": Tournament.start_date, "coeff": Tournament.coefficient,
               "players": Tournament.nb_players, "name": Tournament.name,
               "city": City.name, "country": Tournament.country}
    col = col_map.get(sort, Tournament.start_date)
    q = q.order_by(col if asc else col.desc())
    if city:
        q = q.filter(City.name == city)
    tournaments_list = q.filter(Tournament.start_date != date(1900, 1, 1)).all()

    vq = db.query(
        City.name.label("city"), Tournament.country, City.latitude, City.longitude,
        func.count(Tournament.id).label("nb"),
    ).join(City, Tournament.city_id == City.id
    ).filter(
        Tournament.city_id.isnot(None), Tournament.rules == rules,
        Tournament.ema_id.isnot(None),
    )
    if view == "actifs":
        vq = vq.filter(Tournament.id.in_(active_ids.keys()))
    elif view == "speciaux":
        vq = vq.filter(Tournament.tournament_type.in_(["wmc", "wrc", "oemc", "oerc"]))
    cities = [{"city": v.city, "country": v.country, "lat": v.latitude,
               "lon": v.longitude, "nb": v.nb}
              for v in vq.group_by(City.name, Tournament.country,
                                    City.latitude, City.longitude).all()]

    map_bounds = None
    if view == "speciaux" and cities:
        lats = [v["lat"] for v in cities]
        lons = [v["lon"] for v in cities]
        map_bounds = [[min(lats), min(lons)], [max(lats), max(lons)]]

    incomplete = _incomplete_ids(db, [t.id for t in tournaments_list])

    return {
        "tournaments":  tournaments_list,
        "active_ids":   active_ids,
        "cities":       cities,
        "carte_bounds": map_bounds,
        "incomplete":   incomplete,
    }


@router.get("/")
def list_tournaments(
    request: Request,
    view: str = Query("all"),
    sort: str = Query("date"),
    asc: int = Query(0),
    city: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    mcr = _tournaments_tab(db, "MCR", view, sort, asc, city)
    rcr = _tournaments_tab(db, "RCR", view, sort, asc, city)

    return templates.TemplateResponse(request, "tournaments/list.html", {
        "mcr": mcr,
        "rcr": rcr,
        "view": view,
        "sort": sort,
        "asc": asc,
        "city_filter": city,
        "carte_bounds_mcr": mcr["carte_bounds"],
        "carte_bounds_rcr": rcr["carte_bounds"],
    })


@router.get("/calendar")
def calendar(request: Request, db: Session = Depends(get_db)):
    from collections import defaultdict

    tournaments = (
        db.query(Tournament)
        .filter(Tournament.status == "calendrier")
        .order_by(Tournament.start_date)
        .all()
    )

    by_month = defaultdict(list)
    for t in tournaments:
        by_month[(t.start_date.year, t.start_date.month)].append(t)

    from app.i18n import _LOCALES, _detect_lang
    lang = _detect_lang(request)
    months = _LOCALES.get(lang, _LOCALES.get("fr", {})).get("common", {}).get("months", [])

    tournaments_by_month = [
        {"label": f"{months[m-1]} {y}" if months else f"{m}/{y}", "tournaments": ts}
        for (y, m), ts in sorted(by_month.items())
    ]

    recent = (
        db.query(Tournament)
        .filter(Tournament.status == "calendrier", Tournament.created_at.isnot(None))
        .order_by(Tournament.created_at.desc())
        .limit(5)
        .all()
    )
    recent_ids = [t.id for t in recent]

    return templates.TemplateResponse(request, "tournaments/calendar.html", {
        "tournois_par_mois": tournaments_by_month,
        "nb_total": len(tournaments),
        "recent": recent,
        "recent_ids": recent_ids,
    })


@router.get("/{rules}_{ema_id}")
def tournament_detail_ema(rules: str, ema_id: int, request: Request, db: Session = Depends(get_db)):
    tournament = db.query(Tournament).filter(Tournament.ema_id == ema_id, Tournament.rules == rules.upper()).first()
    if not tournament:
        return templates.TemplateResponse(request, "404.html", status_code=404)
    return tournament_detail(tournament.id, request, db)


@router.get("/{tournament_id}")
def tournament_detail(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    from collections import Counter
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        return templates.TemplateResponse(request, "404.html", status_code=404)

    identified_results = (
        db.query(Result)
        .filter(Result.tournament_id == tournament_id)
        .order_by(Result.position)
        .all()
    )
    anonymous_results = (
        db.query(AnonymousResult)
        .filter(AnonymousResult.tournament_id == tournament_id)
        .order_by(AnonymousResult.position)
        .all()
    )
    players = db.query(Player).order_by(Player.last_name).all()
    players_map = {p.id: p for p in players}

    def _as_row(r, player=None):
        return {
            "position":    r.position,
            "nationality": r.nationality or "",
            "player":      player,
            "ranking":     getattr(r, "ranking", None),
            "points":      getattr(r, "points", None),
            "mahjong":     getattr(r, "mahjong", None),
            "anonyme":     player is None,
            "first_name":  getattr(r, "first_name", None) or (player.first_name if player else ""),
            "name":        getattr(r, "last_name", None)   or (player.last_name  if player else ""),
        }

    unified_results = sorted(
        [_as_row(r, players_map.get(r.player_id)) for r in identified_results]
        + [_as_row(r) for r in anonymous_results],
        key=lambda x: x["position"],
    )

    nat_list = [
        players_map[r.player_id].nationality
        for r in identified_results
        if r.player_id in players_map
    ] + [
        r.nationality for r in anonymous_results if r.nationality
    ]
    country_count = Counter(nat_list)
    country_stats = sorted(
        [{"code": k, "nb": v} for k, v in country_count.items() if k and k != "GUEST"],
        key=lambda x: -x["nb"]
    )

    from sqlalchemy import text as _text
    podium = []
    podium_positions = set()

    for r in identified_results:
        if r.position > 3:
            break
        p = players_map.get(r.player_id)
        if not p:
            continue
        medal_rank = db.execute(_text('''
            SELECT COUNT(*) FROM results r2
            JOIN tournaments t2 ON t2.id = r2.tournament_id
            WHERE r2.player_id = :pid
              AND r2.position = :pos
              AND t2.rules   = :rules
              AND t2.start_date < :ddate
        '''), {"pid": r.player_id, "pos": r.position,
               "rules": tournament.rules, "ddate": tournament.start_date}).scalar() or 0
        podium.append({
            "position":      r.position,
            "player":        p,
            "rang_medaille": medal_rank + 1,
            "anonyme":       False,
        })
        podium_positions.add(r.position)

    for r in anonymous_results:
        if r.position > 3:
            continue
        if r.position in podium_positions:
            continue
        podium.append({
            "position":      r.position,
            "player":        None,
            "rang_medaille": None,
            "anonyme":       True,
            "nationality":   r.nationality or "",
            "first_name":    r.first_name or "",
            "name":          r.last_name or "",
        })
        podium_positions.add(r.position)

    podium.sort(key=lambda x: x["position"])

    num_results = len(identified_results) + len(anonymous_results)
    num_anonymous_europeans = sum(
        1 for r in anonymous_results
        if r.nationality and r.nationality.upper() in PAYS_EMA
        and not (r.first_name or r.last_name)
    )
    incomplete_results = num_anonymous_europeans > 0

    from app.models import ChampionshipTournament, Championship, ChampionshipSeries
    circuit_link = db.query(ChampionshipTournament).filter_by(tournament_id=tournament_id).first()
    circuit_tournaments = []
    circuit_series = None
    circuit_edition = None
    if circuit_link:
        circuit_edition = db.query(Championship).filter_by(id=circuit_link.championship_id).first()
        circuit_series = db.query(ChampionshipSeries).filter_by(id=circuit_edition.series_id).first()
        circuit_tournaments = [
            l.tournament for l in circuit_edition.tournament_links
            if l.tournament.city_id
        ]

    return templates.TemplateResponse(request, "tournaments/detail.html", {
        "tournoi":               tournament,
        "results":               unified_results,
        "players":               players,
        "pays_stats":            country_stats,
        "nb_pays":               len(country_stats),
        "podium":                podium,
        "resultats_incomplets":  incomplete_results,
        "nb_resultats":          num_results,
        "nb_anon_europeens":     num_anonymous_europeans,
        "is_mondial":            tournament.tournament_type in ('wmc', 'wrc'),
        "circuit_tournois":      circuit_tournaments,
        "circuit_serie":         circuit_series,
        "circuit_edition":       circuit_edition,
    })

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


def _incomplets_ids(db, tournoi_ids: list) -> set:
    """IDs of tournaments with at least one anonymous European player without a name (unidentified EMA player)."""
    if not tournoi_ids:
        return set()
    rows = db.query(AnonymousResult.tournament_id).filter(
        AnonymousResult.tournament_id.in_(tournoi_ids),
        AnonymousResult.nationality.in_(PAYS_EMA),
        AnonymousResult.first_name.is_(None),
        AnonymousResult.last_name.is_(None),
    ).distinct().all()
    return {row.tournament_id for row in rows}


def _tournois_tab(db, rules: str, view: str, sort: str, asc: int, city) -> dict:
    from sqlalchemy import func
    week = week_monday(date.today())
    active_ids = {t.id: c for t, c in active_tournaments(db, week, rules)}

    q = db.query(Tournament).filter(Tournament.rules == rules, Tournament.ema_id.isnot(None))
    if view == "actifs":
        q = q.filter(Tournament.id.in_(active_ids.keys()))
    elif view == "speciaux":
        q = q.filter(Tournament.tournament_type.in_(["wmc", "wrc", "oemc", "oerc"]))

    col_map = {"date": Tournament.start_date, "coeff": Tournament.coefficient,
               "players": Tournament.nb_players, "name": Tournament.name,
               "city": Tournament.city, "country": Tournament.country}
    col = col_map.get(sort, Tournament.start_date)
    q = q.order_by(col if asc else col.desc())
    if city:
        q = q.filter(Tournament.city == city)
    tournois_list = q.filter(Tournament.start_date != date(1900, 1, 1)).all()

    from app.models import City
    vq = db.query(
        Tournament.city, Tournament.country, City.latitude, City.longitude,
        func.count(Tournament.id).label("nb"),
    ).join(City, Tournament.city_id == City.id
    ).filter(
        Tournament.city != "", Tournament.rules == rules,
        Tournament.ema_id.isnot(None),
    )
    if view == "actifs":
        vq = vq.filter(Tournament.id.in_(active_ids.keys()))
    elif view == "speciaux":
        vq = vq.filter(Tournament.tournament_type.in_(["wmc", "wrc", "oemc", "oerc"]))
    cities = [{"city": v.city, "country": v.country, "lat": v.latitude,
               "lon": v.longitude, "nb": v.nb}
              for v in vq.group_by(Tournament.city, Tournament.country,
                                    City.latitude, City.longitude).all()]

    # Map bounds: fitBounds on all if view=speciaux, otherwise Europe by default
    carte_bounds = None
    if view == "speciaux" and cities:
        lats = [v["lat"] for v in cities]
        lons = [v["lon"] for v in cities]
        carte_bounds = [[min(lats), min(lons)], [max(lats), max(lons)]]

    incomplete = _incomplets_ids(db, [t.id for t in tournois_list])

    return {
        "tournaments":     tournois_list,
        "active_ids":   active_ids,
        "cities":       cities,
        "carte_bounds": carte_bounds,
        "incomplete":   incomplete,
    }


@router.get("/")
def liste_tournois(
    request: Request,
    view: str = Query("all"),
    sort: str = Query("date"),
    asc: int = Query(0),
    city: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    mcr = _tournois_tab(db, "MCR", view, sort, asc, city)
    rcr = _tournois_tab(db, "RCR", view, sort, asc, city)

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
def calendrier(request: Request, db: Session = Depends(get_db)):
    from collections import defaultdict
    from datetime import date as _date
    MOIS_FR = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
               "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]

    tournois = (
        db.query(Tournament)
        .filter(Tournament.status == "calendrier")
        .order_by(Tournament.start_date)
        .all()
    )

    by_month = defaultdict(list)
    for t in tournois:
        by_month[(t.start_date.year, t.start_date.month)].append(t)

    tournois_par_mois = [
        {"label": f"{MOIS_FR[m]} {y}", "tournaments": ts}
        for (y, m), ts in sorted(by_month.items())
    ]

    return templates.TemplateResponse(request, "tournaments/calendar.html", {
        "tournois_par_mois": tournois_par_mois,
        "nb_total": len(tournois),
    })



@router.get("/{rules}_{ema_id}")
def detail_tournoi_ema(rules: str, ema_id: int, request: Request, db: Session = Depends(get_db)):
    tournoi = db.query(Tournament).filter(Tournament.ema_id == ema_id, Tournament.rules == rules.upper()).first()
    if not tournoi:
        return templates.TemplateResponse(request, "404.html", status_code=404)
    return detail_tournoi(tournoi.id, request, db)


@router.get("/{tournament_id}")
def detail_tournoi(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    from collections import Counter
    tournoi = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournoi:
        return templates.TemplateResponse(request, "404.html", status_code=404)
    resultats_identifies = (
        db.query(Result)
        .filter(Result.tournament_id == tournament_id)
        .order_by(Result.position)
        .all()
    )
    resultats_anonymes = (
        db.query(AnonymousResult)
        .filter(AnonymousResult.tournament_id == tournament_id)
        .order_by(AnonymousResult.position)
        .all()
    )
    joueurs = db.query(Player).order_by(Player.last_name).all()
    players_map = {j.id: j for j in joueurs}

    # Unified list sorted by position: each entry has the fields needed by the template
    def _as_row(r, joueur=None):
        return {
            "position":    r.position,
            "nationality": r.nationality or "",
            "player":      joueur,
            "ranking":     getattr(r, "ranking", None),
            "points":      getattr(r, "points", None),
            "mahjong":     getattr(r, "mahjong", None),
            "anonyme":     joueur is None,
            "first_name":      getattr(r, "first_name", None) or (joueur.first_name if joueur else ""),
            "name":         getattr(r, "last_name", None)    or (joueur.last_name    if joueur else ""),
        }

    resultats_unifies = sorted(
        [_as_row(r, players_map.get(r.player_id)) for r in resultats_identifies]
        + [_as_row(r) for r in resultats_anonymes],
        key=lambda x: x["position"],
    )

    # For backward compatibility with the rest of the template (podium, pays_stats, etc.)
    results = resultats_identifies

    # Stats by country (identified + anonymous with flag)
    nat_list = [
        players_map[r.player_id].nationality
        for r in resultats_identifies
        if r.player_id in players_map
    ] + [
        r.nationality for r in resultats_anonymes if r.nationality
    ]
    pays_count = Counter(nat_list)
    pays_stats = sorted(
        [{"code": k, "nb": v} for k, v in pays_count.items() if k and k != "GUEST"],
        key=lambda x: -x["nb"]
    )

    # Podium: top 3 with medal rank (how many times this player finished at this position before)
    from sqlalchemy import text as _text
    podium = []
    positions_podium = set()

    for r in resultats_identifies:
        if r.position > 3:
            break
        j = players_map.get(r.player_id)
        if not j:
            continue
        rang_med = db.execute(_text('''
            SELECT COUNT(*) FROM results r2
            JOIN tournaments t2 ON t2.id = r2.tournament_id
            WHERE r2.player_id = :jid
              AND r2.position = :pos
              AND t2.rules   = :reg
              AND t2.start_date < :ddate
        '''), {"jid": r.player_id, "pos": r.position,
               "reg": tournoi.rules, "ddate": tournoi.start_date}).scalar() or 0
        podium.append({
            "position":      r.position,
            "player":        j,
            "rang_medaille": rang_med + 1,
            "anonyme":       False,
        })
        positions_podium.add(r.position)

    for r in resultats_anonymes:
        if r.position > 3:
            continue
        if r.position in positions_podium:
            continue
        podium.append({
            "position":      r.position,
            "player":        None,
            "rang_medaille": None,
            "anonyme":       True,
            "nationality":   r.nationality or "",
            "first_name":        r.first_name or "",
            "name":           r.last_name or "",
        })
        positions_podium.add(r.position)

    podium.sort(key=lambda x: x["position"])

    nb_resultats = len(resultats_identifies) + len(resultats_anonymes)
    nb_anon_europeens = sum(
        1 for r in resultats_anonymes
        if r.nationality and r.nationality.upper() in PAYS_EMA
        and not (r.first_name or r.last_name)
    )  # PAYS_EMA defined at module level
    resultats_incomplets = nb_anon_europeens > 0

    # Championship this tournament belongs to (if any)
    from app.models import ChampionshipTournament, Championship, ChampionshipSeries
    lien_champ = db.query(ChampionshipTournament).filter_by(tournament_id=tournament_id).first()
    circuit_tournois = []
    circuit_serie = None
    circuit_edition = None
    if lien_champ:
        circuit_edition = db.query(Championship).filter_by(id=lien_champ.championship_id).first()
        circuit_serie = db.query(ChampionshipSeries).filter_by(id=circuit_edition.series_id).first()
        circuit_tournois = [
            l.tournament for l in circuit_edition.tournament_links
            if l.tournament.city_id
        ]

    return templates.TemplateResponse(request, "tournaments/detail.html", {
        "tournoi":              tournoi,
        "results":            resultats_unifies,
        "players":              joueurs,
        "pays_stats":           pays_stats,
        "nb_pays":              len(pays_stats),
        "podium":               podium,
        "resultats_incomplets":  resultats_incomplets,
        "nb_resultats":          nb_resultats,
        "nb_anon_europeens":     nb_anon_europeens,
        "is_mondial":            tournoi.tournament_type in ('wmc', 'wrc'),
        "circuit_tournois":      circuit_tournois,
        "circuit_serie":         circuit_serie,
        "circuit_edition":       circuit_edition,
    })


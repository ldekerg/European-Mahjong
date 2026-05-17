import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text, case
from datetime import date as dt, timedelta
from typing import Optional
from collections import defaultdict

from app.database import get_db
from app.models import Player, Tournament, Result, RankingHistory
from app.ranking import week_monday, active_tournaments, FREEZE_START, FREEZE_END
from app.i18n import templates, ISO_NOM_PAYS, _PAYS_ISO

router = APIRouter(prefix="/countries")

def _chart_joueurs_liste(db):
    """Two global curves MCR + RCR (total ranked players per week)."""
    rows = db.execute(text('''
        SELECT ch.week, ch.rules, COUNT(DISTINCT ch.player_id) AS nb
        FROM ranking_history ch
        JOIN players j ON j.id = ch.player_id
        WHERE j.nationality NOT IN ('', 'GUEST')
        GROUP BY ch.week, ch.rules
        ORDER BY ch.week
    ''')).fetchall()

    by_rules: dict = defaultdict(dict)
    weeks_set: set = set()
    for sem, r, nb in rows:
        by_rules[r][sem] = nb
        weeks_set.add(sem)

    labels = sorted(weeks_set)
    mcr = by_rules['MCR']
    rcr = by_rules['RCR']

    return {
        'labels': [s.isoformat() if hasattr(s, 'isoformat') else str(s) for s in labels],
        'datasets': [
            {'label': 'Tout', 'cssColor': '--chart-tout', 'width': 2.5,
             'data': [mcr.get(s, 0) + rcr.get(s, 0) for s in labels]},
            {'label': 'MCR',  'cssColor': '--chart-mcr',  'width': 2,
             'data': [mcr.get(s, 0) for s in labels]},
            {'label': 'RCR',  'cssColor': '--chart-rcr',  'width': 2,
             'data': [rcr.get(s, 0) for s in labels]},
        ],
    }


def _chart_joueurs_detail(db, code):
    """
    Returns MCR, RCR and Total (MCR+RCR) for a single country.
    Format: {labels, datasets: [{label, color, width, data}]}
    """
    rows = db.execute(text('''
        SELECT ch.week, ch.rules, COUNT(DISTINCT ch.player_id) AS nb
        FROM ranking_history ch
        JOIN players j ON j.id = ch.player_id
        WHERE j.nationality = :c
        GROUP BY ch.week, ch.rules
        ORDER BY ch.week
    '''), {'c': code}).fetchall()

    by_rules: dict = defaultdict(dict)
    weeks_set: set = set()
    for sem, r, nb in rows:
        by_rules[r][sem] = nb
        weeks_set.add(sem)

    labels = sorted(weeks_set)
    mcr = by_rules['MCR']
    rcr = by_rules['RCR']

    return {
        'labels': [s.isoformat() if hasattr(s, 'isoformat') else str(s) for s in labels],
        'datasets': [
            {'label': 'Tout', 'cssColor': '--chart-tout', 'width': 2,
             'data': [mcr.get(s, 0) + rcr.get(s, 0) for s in labels]},
            {'label': 'MCR',  'cssColor': '--chart-mcr',  'width': 2,
             'data': [mcr.get(s, 0) for s in labels]},
            {'label': 'RCR',  'cssColor': '--chart-rcr',  'width': 2,
             'data': [rcr.get(s, 0) for s in labels]},
        ],
    }


def _pays_name(code: str) -> str:
    return ISO_NOM_PAYS.get(code.upper(), code)


def _pays_tournois_name(code: str) -> str:
    """Returns the country name as it appears in the tournaments table."""
    return ISO_NOM_PAYS.get(code.upper(), code)


def _ranking_pays(db, week, regles, code):
    """Global ranking filtered to players from country code."""
    rows = (
        db.query(RankingHistory, Player)
        .join(Player, RankingHistory.player_id == Player.id)
        .filter(
            RankingHistory.week == week,
            RankingHistory.rules == regles,
            Player.nationality == code,
        )
        .order_by(RankingHistory.position)
        .all()
    )
    return [
        {
            "position":    ch.position,
            "player_id":   ch.player_id,
            "name":         j.last_name,
            "first_name":      j.first_name,
            "nationality": j.nationality,
            "score":       ch.score,
            "nb_tournaments": ch.nb_tournaments or 0,
            "nb_gold":       ch.nb_gold or 0,
            "nb_silver":   ch.nb_silver or 0,
            "nb_bronze":   ch.nb_bronze or 0,
            "delta":       None,
        }
        for ch, j in rows
    ]


def _rang_national_semaine(db, week, regles, code):
    """Returns {player_id: national_rank} for a given week."""
    rows = (
        db.query(RankingHistory.player_id)
        .join(Player, RankingHistory.player_id == Player.id)
        .filter(
            RankingHistory.week == week,
            RankingHistory.rules == regles,
            Player.nationality == code,
        )
        .order_by(RankingHistory.position)
        .all()
    )
    return {row[0]: i + 1 for i, row in enumerate(rows)}


def _semaines_nav(db):
    """Returns the list of available weeks (from MCR)."""
    return [
        row[0] for row in
        db.query(RankingHistory.week)
        .filter(RankingHistory.rules == "MCR")
        .distinct()
        .order_by(RankingHistory.week)
        .all()
    ]


def _score_equipe(top3: list) -> float:
    """Average of the 3 best scores (0 for missing players)."""
    scores = [r["score"] for r in top3[:3]]
    while len(scores) < 3:
        scores.append(0.0)
    return round(sum(scores) / 3, 2)


def _ranking_equipes(db, week, regles):
    """
    For each country: top 3 players ranked at week/regles,
    team score = average of the 3 (0 if absent).
    Returns a list sorted by team_score desc.
    """
    rows = (
        db.query(RankingHistory, Player)
        .join(Player, RankingHistory.player_id == Player.id)
        .filter(
            RankingHistory.week == week,
            RankingHistory.rules == regles,
            Player.nationality.notin_(["", "GUEST"]),
        )
        .order_by(RankingHistory.position)
        .all()
    )

    # Group by country, keep top 3
    par_pays: dict[str, list] = defaultdict(list)
    for ch, j in rows:
        if len(par_pays[j.nationality]) < 3:
            par_pays[j.nationality].append({
                "player_id":   ch.player_id,
                "name":         j.last_name,
                "first_name":      j.first_name,
                "nationality": j.nationality,
                "position":    ch.position,
                "score":       round(ch.score, 2),
            })

    equipes = []
    for code, top3 in par_pays.items():
        equipes.append({
            "code":         code,
            "name":          _pays_name(code),
            "top3":         top3,
            "score_equipe": _score_equipe(top3),
            "nb_classes":   len(top3),
        })

    equipes.sort(key=lambda x: -x["score_equipe"])
    for i, e in enumerate(equipes):
        e["rang"] = i + 1

    return equipes


@router.get("/")
def pays_liste(
    request: Request,
    week: Optional[str] = Query(None),
    tab: str = Query("list"),
    db: Session = Depends(get_db),
):
    if week:
        try:
            week_date = week_monday(dt.fromisoformat(week))
        except ValueError:
            week_date = week_monday(dt.today())
    else:
        week_date = week_monday(dt.today())

    # ── Team rankings ────────────────────────────────────────────────────
    equipes_mcr = _ranking_equipes(db, week_date, "MCR")
    equipes_rcr = _ranking_equipes(db, week_date, "RCR")

    # Week navigation
    weeks_raw = _semaines_nav(db)
    total = len(weeks_raw)
    idx = next((i for i, s in enumerate(weeks_raw) if s == week_date), total - 1)
    week_prev = weeks_raw[idx - 1].isoformat() if idx > 0 else None
    week_next = weeks_raw[idx + 1].isoformat() if idx < total - 1 else None
    par_annee: dict = defaultdict(list)
    for i, s in enumerate(weeks_raw):
        par_annee[s.year].append({"date": s, "num": i + 1})
    available_weeks = [
        {"year": yr, "weeks": list(reversed(wks))}
        for yr, wks in sorted(par_annee.items(), reverse=True)
    ]

    # ── General stats by country ─────────────────────────────────────────
    players_by_country = dict(
        db.query(Player.nationality, func.count(Player.id))
        .filter(Player.nationality.notin_(["", "GUEST"]))
        .group_by(Player.nationality)
        .all()
    )

    tournois_par_pays_nom = dict(
        db.query(Tournament.country, func.count(Tournament.id))
        .filter(Tournament.country != "")
        .group_by(Tournament.country)
        .all()
    )
    tournois_par_code: dict = defaultdict(int)
    for nom, nb in tournois_par_pays_nom.items():
        iso = _PAYS_ISO.get(nom.lower().strip())
        if iso:
            tournois_par_code[iso] += nb

    # Active players (ranked this week, MCR or RCR)
    actifs_par_pays = dict(
        db.query(Player.nationality, func.count(RankingHistory.player_id.distinct()))
        .join(RankingHistory, RankingHistory.player_id == Player.id)
        .filter(
            RankingHistory.week == week_date,
            Player.nationality.notin_(["", "GUEST"]),
        )
        .group_by(Player.nationality)
        .all()
    )

    # All known countries
    all_codes = set(players_by_country.keys()) - {"", "GUEST"}
    pays_list = sorted([
        {
            "code":          code,
            "name":           _pays_name(code),
            "nb_players":    players_by_country.get(code, 0),
            "nb_actifs":     actifs_par_pays.get(code, 0),
            "nb_tournaments":   tournois_par_code.get(code, 0),
        }
        for code in all_codes
    ], key=lambda x: (-x["nb_players"], x["name"]))

    import json
    chart_liste = _chart_joueurs_liste(db)

    # ── Global stats ─────────────────────────────────────────────────────
    stats_raw = db.execute(text('''
        SELECT
            (SELECT COUNT(*) FROM players WHERE nationality NOT IN ('', 'GUEST')) AS nb_players,
            (SELECT COUNT(DISTINCT nationality) FROM players WHERE nationality NOT IN ('', 'GUEST')) AS nb_pays,
            (SELECT COUNT(*) FROM tournaments WHERE rules='MCR') AS nb_tournois_mcr,
            (SELECT COUNT(*) FROM tournaments WHERE rules='RCR') AS nb_tournois_rcr,
            (SELECT COUNT(*) FROM ranking_history
             WHERE week=(SELECT MAX(week) FROM ranking_history WHERE rules='MCR')
               AND rules='MCR') AS classes_mcr,
            (SELECT COUNT(*) FROM ranking_history
             WHERE week=(SELECT MAX(week) FROM ranking_history WHERE rules='RCR')
               AND rules='RCR') AS classes_rcr
    ''')).fetchone()
    stats_globales = {
        "nb_players":      stats_raw[0],
        "nb_pays":         stats_raw[1],
        "nb_tournois_mcr": stats_raw[2],
        "nb_tournois_rcr": stats_raw[3],
        "classes_mcr":     stats_raw[4],
        "classes_rcr":     stats_raw[5],
    }

    return templates.TemplateResponse(request, "countries/list.html", {
        "equipes_mcr":    equipes_mcr,
        "equipes_rcr":    equipes_rcr,
        "pays_list":      pays_list,
        "tab":            tab,
        "stats":          stats_globales,
        "week":        week_date,
        "week_num":    idx + 1,
        "week_prev":   week_prev,
        "week_next":   week_next,
        "available_weeks": available_weeks,
        "today_date":    dt.today(),
        "chart_json":     json.dumps(chart_liste),
    })


@router.get("/{code}")
def pays_detail(
    request: Request,
    code: str,
    week: Optional[str] = Query(None),
    rules: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    code = code.upper()
    if not db.query(Player).filter(Player.nationality == code).first():
        return templates.TemplateResponse(request, "404.html", status_code=404)
    nom_pays = _pays_name(code)

    # Current week
    if week:
        try:
            week_date = week_monday(dt.fromisoformat(week))
        except ValueError:
            week_date = week_monday(dt.today())
    else:
        week_date = week_monday(dt.today())

    active_tab = (rules or "MCR").upper()

    # ── Ranking ──────────────────────────────────────────────────────────
    mcr = _ranking_pays(db, week_date, "MCR", code)
    rcr = _ranking_pays(db, week_date, "RCR", code)

    semaine_prec = week_date - timedelta(weeks=1)
    for lst, r in [(mcr, "MCR"), (rcr, "RCR")]:
        current_rank  = {row["player_id"]: i + 1 for i, row in enumerate(lst)}
        prev_rank = _rang_national_semaine(db, semaine_prec, r, code)
        for row in lst:
            jid = row["player_id"]
            p = prev_rank.get(jid)
            row["delta"] = (p - current_rank[jid]) if p else None

    # Week navigation
    weeks_raw = _semaines_nav(db)
    total = len(weeks_raw)
    idx = next((i for i, s in enumerate(weeks_raw) if s == week_date), total - 1)
    week_prev = weeks_raw[idx - 1].isoformat() if idx > 0 else None
    week_next = weeks_raw[idx + 1].isoformat() if idx < total - 1 else None

    par_annee: dict = defaultdict(list)
    for i, s in enumerate(weeks_raw):
        par_annee[s.year].append({"date": s, "num": i + 1})
    available_weeks = [
        {"year": yr, "weeks": list(reversed(wks))}
        for yr, wks in sorted(par_annee.items(), reverse=True)
    ]

    # Default players for the preview panel
    default_player_mcr = mcr[0]["player_id"] if mcr else None
    default_player_rcr = rcr[0]["player_id"] if rcr else None
    default_player = default_player_mcr if active_tab == "MCR" else default_player_rcr

    # ── Country tournaments ──────────────────────────────────────────────
    pays_nom = _pays_tournois_name(code)
    tous_tournois = (
        db.query(Tournament)
        .filter(Tournament.country == pays_nom)
        .filter(Tournament.status != "calendrier") # Exclude calendar placeholders
        .order_by(Tournament.start_date.desc())
        .all()
    )
    actifs_dict = {t.id: c for t, c in active_tournaments(db, week_date, "MCR")}
    actifs_dict.update({t.id: c for t, c in active_tournaments(db, week_date, "RCR")})

    from app.routes.tournaments import _incomplets_ids
    incomplete = _incomplets_ids(db, [t.id for t in tous_tournois])

    # Cities for the map
    from app.models import City
    villes_q = (
        db.query(Tournament.city, Tournament.country, City.latitude, City.longitude,
                 func.count(Tournament.id).label("nb"))
        .join(City, Tournament.city_id == City.id)
        .filter(Tournament.country == pays_nom)
        .group_by(Tournament.city, Tournament.country, City.latitude, City.longitude)
        .all()
    )
    cities = [{"city": v.city, "country": v.country, "lat": v.latitude, "lon": v.longitude, "nb": v.nb}
              for v in villes_q]
    # Detection of geographic groups (e.g. mainland + distant islands)
    # Separate cities whose distance exceeds a threshold (>15° lat or lon)
    def _bounds(pts):
        lats = [p["lat"] for p in pts]
        lons = [p["lon"] for p in pts]
        return [[min(lats), min(lons)], [max(lats), max(lons)]]

    def _groupes(pts, seuil_lat=15, seuil_lon=30):
        if not pts:
            return []
        pts_s = sorted(pts, key=lambda p: p["lat"])
        groupes, grp = [], [pts_s[0]]
        for p in pts_s[1:]:
            if p["lat"] - grp[-1]["lat"] > seuil_lat:
                groupes.append(grp); grp = [p]
            else:
                grp.append(p)
        groupes.append(grp)
        return groupes

    groupes_villes = _groupes(cities)
    # Sort groups by decreasing latitude (mainland before overseas territories/islands)
    groupes_villes.sort(key=lambda g: -max(p["lat"] for p in g))
    cartes = [{"cities": g, "bounds": _bounds(g)} for g in groupes_villes]
    carte_bounds = cartes[0]["bounds"] if cartes else None

    # ── Player list ───────────────────────────────────────────────────────
    from datetime import date as _date
    joueurs_q = db.query(Player).filter(Player.nationality == code).order_by(Player.last_name).all()
    player_ids = [j.id for j in joueurs_q]
    _tpj = {
        row.player_id: row
        for row in db.query(
            Result.player_id,
            func.sum(case((Tournament.rules == "MCR", 1), else_=0)).label("nb_mcr"),
            func.sum(case((Tournament.rules == "RCR", 1), else_=0)).label("nb_rcr"),
            func.min(Tournament.start_date).label("premier"),
        )
        .join(Tournament, Result.tournament_id == Tournament.id)
        .filter(Result.player_id.in_(player_ids),
                Tournament.start_date != _date(1900, 1, 1))
        .group_by(Result.player_id)
        .all()
    }
    joueurs_data = [
        {
            "player":   j,
            "nb_mcr":   (_tpj[j.id].nb_mcr if j.id in _tpj else 0) or 0,
            "nb_rcr":   (_tpj[j.id].nb_rcr if j.id in _tpj else 0) or 0,
            "nb_total": ((_tpj[j.id].nb_mcr if j.id in _tpj else 0) or 0)
                       + ((_tpj[j.id].nb_rcr if j.id in _tpj else 0) or 0),
            "premier":  _tpj[j.id].premier if j.id in _tpj else None,
        }
        for j in joueurs_q
    ]

    nb_classes_mcr = len(mcr)
    nb_classes_rcr = len(rcr)
    meilleur_actuel_mcr = mcr[0]["position"] if mcr else None
    meilleur_actuel_rcr = rcr[0]["position"] if rcr else None

    import json
    chart_detail = _chart_joueurs_detail(db, code)

    from app.models import ChampionshipSeries
    series_pays = db.query(ChampionshipSeries).filter_by(country=code).order_by(ChampionshipSeries.name).all()

    return templates.TemplateResponse(request, "countries/detail.html", {
        "code":             code,
        "nom_pays":         nom_pays,
        # Stats
        "nb_players":       len(joueurs_data),
        "nb_tournois_org":  len(tous_tournois),
        "nb_classes_mcr":       nb_classes_mcr,
        "nb_classes_rcr":       nb_classes_rcr,
        "meilleur_actuel_mcr":  meilleur_actuel_mcr,
        "meilleur_actuel_rcr":  meilleur_actuel_rcr,
        # Ranking
        "mcr":              mcr,
        "rcr":              rcr,
        "week":          week_date,
        "week_num":      idx + 1,
        "week_prev":     week_prev,
        "week_next":     week_next,
        "available_weeks":   available_weeks,
        "today_date":      dt.today(),
        "active_tab":       active_tab,
        "default_player":         default_player,
        "default_player_mcr":     default_player_mcr,
        "default_player_rcr":     default_player_rcr,
        # Tournaments
        "tournaments":         tous_tournois,
        "active_ids":       actifs_dict,
        "incomplete":       incomplete,
        "cities":           cities,
        "cartes":           cartes,
        "carte_bounds":     carte_bounds,
        "ville_filtre":     None,
        # Players
        "players":          joueurs_data,
        # Chart
        "chart_json":       json.dumps(chart_detail),
        # National circuits
        "series_pays":      series_pays,
    })

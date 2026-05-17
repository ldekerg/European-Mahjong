import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from typing import Optional

from app.database import get_db
from app.models import RankingHistory, Player, Result, AnonymousResult, Tournament
from app.i18n import templates, PAYS_EMA

router = APIRouter(prefix="/hof")


def _hof_data(db: Session, regles: str, active_ids=None):
    """Computes Hall of Fame stats for a discipline."""
    # Aggregations on classement_historique
    stats = db.query(
        RankingHistory.player_id,
        func.count(RankingHistory.id).label("nb_semaines"),
        func.sum(case((RankingHistory.position == 1,  1), else_=0)).label("nb_gold"),
        func.sum(case((RankingHistory.position <= 2,  1), else_=0)).label("nb_silver"),
        func.sum(case((RankingHistory.position <= 3,  1), else_=0)).label("nb_bronze"),
        func.sum(case((RankingHistory.position <= 10, 1), else_=0)).label("nb_top10"),
        func.sum(case((RankingHistory.position <= 20, 1), else_=0)).label("nb_top20"),
        func.sum(case((RankingHistory.position <= 50, 1), else_=0)).label("nb_top50"),
        func.min(case((RankingHistory.position == 1, RankingHistory.week), else_=None)).label("premiere_1"),
        func.min(case((RankingHistory.position <= 10, RankingHistory.week), else_=None)).label("premiere_top10"),
        func.min(RankingHistory.position).label("meilleur_rang"),
        func.max(RankingHistory.score).label("score_max"),
    ).filter(
        RankingHistory.rules == regles,
    ).group_by(RankingHistory.player_id).subquery()

    qr = db.query(stats, Player).join(Player, stats.c.player_id == Player.id)
    if active_ids is not None:
        qr = qr.filter(stats.c.player_id.in_(active_ids))
    rows = qr.all()

    result = []
    for row in rows:
        j = row.Player
        result.append({
            "player":        j,
            "nb_semaines":   row.nb_semaines or 0,
            "nb_gold":         row.nb_gold or 0,
            "nb_silver":     row.nb_silver or 0,
            "nb_bronze":     row.nb_bronze or 0,
            "nb_top10":      row.nb_top10 or 0,
            "nb_top20":      row.nb_top20 or 0,
            "nb_top50":      row.nb_top50 or 0,
            "premiere_1":    row.premiere_1,
            "premiere_top10":row.premiere_top10,
            "meilleur_rang": row.meilleur_rang,
            "score_max":     round(row.score_max, 2) if row.score_max else None,
        })
    return result


def _championnats(db: Session, regles: str):
    """OEMC/WMC/OERC/WRC results."""
    types = ["wmc", "oemc"] if regles == "MCR" else ["wrc", "oerc"]
    rows = db.query(Result, Tournament, Player).join(
        Tournament, Result.tournament_id == Tournament.id
    ).join(
        Player, Result.player_id == Player.id
    ).filter(
        Tournament.tournament_type.in_(types),
        Tournament.start_date.isnot(None),
    ).order_by(Tournament.start_date.desc(), Result.position).all()
    return rows


def _meilleur_europeen(db: Session, type_tournoi: str):
    """Best European player from the last tournament of this type."""
    from sqlalchemy import func
    # Date of the last tournament of this type WITH results
    dernier = db.query(func.max(Tournament.start_date)).join(
        Result, Result.tournament_id == Tournament.id
    ).filter(
        Tournament.tournament_type == type_tournoi
    ).scalar()
    if not dernier:
        return None

    tournoi = db.query(Tournament).filter(
        Tournament.tournament_type == type_tournoi,
        Tournament.start_date == dernier,
    ).first()

    result = db.query(Result, Player).join(
        Player, Result.player_id == Player.id
    ).filter(
        Result.tournament_id == tournoi.id,
        Player.status == "europeen",
    ).order_by(Result.position).first()

    if not result:
        return None

    r, j = result
    return {
        "tournament": tournoi,
        "player":     j,
        "position": r.position,
        "est_champion": r.position == 1,
        "est_vice":     r.position == 2,
        "est_bronze":   r.position == 3,
    }


def _palmares_championnats(db: Session, regles: str) -> list:
    """For each major tournament with results, returns the top 3 (identified + anonymous merged)."""
    types = ["wmc", "oemc"] if regles == "MCR" else ["wrc", "oerc"]
    tournois = db.query(Tournament).filter(
        Tournament.tournament_type.in_(types),
        Tournament.start_date.isnot(None),
        Tournament.start_date != __import__('datetime').date(1900, 1, 1),
    ).order_by(Tournament.start_date.desc()).all()

    result = []
    for t in tournois:
        identifies = db.query(Result, Player).join(
            Player, Result.player_id == Player.id
        ).filter(
            Result.tournament_id == t.id,
            Player.status == "europeen",
        ).order_by(Result.position).all()

        anonymes = db.query(AnonymousResult).filter(
            AnonymousResult.tournament_id == t.id,
            AnonymousResult.nationality.in_(PAYS_EMA),
        ).order_by(AnonymousResult.position).all()

        # Merge and sort by position, keep top 3
        all_entries = [
            {"player": j, "position": r.position, "nationality": r.nationality, "anonyme": False}
            for r, j in identifies
        ] + [
            {"player": None, "position": a.position, "nationality": a.nationality,
             "first_name": a.first_name, "name": a.last_name, "anonyme": True}
            for a in anonymes
        ]
        all_entries.sort(key=lambda x: x["position"])

        if not all_entries:
            continue  # Tournament with no results

        result.append({
            "tournoi": t,
            "top3":    all_entries[:3],
        })
    return result


def _compute_hof(db: Session, regles: str, periode: str) -> dict:
    """Computes all HoF data for a discipline and a period."""
    from app.ranking import week_monday, FREEZE_START, FREEZE_END
    from datetime import date as dt
    from collections import defaultdict

    current_week = week_monday(dt.today())
    active_ids = None
    streak_map = {}

    if periode == "encours":
        all_weeks = db.query(
            RankingHistory.player_id,
            RankingHistory.week,
        ).filter(
            RankingHistory.rules == regles,
        ).order_by(
            RankingHistory.player_id,
            RankingHistory.week.desc(),
        ).all()

        by_player = defaultdict(list)
        for jid, sem in all_weeks:
            by_player[jid].append(sem)

        freeze_gap = (FREEZE_END - FREEZE_START).days // 7 + 1

        for jid, weeks in by_player.items():
            if weeks[0] != current_week:
                continue
            streak = 1
            for k in range(1, len(weeks)):
                diff = (weeks[k-1] - weeks[k]).days // 7
                if diff == 1:
                    streak += 1
                elif diff == freeze_gap:
                    streak += 1
                else:
                    break
            streak_map[jid] = streak

        active_ids = set(streak_map.keys())

    data = _hof_data(db, regles, active_ids)
    championnats = _championnats(db, regles)

    medals_q = db.query(
        Result.player_id,
        func.sum(case((Result.position == 1, 1), else_=0)).label("or_t"),
        func.sum(case((Result.position == 2, 1), else_=0)).label("argent_t"),
        func.sum(case((Result.position == 3, 1), else_=0)).label("bronze_t"),
        func.count(Result.id).label("total_t"),
    ).join(Tournament, Result.tournament_id == Tournament.id
    ).filter(Tournament.rules == regles
    ).group_by(Result.player_id).subquery()

    medals_rows = db.query(medals_q, Player).join(Player, medals_q.c.player_id == Player.id).all()
    medals_data = [{
        "player":   row.Player,
        "or_t":     row.or_t or 0,
        "argent_t": row.argent_t or 0,
        "bronze_t": row.bronze_t or 0,
        "total_t":  row.total_t or 0,
    } for row in medals_rows if (row.or_t or 0) + (row.argent_t or 0) + (row.bronze_t or 0) > 0]
    medals_data.sort(key=lambda x: (-x["or_t"], -x["argent_t"], -x["bronze_t"]))

    if periode == "encours" and streak_map:
        def streak_for(semaines_desc, threshold):
            s = 0
            for _, p in semaines_desc:
                if p <= threshold: s += 1
                else: break
            return s

        for d in data:
            jid = d["player"].id
            total_streak = streak_map.get(jid, 0)
            all_series = db.query(
                RankingHistory.week,
                RankingHistory.position,
            ).filter(
                RankingHistory.player_id == jid,
                RankingHistory.rules == regles,
            ).order_by(RankingHistory.week.desc()).limit(total_streak).all()

            d["nb_semaines"] = total_streak
            d["nb_gold"]    = streak_for(all_series, 1)
            d["nb_silver"] = streak_for(all_series, 2)
            d["nb_bronze"] = streak_for(all_series, 3)
            d["nb_top10"]  = streak_for(all_series, 10)
            d["nb_top20"]  = streak_for(all_series, 20)
            d["nb_top50"]  = streak_for(all_series, 50)

    if periode == "encours":
        data.sort(key=lambda x: (-x["nb_gold"], -x["nb_bronze"], -x["nb_top10"], -x["nb_top20"], -x["nb_top50"]))
        data = [d for d in data if d["nb_top50"] > 0]
    else:
        data.sort(key=lambda x: (-x["nb_gold"], -x["nb_silver"], -x["nb_bronze"]))
        data = [d for d in data if d["nb_semaines"] > 0]

    return {"data": data, "medals_data": medals_data, "championnats": championnats}


def _records(db: Session, regles: str) -> dict:
    """Top 20 mahjong scores and (MCR only) top 20 tournament points."""
    base = db.query(
        Result, Tournament, Player,
    ).join(Tournament, Result.tournament_id == Tournament.id
    ).join(Player, Result.player_id == Player.id
    ).filter(
        Tournament.rules == regles,
        Tournament.tournament_type.notin_(["wmc", "wrc"]),
    )

    def _row(r, t, j):
        return {
            "player":        j,
            "points":        r.points,
            "mahjong":       r.mahjong,
            "tournoi_nom":   t.name,
            "tournoi_regles": t.rules,
            "tournoi_ema_id": t.ema_id,
            "nb_players":    t.nb_players,
            "date":          t.start_date,
        }

    from datetime import timedelta

    seuil_mah = 10000 if regles == "RCR" else 100

    def _top_mahjong(q, limit=20):
        return [_row(r, t, j) for r, t, j in
                q.filter(Result.mahjong > seuil_mah)
                 .order_by(Result.mahjong.desc())
                 .limit(limit).all()]

    def _top_points(q, limit=20):
        return [_row(r, t, j) for r, t, j in
                q.filter(Result.points.between(1, 99))
                 .order_by(Result.points.desc())
                 .limit(limit).all()]

    # Filter 2-day tournaments (end_date - start_date <= 1 day)
    base_2j = base.filter(
        (func.julianday(Tournament.end_date) - func.julianday(Tournament.start_date)) <= 1
    )

    top_mahjong      = _top_mahjong(base)
    top_mahjong_2j   = _top_mahjong(base_2j)
    top_points       = _top_points(base)    if regles == "MCR" else []
    top_points_2j    = _top_points(base_2j) if regles == "MCR" else []

    return {
        "top_mahjong":    top_mahjong,
        "top_mahjong_2j": top_mahjong_2j,
        "top_points":     top_points,
        "top_points_2j":  top_points_2j,
    }


@router.get("/")
def hallfame(
    request: Request,
    view: str = Query("medals"),     # medals | weeks | championships | records
    periode: str = Query("alltime"), # alltime | encours
    db: Session = Depends(get_db),
):
    mcr = _compute_hof(db, "MCR", periode)
    rcr = _compute_hof(db, "RCR", periode)

    champions = {
        "oemc": _meilleur_europeen(db, "oemc"),
        "wmc":  _meilleur_europeen(db, "wmc"),
        "oerc": _meilleur_europeen(db, "oerc"),
        "wrc":  _meilleur_europeen(db, "wrc"),
    }
    palmares_mcr = _palmares_championnats(db, "MCR")
    palmares_rcr = _palmares_championnats(db, "RCR")

    from app.routes.tournaments import _incomplets_ids
    tous_ids = [item["tournoi"].id for item in palmares_mcr + palmares_rcr]
    incomplete = _incomplets_ids(db, tous_ids)

    records_mcr = _records(db, "MCR")
    records_rcr = _records(db, "RCR")

    return templates.TemplateResponse(request, "hof.html", {
        "mcr":          mcr,
        "rcr":          rcr,
        "view":         view,
        "periode":      periode,
        "champions":    champions,
        "palmares_mcr": palmares_mcr,
        "palmares_rcr": palmares_rcr,
        "incomplete":    incomplete,
        "records_mcr":   records_mcr,
        "records_rcr":   records_rcr,
    })

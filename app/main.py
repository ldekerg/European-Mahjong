from fastapi import FastAPI, Request, Query, Depends
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from typing import Optional
from sqlalchemy.orm import Session

from app.database import engine, SessionLocal, get_db
import app.models as models
from app.routes import players, tournaments, hof, championships
from app.routes import countries
from app.routes import formulas
from app.i18n import templates
from app.models import RankingHistory, Player
from app.ranking import week_monday, ranking

if os.getenv("DATABASE_URL"):
    models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="EMA Ranking")
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

app.include_router(players.router)
app.include_router(tournaments.router)
app.include_router(hof.router)
app.include_router(countries.router)
app.include_router(championships.router)
app.include_router(formulas.router)


def get_rank_delta(db: Session, week: date, regles: str) -> dict:
    """Returns {player_id: previous_week_position} to compute the rank delta."""
    from datetime import timedelta
    prev_week = week - timedelta(weeks=1)
    rows = db.query(RankingHistory.player_id, RankingHistory.position).filter(
        RankingHistory.week == prev_week,
        RankingHistory.rules == regles,
    ).all()
    return {r[0]: r[1] for r in rows}


def get_week_ranking(db: Session, week: date, regles: str) -> list:
    """Retrieves the ranking from history or computes it on the fly."""
    rows = (
        db.query(RankingHistory, Player)
        .join(Player, RankingHistory.player_id == Player.id)
        .filter(
            RankingHistory.week == week,
            RankingHistory.rules == regles,
        )
        .order_by(RankingHistory.position)
        .all()
    )
    if rows:
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
                "delta":       None,  # filled in later
            }
            for ch, j in rows
        ]
    # On-the-fly computation if week not yet stored
    raw = ranking(db, week, regles)
    players_map = {j.id: j for j in db.query(Player).all()}
    return [
        {
            "position":    r["position"],
            "player_id":   r["player_id"],
            "name":         players_map[r["player_id"]].last_name,
            "first_name":      players_map[r["player_id"]].first_name,
            "nationality": players_map[r["player_id"]].nationality,
            "score":       r["score"],
            "nb_tournaments": r["nb_tournaments"],
            "nb_gold":       r["nb_gold"],
            "nb_silver":   r["nb_silver"],
            "nb_bronze":   r["nb_bronze"],
        }
        for r in raw
        if r["player_id"] in players_map
    ]


@app.get("/home")
def home(request: Request, db: Session = Depends(get_db)):
    from app.models import Tournament, Result, AnonymousResult
    from app.routes.hof import _meilleur_europeen
    from sqlalchemy import func, exists
    try:
        today = date.today()
        week_date = week_monday(today)

        # Global stats
        nb_players   = db.query(Player).filter(Player.status == "europeen").count()
        nb_tournaments  = db.query(Tournament).count()
        nb_classes_mcr = db.query(RankingHistory.player_id).filter(
            RankingHistory.week == week_date,
            RankingHistory.rules  == "MCR",
        ).distinct().count()
        nb_classes_rcr = db.query(RankingHistory.player_id).filter(
            RankingHistory.week == week_date,
            RankingHistory.rules  == "RCR",
        ).distinct().count()

        # Top 5 MCR and RCR
        def top5(rules):
            rows = (
                db.query(RankingHistory, Player)
                .join(Player, RankingHistory.player_id == Player.id)
                .filter(
                    RankingHistory.week == week_date,
                    RankingHistory.rules  == rules,
                )
                .order_by(RankingHistory.position)
                .limit(5).all()
            )
            return [{"position": ch.position, "player": j, "score": ch.score} for ch, j in rows]

        # Last played tournaments: with results AND past date
        has_resultats = exists().where(Result.tournament_id == Tournament.id)
        from datetime import date as _date
        recent = (
            db.query(Tournament)
            .filter(
                Tournament.start_date <= today,
                Tournament.start_date != _date(1900, 1, 1),
                has_resultats,
            )
            .order_by(Tournament.start_date.desc())
            .limit(8).all()
        )

        # Upcoming tournaments: future date AND no results
        has_no_resultats = ~exists().where(Result.tournament_id == Tournament.id)
        upcoming = (
            db.query(Tournament)
            .filter(
                Tournament.start_date > today,
                has_no_resultats,
                Tournament.tournament_type == "normal",
            )
            .order_by(Tournament.start_date)
            .limit(6).all()
        )

        # Calendar (for the compact home partial)
        from collections import defaultdict
        MONTHS_FR = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
                   "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
        cal_tournaments = (
            db.query(Tournament)
            .filter(Tournament.status == "calendrier")
            .order_by(Tournament.start_date)
            .all()
        )
        cal_by_month = defaultdict(list)
        for t in cal_tournaments:
            cal_by_month[(t.start_date.year, t.start_date.month)].append(t)
        calendar_by_month = [
            {"label": f"{MONTHS_FR[m]} {y}", "tournaments": ts}
            for (y, m), ts in sorted(cal_by_month.items())
        ]

        # Reigning champions
        champions = {
            "oemc": _meilleur_europeen(db, "oemc"),
            "wmc":  _meilleur_europeen(db, "wmc"),
            "oerc": _meilleur_europeen(db, "oerc"),
            "wrc":  _meilleur_europeen(db, "wrc"),
        }

    finally:
        pass

    return templates.TemplateResponse(request, "home.html", {
        "nb_players":    nb_players,
        "nb_tournaments":   nb_tournaments,
        "nb_classes_mcr": nb_classes_mcr,
        "nb_classes_rcr": nb_classes_rcr,
        "top_mcr":       top5("MCR"),
        "top_rcr":       top5("RCR"),
        "recent":           recent,
        "upcoming":          upcoming,
        "champions":          champions,
        "calendar_by_month": calendar_by_month,
    })


@app.get("/ranking")
def accueil(
    request: Request,
    week: Optional[str] = Query(None),
    player_filter: Optional[str] = Query(None),
    rules: Optional[str] = Query(None),  # active tab to display (MCR or RCR)
    db: Session = Depends(get_db),
):
    try:
        if week:
            try:
                week_date = week_monday(date.fromisoformat(week))
            except ValueError:
                week_date = week_monday(date.today())
        else:
            week_date = week_monday(date.today())

        mcr = get_week_ranking(db, week_date, "MCR")
        rcr = get_week_ranking(db, week_date, "RCR")

        # Compute rank delta
        for lst, rules_key in [(mcr, "MCR"), (rcr, "RCR")]:
            prev = get_rank_delta(db, week_date, rules_key)
            for r in lst:
                p = prev.get(r["player_id"])
                r["delta"] = (p - r["position"]) if p else None  # positive = moved up

        # All weeks for prev/next navigation
        weeks_raw = [
            row[0] for row in
            db.query(RankingHistory.week)
            .filter(RankingHistory.rules == "MCR")
            .distinct()
            .order_by(RankingHistory.week)
            .all()
        ]
        total = len(weeks_raw)
        current_idx = next((i for i, s in enumerate(weeks_raw) if s == week_date), total - 1)
        week_prev = weeks_raw[current_idx - 1].isoformat() if current_idx > 0 else None
        week_next = weeks_raw[current_idx + 1].isoformat() if current_idx < total - 1 else None

        # Dropdown: all weeks grouped by year
        from collections import defaultdict
        by_year: dict = defaultdict(list)
        for i, s in enumerate(weeks_raw):
            by_year[s.year].append({"date": s, "num": i + 1})
        available_weeks = [
            {"year": yr, "weeks": list(reversed(wks))}
            for yr, wks in sorted(by_year.items(), reverse=True)
        ]
    finally:
        pass

    current_week = week_monday(date.today())
    today_date = date.today()

    return templates.TemplateResponse(request, "ranking.html", {
        "mcr": mcr,
        "rcr": rcr,
        "current_week": current_week,
        "today_date": today_date,
        "week": week_date,
        "week_num": current_idx + 1,
        "week_prev": week_prev,
        "week_next": week_next,
        "available_weeks": available_weeks,
        "selected_player": player_filter,
        "active_tab": (rules or "MCR").upper(),
        "default_player": mcr[0]["player_id"] if mcr else None,
        "default_player_mcr": mcr[0]["player_id"] if mcr else None,
        "default_player_rcr": rcr[0]["player_id"] if rcr else None,
    })


@app.get("/")
def root():
    return RedirectResponse(url="/home")

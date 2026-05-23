import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from datetime import date

from app.database import get_db
from app.models import Player, Tournament, Result, RankingHistory, NationalityChange, Referee, TournamentReferee
from app.ranking import week_monday, active_tournaments, _player_results, contribution, FREEZE_START, FREEZE_END

router = APIRouter(prefix="/players")
from app.i18n import templates


@router.get("/")
def list_players(
    request: Request,
    sort: str = "name",        # id | name | first_name | nationality | nb_mcr | nb_rcr | nb_total
    asc: int = 1,              # 1 = ascending, 0 = descending
    rules: str = "all",        # all | MCR | RCR | referee_mcr | referee_rcr
    q: str = "",               # text search
    db: Session = Depends(get_db),
):
    from app.models import Result, Tournament as T
    from sqlalchemy import func

    # Subqueries to count tournaments per player/rules + date of first tournament
    mcr_count = (
        db.query(Result.player_id, func.count(Result.id).label("nb"))
        .join(T).filter(T.rules == "MCR", T.ema_id.isnot(None)).group_by(Result.player_id).subquery()
    )
    rcr_count = (
        db.query(Result.player_id, func.count(Result.id).label("nb"))
        .join(T).filter(T.rules == "RCR", T.ema_id.isnot(None)).group_by(Result.player_id).subquery()
    )
    first_tournament = (
        db.query(Result.player_id, func.min(T.start_date).label("first"))
        .join(T).filter(T.start_date != date(1900, 1, 1), T.ema_id.isnot(None))
        .group_by(Result.player_id).subquery()
    )

    qr = db.query(
        Player,
        func.coalesce(mcr_count.c.nb, 0).label("nb_mcr"),
        func.coalesce(rcr_count.c.nb, 0).label("nb_rcr"),
        first_tournament.c.first.label("first"),
    ).outerjoin(mcr_count, Player.id == mcr_count.c.player_id
    ).outerjoin(rcr_count, Player.id == rcr_count.c.player_id
    ).outerjoin(first_tournament, Player.id == first_tournament.c.player_id)

    if rules == "MCR":
        qr = qr.filter(mcr_count.c.nb > 0)
    elif rules == "RCR":
        qr = qr.filter(rcr_count.c.nb > 0)

    if q:
        like = f"%{q.upper()}%"
        qr = qr.filter((Player.last_name.ilike(like)) | (Player.first_name.ilike(like)) | (Player.id.ilike(like)))

    col_map = {
        "id":          Player.id,
        "name":         Player.last_name,
        "first_name":      Player.first_name,
        "nationality": Player.nationality,
        "nb_mcr":      func.coalesce(mcr_count.c.nb, 0),
        "nb_rcr":      func.coalesce(rcr_count.c.nb, 0),
        "nb_total":    func.coalesce(mcr_count.c.nb, 0) + func.coalesce(rcr_count.c.nb, 0),
        "first":       first_tournament.c.first,
    }
    col = col_map.get(sort, Player.last_name)
    qr = qr.order_by(col if asc else col.desc())

    rows = qr.all()
    players_list = [{"player": r[0], "nb_mcr": r[1], "nb_rcr": r[2], "nb_total": r[1]+r[2], "first": r[3]} for r in rows]

    from app.main import get_referee_ids
    referee_ids = get_referee_ids(db)

    if rules == "referee_mcr":
        players_list = [p for p in players_list if p["player"].id in referee_ids and "MCR" in referee_ids[p["player"].id]]
    elif rules == "referee_rcr":
        players_list = [p for p in players_list if p["player"].id in referee_ids and "RCR" in referee_ids[p["player"].id]]

    return templates.TemplateResponse(request, "players/list.html", {
        "players":      players_list,
        "sort":         sort,
        "asc":          asc,
        "rules":        rules,
        "q":            q,
        "total":        len(players_list),
        "current_week": week_monday(date.today()),
        "referee_ids":  referee_ids,
    })



@router.get("/{player_id}")
def player_detail(player_id: str, request: Request, db: Session = Depends(get_db)):
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        return templates.TemplateResponse(request, "404.html", status_code=404)

    week = week_monday(date.today())

    def build_tab(rules: str):
        # Current ranking
        ranking = db.query(RankingHistory).filter(
            RankingHistory.player_id == player_id,
            RankingHistory.rules == rules,
            RankingHistory.week == week,
        ).first()

        # Ranking history (all weeks)
        history = (
            db.query(RankingHistory)
            .filter(
                RankingHistory.player_id == player_id,
                RankingHistory.rules == rules,
            )
            .order_by(RankingHistory.week)
            .all()
        )

        # Best ranking and max score
        best_rank = min((h.position for h in history), default=None)
        max_score = max((h.score for h in history), default=None)
        max_score = round(max_score, 2) if max_score else None
        # Dates of maxima for the chart
        date_best_rank = next((h.week.isoformat() for h in history if h.position == best_rank), None)
        date_max_score = next((h.week.isoformat() for h in history if max_score and round(h.score,2) == max_score), None)

        # Played tournaments with details
        active = {t.id: (t, c) for t, c in active_tournaments(db, week, rules)}
        results = (
            db.query(Result)
            .join(Tournament)
            .filter(Result.player_id == player_id, Tournament.rules == rules,
                    Tournament.ema_id.isnot(None))
            .order_by(Tournament.start_date.desc())
            .all()
        )

        tournaments_data = []
        for r in results:
            t = r.tournament
            c = contribution(t.start_date, week) if t.start_date.year != 1900 else 0.0
            tournaments_data.append({
                "date": t.start_date,
                "duration": max(1, (t.end_date - t.start_date).days + 1) if t.end_date and t.start_date.year != 1900 else 1,
                "name": t.name,
                "city": t.city,
                "country": t.country,
                "ema_id": t.ema_id,
                "contrib": c,
                "coeff": t.coefficient,
                "points": r.points,
                "mahjong": r.mahjong,
                "position": r.position,
                "nb_players": t.nb_players,
                "ranking": r.ranking,
                "type": t.tournament_type,
                "active": t.id in active or (
                    t.tournament_type in ("wmc", "wrc") and
                    t.start_date.year != 1900 and
                    (week - t.start_date).days <= 730
                ),
                "nat_at_tournament": r.nationality or player.nationality,
            })

        history_chart = [
            {"week": h.week.isoformat(), "position": h.position, "score": round(h.score, 2)}
            for h in history
        ]

        # Best points/mahjong score — exclude unusual formats
        best_points = max(
            (td for td in tournaments_data if td["points"] > 0 and td["points"] < 100),
            key=lambda x: x["points"], default=None,
        )
        threshold = 10000 if rules == "RCR" else 100
        best_mahjong = max(
            (td for td in tournaments_data if td["mahjong"] and td["mahjong"] > threshold),
            key=lambda x: x["mahjong"], default=None,
        )

        # Current + best national rank
        compatriot_ids = [
            r[0] for r in db.query(Player.id)
            .filter(Player.nationality == player.nationality).all()
        ]
        national_rank = None
        if ranking:
            nb_above = db.query(RankingHistory.player_id).filter(
                RankingHistory.rules == rules,
                RankingHistory.week == week,
                RankingHistory.player_id.in_(compatriot_ids),
                RankingHistory.position < ranking.position,
            ).count()
            national_rank = nb_above + 1

        # Best national rank — single query: for each week the player was ranked,
        # count compatriots ranked above, then pick the minimum
        best_national_rank = None
        date_best_national_rank = None
        if history and compatriot_ids:
            from sqlalchemy import text as _text
            ids_placeholder = ",".join(f"'{i}'" for i in compatriot_ids)
            rows = db.execute(_text(f"""
                SELECT ph.week, ph.position,
                       (SELECT COUNT(*) FROM ranking_history ch
                        WHERE ch.rules = :rules AND ch.week = ph.week
                          AND ch.player_id IN ({ids_placeholder})
                          AND ch.position < ph.position) AS nb_above
                FROM ranking_history ph
                WHERE ph.player_id = :pid AND ph.rules = :rules
                ORDER BY nb_above ASC
                LIMIT 1
            """), {"rules": rules, "pid": player_id}).fetchone()
            if rows:
                best_national_rank = rows[2] + 1
                date_best_national_rank = rows[0].isoformat() if hasattr(rows[0], 'isoformat') else str(rows[0])

        return {
            "ranking": ranking,
            "best_rank": best_rank,
            "max_score": max_score,
            "date_best_rank": date_best_rank,
            "date_max_score": date_max_score,
            "history": history,
            "history_chart": history_chart,
            "tournaments": tournaments_data,
            "nb_active": sum(1 for td in tournaments_data if td["active"]),
            "best_points":  best_points,
            "best_mahjong": best_mahjong,
            "national_rank": national_rank,
            "best_national_rank": best_national_rank,
            "date_best_national_rank": date_best_national_rank,
        }

    nationality_changes = db.query(NationalityChange).filter(
        NationalityChange.player_id == player_id
    ).order_by(NationalityChange.change_date).all()

    referee_rules = [
        r.rules for r in db.query(Referee.rules).filter(Referee.player_id == player_id).all()
    ]

    # Tournaments where this player was EMA observer
    obs_tournaments = (
        db.query(Tournament)
        .filter(Tournament.obs_player_id == player_id)
        .order_by(Tournament.start_date.desc())
        .all()
    )

    # Tournaments where this player was referee (via TournamentReferee)
    referee_assignments = (
        db.query(TournamentReferee)
        .filter(TournamentReferee.player_id == player_id)
        .join(Tournament, TournamentReferee.tournament_id == Tournament.id)
        .order_by(Tournament.start_date.desc())
        .all()
    )

    import os as _os
    photo_path = _os.path.join(_os.path.dirname(__file__), "../static/photos", f"{player_id}.jpg")
    player_photo = _os.path.exists(photo_path)

    return templates.TemplateResponse(request, "players/detail.html", {
        "player": player,
        "mcr": build_tab("MCR"),
        "rcr": build_tab("RCR"),
        "week": week,
        "nationality_changes": nationality_changes,
        "freeze_start": FREEZE_START.isoformat(),
        "freeze_end": FREEZE_END.isoformat(),
        "referee_rules": referee_rules,
        "obs_tournaments": obs_tournaments,
        "referee_assignments": referee_assignments,
        "player_photo": player_photo,
    })


@router.get("/{player_id}/apercu")
def player_preview(
    player_id: str, request: Request,
    week: str = None,
    rules: str = "MCR",
    country_code: str = None,
    db: Session = Depends(get_db)
):
    """HTML fragment for the ranking side panel."""
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        return templates.TemplateResponse(request, "players/preview.html", {"player": None})
    try:
        week_date = week_monday(date.fromisoformat(week)) if week else week_monday(date.today())
    except ValueError:
        week_date = week_monday(date.today())
    week = week_date

    active_mcr = {t.id: (t, c) for t, c in active_tournaments(db, week, "MCR")}
    active_rcr = {t.id: (t, c) for t, c in active_tournaments(db, week, "RCR")}

    def stats(rules_key):
        from app.models import RankingHistory, Result, Tournament as T
        current_ranking = db.query(RankingHistory).filter(
            RankingHistory.player_id == player_id,
            RankingHistory.rules == rules_key,
            RankingHistory.week == week,
        ).first()

        if country_code:
            from app.models import RankingHistory as RH, Player as P
            from sqlalchemy import func
            player_rows = db.query(RH.week, RH.position, RH.score).filter(
                RH.player_id == player_id,
                RH.rules == rules_key,
            ).all()
            compatriots = {
                r[0]: r[1] for r in
                db.query(P.id, P.nationality).filter(P.nationality == player.nationality).all()
            }
            compatriot_ids = list(compatriots.keys())
            best = None
            best_national_rank = None
            for row in player_rows:
                nb_above = db.query(func.count(RH.player_id)).filter(
                    RH.rules == rules_key,
                    RH.week == row.week,
                    RH.player_id.in_(compatriot_ids),
                    RH.position < row.position,
                ).scalar() or 0
                national_rank = nb_above + 1
                if best_national_rank is None or national_rank < best_national_rank:
                    best_national_rank = national_rank
                    best = type('BestNational', (), {
                        'position': national_rank,
                        'week': row.week,
                        'score': row.score,
                    })()

        else:
            best = db.query(RankingHistory).filter(
                RankingHistory.player_id == player_id,
                RankingHistory.rules == rules_key,
            ).order_by(RankingHistory.position).first()

        nb_total = db.query(Result).join(T).filter(
            Result.player_id == player_id,
            T.rules == rules_key,
            T.tournament_type.notin_(["wmc", "wrc"]),
            T.ema_id.isnot(None),
        ).count()

        active_ids = active_mcr if rules_key == "MCR" else active_rcr
        active_results = db.query(Result).join(T).filter(
            Result.player_id == player_id,
            Result.tournament_id.in_(active_ids.keys()),
            T.ema_id.isnot(None)
        ).all()

        snapshot = sorted([
            {
                "date":       active_ids[r.tournament_id][0].start_date,
                "name":       active_ids[r.tournament_id][0].name,
                "ema_id":     active_ids[r.tournament_id][0].ema_id,
                "contrib":    active_ids[r.tournament_id][1],
                "coeff":      active_ids[r.tournament_id][0].coefficient,
                "position":   r.position,
                "nb_players": active_ids[r.tournament_id][0].nb_players,
                "ranking":    r.ranking,
            }
            for r in active_results
        ], key=lambda x: x["date"], reverse=True)

        return {
            "ranking": current_ranking,
            "best": best,
            "nb_total": nb_total,
            "nb_active": len(active_results),
            "snapshot": snapshot,
        }

    active_rules = rules.upper() if rules else "MCR"
    base_ranking = f"/countries/{country_code}" if country_code else "/ranking"

    import os as _os
    photo_path = _os.path.join(_os.path.dirname(__file__), "../static/photos", f"{player_id}.jpg")
    player_photo = _os.path.exists(photo_path)

    return templates.TemplateResponse(request, "players/preview.html", {
        "player":        player,
        "mcr":           stats("MCR"),
        "rcr":           stats("RCR"),
        "rules":         active_rules,
        "week":          week,
        "base_ranking":  base_ranking,
        "player_photo":  player_photo,
    })

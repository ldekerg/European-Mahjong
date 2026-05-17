import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from datetime import date

from app.database import get_db
from app.models import Player, Tournament, Result, RankingHistory, NationalityChange
from app.ranking import week_monday, active_tournaments, _player_results, contribution, FREEZE_START, FREEZE_END

router = APIRouter(prefix="/players")
from app.i18n import templates


@router.get("/")
def liste_joueurs(
    request: Request,
    sort: str = "name",        # id | name | first_name | nationality | nb_mcr | nb_rcr | nb_total
    asc: int = 1,              # 1 = ascending, 0 = descending
    rules: str = "all",        # all | MCR | RCR
    q: str = "",               # text search
    db: Session = Depends(get_db),
):
    from app.models import Result, Tournament as T
    from sqlalchemy import func

    # Subqueries to count tournaments per player/rules + date of first tournament
    mcr_count = (
        db.query(Result.player_id, func.count(Result.id).label("nb"))
        .join(T).filter(T.rules == "MCR").group_by(Result.player_id).subquery()
    )
    rcr_count = (
        db.query(Result.player_id, func.count(Result.id).label("nb"))
        .join(T).filter(T.rules == "RCR").group_by(Result.player_id).subquery()
    )
    premier_tournoi = (
        db.query(Result.player_id, func.min(T.start_date).label("premier"))
        .join(T).filter(T.start_date != date(1900, 1, 1))
        .group_by(Result.player_id).subquery()
    )

    qr = db.query(
        Player,
        func.coalesce(mcr_count.c.nb, 0).label("nb_mcr"),
        func.coalesce(rcr_count.c.nb, 0).label("nb_rcr"),
        premier_tournoi.c.premier.label("premier"),
    ).outerjoin(mcr_count, Player.id == mcr_count.c.player_id
    ).outerjoin(rcr_count, Player.id == rcr_count.c.player_id
    ).outerjoin(premier_tournoi, Player.id == premier_tournoi.c.player_id)

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
        "premier":     premier_tournoi.c.premier,
    }
    col = col_map.get(sort, Player.last_name)
    qr = qr.order_by(col if asc else col.desc())

    rows = qr.all()
    joueurs_list = [{"player": r[0], "nb_mcr": r[1], "nb_rcr": r[2], "nb_total": r[1]+r[2], "premier": r[3]} for r in rows]

    return templates.TemplateResponse(request, "players/list.html", {
        "players":          joueurs_list,
        "sort":             sort,
        "asc":              asc,
        "rules":            rules,
        "q":                q,
        "total":            len(joueurs_list),
        "current_week": week_monday(date.today()),
    })



@router.get("/{player_id}")
def detail_joueur(player_id: str, request: Request, db: Session = Depends(get_db)):
    joueur = db.query(Player).filter(Player.id == player_id).first()
    if not joueur:
        return templates.TemplateResponse(request, "404.html", status_code=404)

    week = week_monday(date.today())

    def build_tab(regles: str):
        # Current ranking
        rang = db.query(RankingHistory).filter(
            RankingHistory.player_id == player_id,
            RankingHistory.rules == regles,
            RankingHistory.week == week,
        ).first()

        # Ranking history (all weeks)
        historique = (
            db.query(RankingHistory)
            .filter(
                RankingHistory.player_id == player_id,
                RankingHistory.rules == regles,
            )
            .order_by(RankingHistory.week)
            .all()
        )

        # Best ranking and max score
        meilleur = min((h.position for h in historique), default=None)
        score_max = max((h.score for h in historique), default=None)
        score_max = round(score_max, 2) if score_max else None
        # Dates of maxima for the chart
        date_meilleur = next((h.week.isoformat() for h in historique if h.position == meilleur), None)
        date_score_max = next((h.week.isoformat() for h in historique if score_max and round(h.score,2) == score_max), None)

        # Played tournaments with details
        actifs = {t.id: (t, c) for t, c in active_tournaments(db, week, regles)}
        results = (
            db.query(Result)
            .join(Tournament)
            .filter(Result.player_id == player_id, Tournament.rules == regles,
                    Tournament.ema_id.isnot(None))
            .order_by(Tournament.start_date.desc())
            .all()
        )

        tournois_data = []
        for r in results:
            t = r.tournament
            c = contribution(t.start_date, week) if t.start_date.year != 1900 else 0.0
            tournois_data.append({
                "date": t.start_date,
                "duree": max(1, (t.end_date - t.start_date).days + 1) if t.end_date and t.start_date.year != 1900 else 1,
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
                "actif": t.id in actifs or (
                    t.tournament_type in ("wmc", "wrc") and
                    t.start_date.year != 1900 and
                    (week - t.start_date).days <= 730
                ),
                "nat_tournoi": r.nationality or joueur.nationality,
            })

        historique_chart = [
            {"week": h.week.isoformat(), "position": h.position, "score": round(h.score, 2)}
            for h in historique
        ]

        # Best Mahjong score — exclude unusual formats (han-count < 100, anonymous WRC = 1)
        best_points = max(
            (td for td in tournois_data if td["points"] > 0 and td["points"] < 100),
            key=lambda x: x["points"], default=None,
        )
        seuil = 10000 if regles == "RCR" else 100
        best_mahjong = max(
            (td for td in tournois_data if td["mahjong"] and td["mahjong"] > seuil),
            key=lambda x: x["mahjong"], default=None,
        )

        return {
            "rang": rang,
            "meilleur": meilleur,
            "score_max": score_max,
            "date_meilleur": date_meilleur,
            "date_score_max": date_score_max,
            "historique": historique,
            "historique_chart": historique_chart,
            "tournaments": tournois_data,
            "nb_actifs": sum(1 for td in tournois_data if td["actif"]),
            "best_points":  best_points,
            "best_mahjong": best_mahjong,
        }

    changements = db.query(NationalityChange).filter(
        NationalityChange.player_id == player_id
    ).order_by(NationalityChange.change_date).all()

    return templates.TemplateResponse(request, "players/detail.html", {
        "player": joueur,
        "mcr": build_tab("MCR"),
        "rcr": build_tab("RCR"),
        "week": week,
        "changements_nat": changements,
        "freeze_debut": FREEZE_START.isoformat(),
        "freeze_fin": FREEZE_END.isoformat(),
    })


@router.get("/{player_id}/apercu")
def apercu_joueur(
    player_id: str, request: Request,
    week: str = None,
    rules: str = "MCR",
    pays_code: str = None,
    db: Session = Depends(get_db)
):
    """HTML fragment for the ranking side panel."""
    joueur = db.query(Player).filter(Player.id == player_id).first()
    if not joueur:
        return templates.TemplateResponse(request, "players/preview.html", {"player": None})
    try:
        week_date = week_monday(date.fromisoformat(week)) if week else week_monday(date.today())
    except ValueError:
        week_date = week_monday(date.today())
    week = week_date

    actifs_mcr = {t.id: (t, c) for t, c in active_tournaments(db, week, "MCR")}
    actifs_rcr = {t.id: (t, c) for t, c in active_tournaments(db, week, "RCR")}

    def stats(rules_key):
        from app.models import RankingHistory, Result, Tournament as T
        rang_actuel = db.query(RankingHistory).filter(
            RankingHistory.player_id == player_id,
            RankingHistory.rules == rules_key,
            RankingHistory.week == week,
        ).first()

        if pays_code:
            # Best national rank: for each week of the player, count compatriots ranked above
            from app.models import RankingHistory as CH, Player as J
            from sqlalchemy import func
            # Player positions per week
            joueur_rows = db.query(CH.week, CH.position, CH.score).filter(
                CH.player_id == player_id,
                CH.rules == rules_key,
            ).all()
            # Ranked compatriots (all players from the same country)
            compatriotes = {
                r[0]: r[1] for r in
                db.query(J.id, J.nationality).filter(J.nationality == joueur.nationality).all()
            }
            compatriote_ids = list(compatriotes.keys())
            meilleur = None
            best_rang_nat = None
            for row in joueur_rows:
                nb_devant = db.query(func.count(CH.player_id)).filter(
                    CH.rules == rules_key,
                    CH.week == row.week,
                    CH.player_id.in_(compatriote_ids),
                    CH.position < row.position,
                ).scalar() or 0
                rang_nat = nb_devant + 1
                if best_rang_nat is None or rang_nat < best_rang_nat:
                    best_rang_nat = rang_nat
                    meilleur = type('MeilleurNat', (), {
                        'position': rang_nat,
                        'week': row.week,
                        'score': row.score,
                    })()

        else:
            meilleur = db.query(RankingHistory).filter(
                RankingHistory.player_id == player_id,
                RankingHistory.rules == rules_key,
            ).order_by(RankingHistory.position).first()

        nb_total = db.query(Result).join(T).filter(
            Result.player_id == player_id,
            T.rules == rules_key,
            T.tournament_type.notin_(["wmc", "wrc"]),
            T.ema_id.isnot(None),
        ).count()

        ids_dict = actifs_mcr if rules_key == "MCR" else actifs_rcr
        resultats_actifs = db.query(Result).join(T).filter(
            Result.player_id == player_id,
            Result.tournament_id.in_(ids_dict.keys()),
            T.ema_id.isnot(None)
        ).all()

        snapshot = sorted([
            {
                "date":      ids_dict[r.tournament_id][0].start_date,
                "name":       ids_dict[r.tournament_id][0].name,
                "ema_id":    ids_dict[r.tournament_id][0].ema_id,
                "contrib":   ids_dict[r.tournament_id][1],
                "coeff":     ids_dict[r.tournament_id][0].coefficient,
                "position":  r.position,
                "nb_players":ids_dict[r.tournament_id][0].nb_players,
                "ranking":   r.ranking,
            }
            for r in resultats_actifs
        ], key=lambda x: x["date"], reverse=True)

        return {
            "rang": rang_actuel,
            "meilleur": meilleur,
            "nb_total": nb_total,
            "nb_actifs": len(resultats_actifs),
            "snapshot": snapshot,
        }

    active_rules = rules.upper() if rules else "MCR"
    # Base URL for best ranking links
    base_ranking = f"/countries/{pays_code}" if pays_code else "/ranking"

    return templates.TemplateResponse(request, "players/preview.html", {
        "player":           joueur,
        "mcr":              stats("MCR"),
        "rcr":              stats("RCR"),
        "rules":           active_rules,
        "week":          week,
        "base_ranking":  base_ranking,
    })


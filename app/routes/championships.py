import json
from collections import Counter
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Championship, ChampionshipTournament, Player, Result, AnonymousResult, ChampionshipSeries, Tournament
from app.i18n import templates
from app.ranking import ema_points

router = APIRouter(prefix="/championships")

FORMULE_MOYENNE = "moyenne_n_meilleurs"


def _ranking_championnat(db: Session, championnat: Championship) -> list:
    params = json.loads(championnat.params or '{}')
    tournoi_ids = [lien.tournament_id for lien in championnat.tournament_links]

    if not tournoi_ids or championnat.formula != FORMULE_MOYENNE:
        return []

    # Pre-load tournaments to avoid N+1 on nb_players
    tournaments_map = {t.id: t for t in db.query(Tournament).filter(Tournament.id.in_(tournoi_ids)).all()}

    par_joueur_id: dict[str, dict[int, int]] = {}
    for r in db.query(Result.player_id, Result.ranking, Result.tournament_id
                      ).filter(Result.tournament_id.in_(tournoi_ids)).all():
        par_joueur_id.setdefault(r.player_id, {})[r.tournament_id] = r.ranking

    # Anonymous: separate meta from results per tournament
    by_anonymous: dict[tuple, dict] = {}
    for r in db.query(AnonymousResult.first_name, AnonymousResult.last_name,
                      AnonymousResult.nationality, AnonymousResult.tournament_id,
                      AnonymousResult.position
                      ).filter(AnonymousResult.tournament_id.in_(tournoi_ids)).all():
        ranking = ema_points(r.position, tournaments_map[r.tournament_id].nb_players)
        key = ((r.first_name or "").strip().upper(), (r.last_name or "").strip().upper(), r.nationality or "")
        entry = by_anonymous.setdefault(key, {"nationality": r.nationality, "first_name": r.first_name, "name": r.last_name, "results": {}})
        entry["results"][r.tournament_id] = ranking

    n = params.get("n", 3)
    scores = []

    players_map = {j.id: j for j in db.query(Player).filter(Player.id.in_(par_joueur_id.keys())).all()}
    for jid, by_tournament in par_joueur_id.items():
        j = players_map.get(jid)
        if not j:
            continue
        all_rankings = [by_tournament.get(tid, 0) for tid in tournoi_ids]
        top_n = sorted(all_rankings, reverse=True)[:n]
        scores.append({
            "player_id": jid, "player": j, "nom_affiche": None,
            "nationality": j.nationality, "anonyme": False,
            "score": round(sum(top_n) / n, 1),
            "nb_tournaments": len(by_tournament), "nb_comptes": n,
        })

    for key, data in by_anonymous.items():
        by_tournament = data["results"]
        all_rankings = [by_tournament.get(tid, 0) for tid in tournoi_ids]
        top_n = sorted(all_rankings, reverse=True)[:n]
        prenom, nom = data.get("prenom") or "", data.get("nom") or ""
        scores.append({
            "player_id": None, "player": None,
            "nom_affiche": f"{prenom} {nom}".strip(),
            "nationality": data.get("nationalite") or "", "anonyme": True,
            "score": round(sum(top_n) / n, 1),
            "nb_tournaments": len(by_tournament), "nb_comptes": n,
        })

    scores.sort(key=lambda x: (-x["score"], x["nom_affiche"] or (x["player"].last_name if x["player"] else "")))
    for pos, s in enumerate(scores, 1):
        s["position"] = pos

    return scores


def _resolve_champion(db: Session, edition) -> dict | None:
    """Returns the champion's info: identified player, free text, or None."""
    if edition.champion_id:
        j = db.query(Player).filter_by(id=edition.champion_id).first()
        if j:
            return {"player": j, "nom_affiche": None, "nationality": j.nationality}
    if edition.champion_name:
        return {"player": None, "nom_affiche": edition.champion_name, "nationality": None}
    return None


@router.get("/")
def liste_series(request: Request, db: Session = Depends(get_db)):
    series = db.query(ChampionshipSeries).order_by(ChampionshipSeries.country, ChampionshipSeries.name).all()
    return templates.TemplateResponse(request, "championships/list.html", {"series": series})


@router.get("/{slug}")
def detail_serie(slug: str, request: Request, db: Session = Depends(get_db)):
    serie = db.query(ChampionshipSeries).filter(ChampionshipSeries.slug == slug).first()
    if not serie:
        raise HTTPException(status_code=404)

    hall_of_fame = []
    for edition in serie.editions:
        cl = _ranking_championnat(db, edition)
        tournois = [lien.tournament for lien in edition.tournament_links]
        tournois.sort(key=lambda t: t.start_date)
        hall_of_fame.append({
            "edition": edition,
            "ranking": cl,
            "podium": cl[:3],
            "champion": _resolve_champion(db, edition),
            "tournaments": tournois,
        })

    return templates.TemplateResponse(request, "championships/series.html", {
        "serie": serie,
        "hall_of_fame": hall_of_fame,
    })


@router.get("/{slug}/{year}")
def detail_edition(slug: str, year: int, request: Request, db: Session = Depends(get_db)):
    serie = db.query(ChampionshipSeries).filter(ChampionshipSeries.slug == slug).first()
    if not serie:
        raise HTTPException(status_code=404)

    edition = db.query(Championship).filter(
        Championship.series_id == serie.id,
        Championship.year == year,
    ).first()
    if not edition:
        raise HTTPException(status_code=404)

    ranking = _ranking_championnat(db, edition)
    tournois = [lien.tournament for lien in edition.tournament_links]
    tournois.sort(key=lambda t: t.start_date)

    params = json.loads(edition.params or '{}')

    nats = [r["nationality"] for r in ranking if r.get("nationalite")]
    pays_stats = sorted(
        [{"code": k, "nb": v} for k, v in Counter(nats).items() if k],
        key=lambda x: -x["nb"],
    )

    return templates.TemplateResponse(request, "championships/detail.html", {
        "serie": serie,
        "edition": edition,
        "ranking": ranking,
        "podium": ranking[:3],

        "champion": _resolve_champion(db, edition),
        "tournaments": tournois,
        "params": params,
        "pays_stats": pays_stats,
    })

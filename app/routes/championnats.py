import json
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Championnat, ChampionnatTournoi, Joueur, Resultat, ResultatAnonyme, SerieChampionnat, Tournoi
from app.templates_config import templates

router = APIRouter(prefix="/championnats")


def _classement_championnat(db: Session, championnat: Championnat) -> list:
    """
    Calcule le classement général selon la formule du championnat.
    Inclut les joueurs identifiés (Resultat) et anonymes (ResultatAnonyme).
    Pour moyenne_n_meilleurs, les tournois non joués comptent 0.
    """
    params = json.loads(championnat.params or '{}')
    tournoi_ids = [lien.tournoi_id for lien in championnat.liens]
    nb_tournois_total = len(tournoi_ids)

    if not tournoi_ids:
        return []

    # --- Joueurs identifiés ---
    # clé : joueur_id (str)  valeur : {tournoi_id: ranking}
    par_joueur_id: dict[str, dict[int, int]] = {}
    for r in db.query(Resultat.joueur_id, Resultat.ranking, Resultat.tournoi_id
                      ).filter(Resultat.tournoi_id.in_(tournoi_ids)).all():
        par_joueur_id.setdefault(r.joueur_id, {})[r.tournoi_id] = r.ranking

    # --- Joueurs anonymes ---
    # clé : (prenom, nom) normalisé  valeur : {tournoi_id: ranking}
    par_anon: dict[tuple, dict[int, int]] = {}
    for r in db.query(ResultatAnonyme.prenom, ResultatAnonyme.nom,
                      ResultatAnonyme.nationalite, ResultatAnonyme.tournoi_id,
                      ResultatAnonyme.position
                      ).filter(ResultatAnonyme.tournoi_id.in_(tournoi_ids)).all():
        # ranking calculé depuis position et nb_joueurs du tournoi
        tournoi = db.query(Tournoi).filter_by(id=r.tournoi_id).first()
        from ranking import points_ema_tournoi
        ranking = points_ema_tournoi(r.position, tournoi.nb_joueurs)
        key = ((r.prenom or "").strip().upper(), (r.nom or "").strip().upper(), r.nationalite or "")
        par_anon.setdefault(key, {"nationalite": r.nationalite, "prenom": r.prenom, "nom": r.nom})[r.tournoi_id] = ranking

    if championnat.formule != "moyenne_n_meilleurs":
        return []

    n = params.get("n", 3)
    scores = []

    # Identifiés
    joueurs_map = {j.id: j for j in db.query(Joueur).filter(Joueur.id.in_(par_joueur_id.keys())).all()}
    for jid, par_tournoi in par_joueur_id.items():
        j = joueurs_map.get(jid)
        if not j:
            continue
        # Compléter les tournois non joués par 0
        all_rankings = [par_tournoi.get(tid, 0) for tid in tournoi_ids]
        top_n = sorted(all_rankings, reverse=True)[:n]
        score = sum(top_n) / n
        scores.append({
            "joueur_id": jid,
            "joueur": j,
            "nom_affiche": None,        # utilise joueur.prenom/nom
            "nationalite": j.nationalite,
            "anonyme": False,
            "score": round(score, 1),
            "nb_tournois": len(par_tournoi),
            "nb_comptes": n,
        })

    # Anonymes
    for key, data in par_anon.items():
        par_tournoi = {k: v for k, v in data.items() if isinstance(k, int)}
        all_rankings = [par_tournoi.get(tid, 0) for tid in tournoi_ids]
        top_n = sorted(all_rankings, reverse=True)[:n]
        score = sum(top_n) / n
        prenom = data.get("prenom") or ""
        nom = data.get("nom") or ""
        scores.append({
            "joueur_id": None,
            "joueur": None,
            "nom_affiche": f"{prenom} {nom}".strip(),
            "nationalite": data.get("nationalite") or "",
            "anonyme": True,
            "score": round(score, 1),
            "nb_tournois": len(par_tournoi),
            "nb_comptes": n,
        })

    scores.sort(key=lambda x: (-x["score"], x["nom_affiche"] or (x["joueur"].nom if x["joueur"] else "")))
    for pos, s in enumerate(scores, 1):
        s["position"] = pos

    return scores


def _podium(classement: list) -> list:
    return classement[:3]


def _resolve_champion(db: Session, edition) -> dict | None:
    """Retourne les infos du champion : joueur identifié, ou texte libre, ou None."""
    if edition.champion_id:
        j = db.query(Joueur).filter_by(id=edition.champion_id).first()
        if j:
            return {"joueur": j, "nom_affiche": None, "nationalite": j.nationalite}
    if edition.champion_nom:
        return {"joueur": None, "nom_affiche": edition.champion_nom, "nationalite": None}
    return None


@router.get("/")
def liste_series(request: Request, db: Session = Depends(get_db)):
    series = db.query(SerieChampionnat).order_by(SerieChampionnat.pays, SerieChampionnat.nom).all()
    return templates.TemplateResponse(request, "championnats/liste.html", {"series": series})


@router.get("/{slug}")
def detail_serie(slug: str, request: Request, db: Session = Depends(get_db)):
    serie = db.query(SerieChampionnat).filter(SerieChampionnat.slug == slug).first()
    if not serie:
        raise HTTPException(status_code=404)

    palmares = []
    for edition in serie.editions:
        cl = _classement_championnat(db, edition)
        tournois = [lien.tournoi for lien in edition.liens]
        tournois.sort(key=lambda t: t.date_debut)
        palmares.append({
            "edition": edition,
            "classement": cl,
            "podium": _podium(cl),
            "champion": _resolve_champion(db, edition),
            "tournois": tournois,
        })

    return templates.TemplateResponse(request, "championnats/serie.html", {
        "serie": serie,
        "palmares": palmares,
    })


@router.get("/{slug}/{annee}")
def detail_edition(slug: str, annee: int, request: Request, db: Session = Depends(get_db)):
    serie = db.query(SerieChampionnat).filter(SerieChampionnat.slug == slug).first()
    if not serie:
        raise HTTPException(status_code=404)

    edition = db.query(Championnat).filter(
        Championnat.serie_id == serie.id,
        Championnat.annee == annee,
    ).first()
    if not edition:
        raise HTTPException(status_code=404)

    classement = _classement_championnat(db, edition)
    tournois = [lien.tournoi for lien in edition.liens]
    tournois.sort(key=lambda t: t.date_debut)

    params = json.loads(edition.params or '{}')

    from collections import Counter
    nats = [r["nationalite"] for r in classement if r.get("nationalite")]
    pays_stats = sorted(
        [{"code": k, "nb": v} for k, v in Counter(nats).items() if k],
        key=lambda x: -x["nb"],
    )

    return templates.TemplateResponse(request, "championnats/detail.html", {
        "serie": serie,
        "edition": edition,
        "classement": classement,
        "podium": classement[:3],
        "champion": _resolve_champion(db, edition),
        "tournois": tournois,
        "params": params,
        "pays_stats": pays_stats,
    })

from fastapi import FastAPI, Request, Query
from fastapi.staticfiles import StaticFiles
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from typing import Optional
from sqlalchemy.orm import Session

from database import engine, SessionLocal
import models
from app.routes import joueurs, tournois, hallfame
from app.routes import pays
from app.templates_config import templates
from models import ClassementHistorique, Joueur
from ranking import lundi_semaine, classement

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="EMA Ranking")
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

app.include_router(joueurs.router)
app.include_router(tournois.router)
app.include_router(hallfame.router)
app.include_router(pays.router)


def get_delta_rang(db: Session, semaine: date, regles: str) -> dict:
    """Retourne {joueur_id: position_semaine_precedente} pour calculer le Δ rang."""
    from datetime import timedelta
    semaine_prec = semaine - timedelta(weeks=1)
    rows = db.query(ClassementHistorique.joueur_id, ClassementHistorique.position).filter(
        ClassementHistorique.semaine == semaine_prec,
        ClassementHistorique.regles == regles,
    ).all()
    return {r[0]: r[1] for r in rows}


def get_classement_semaine(db: Session, semaine: date, regles: str) -> list:
    """Récupère le classement depuis l'historique ou le calcule en direct."""
    rows = (
        db.query(ClassementHistorique, Joueur)
        .join(Joueur, ClassementHistorique.joueur_id == Joueur.id)
        .filter(
            ClassementHistorique.semaine == semaine,
            ClassementHistorique.regles == regles,
        )
        .order_by(ClassementHistorique.position)
        .all()
    )
    if rows:
        return [
            {
                "position":    ch.position,
                "joueur_id":   ch.joueur_id,
                "nom":         j.nom,
                "prenom":      j.prenom,
                "nationalite": j.nationalite,
                "score":       ch.score,
                "nb_tournois": ch.nb_tournois or 0,
                "nb_or":       ch.nb_or or 0,
                "nb_argent":   ch.nb_argent or 0,
                "nb_bronze":   ch.nb_bronze or 0,
                "delta":       None,  # rempli après
            }
            for ch, j in rows
        ]
    # Calcul en direct si semaine non encore stockée
    raw = classement(db, semaine, regles)
    joueurs_map = {j.id: j for j in db.query(Joueur).all()}
    return [
        {
            "position":    r["position"],
            "joueur_id":   r["joueur_id"],
            "nom":         joueurs_map[r["joueur_id"]].nom,
            "prenom":      joueurs_map[r["joueur_id"]].prenom,
            "nationalite": joueurs_map[r["joueur_id"]].nationalite,
            "score":       r["score"],
            "nb_tournois": r["nb_tournois"],
            "nb_or":       r["nb_or"],
            "nb_argent":   r["nb_argent"],
            "nb_bronze":   r["nb_bronze"],
        }
        for r in raw
        if r["joueur_id"] in joueurs_map
    ]


@app.get("/")
def accueil(
    request: Request,
    semaine: Optional[str] = Query(None),
    joueur: Optional[str] = Query(None),
    regles: Optional[str] = Query(None),  # onglet actif à afficher (MCR ou RCR)
):
    db = SessionLocal()
    try:
        if semaine:
            try:
                semaine_date = lundi_semaine(date.fromisoformat(semaine))
            except ValueError:
                semaine_date = lundi_semaine(date.today())
        else:
            semaine_date = lundi_semaine(date.today())

        mcr = get_classement_semaine(db, semaine_date, "MCR")
        rcr = get_classement_semaine(db, semaine_date, "RCR")

        # Calculer le Δ rang
        for lst, regles_key in [(mcr, "MCR"), (rcr, "RCR")]:
            prev = get_delta_rang(db, semaine_date, regles_key)
            for r in lst:
                p = prev.get(r["joueur_id"])
                r["delta"] = (p - r["position"]) if p else None  # positif = montée

        # Toutes les semaines pour navigation prev/next
        semaines_raw = [
            row[0] for row in
            db.query(ClassementHistorique.semaine)
            .filter(ClassementHistorique.regles == "MCR")
            .distinct()
            .order_by(ClassementHistorique.semaine)
            .all()
        ]
        total = len(semaines_raw)
        idx_courant = next((i for i, s in enumerate(semaines_raw) if s == semaine_date), total - 1)
        semaine_prev = semaines_raw[idx_courant - 1].isoformat() if idx_courant > 0 else None
        semaine_next = semaines_raw[idx_courant + 1].isoformat() if idx_courant < total - 1 else None

        # Dropdown : toutes les semaines, groupées par année
        from collections import defaultdict
        par_annee: dict = defaultdict(list)
        for i, s in enumerate(semaines_raw):
            par_annee[s.year].append({"date": s, "num": i + 1})
        semaines_dispo = [
            {"annee": yr, "semaines": list(reversed(wks))}
            for yr, wks in sorted(par_annee.items(), reverse=True)
        ]
    finally:
        db.close()

    semaine_actuelle = lundi_semaine(date.today())
    aujourd_hui = date.today()

    return templates.TemplateResponse(request, "accueil.html", {
        "mcr": mcr,
        "rcr": rcr,
        "semaine_actuelle": semaine_actuelle,
        "aujourd_hui": aujourd_hui,
        "semaine": semaine_date,
        "semaine_num": idx_courant + 1,
        "semaine_prev": semaine_prev,
        "semaine_next": semaine_next,
        "semaines_dispo": semaines_dispo,
        "joueur_selectionne": joueur,
        "onglet_actif": (regles or "MCR").upper(),
        "joueur_defaut": mcr[0]["joueur_id"] if mcr else None,
        "joueur_defaut_mcr": mcr[0]["joueur_id"] if mcr else None,
        "joueur_defaut_rcr": rcr[0]["joueur_id"] if rcr else None,
    })

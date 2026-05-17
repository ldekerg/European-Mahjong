from fastapi import FastAPI, Request, Query
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from typing import Optional
from sqlalchemy.orm import Session

from app.database import engine, SessionLocal
import app.models as models
from app.routes import players, tournaments, hof, championships
from app.routes import countries
from app.i18n import templates
from app.models import ClassementHistorique, Joueur
from app.ranking import lundi_semaine, classement

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="EMA Ranking")
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

app.include_router(players.router)
app.include_router(tournaments.router)
app.include_router(hof.router)
app.include_router(countries.router)
app.include_router(championships.router)


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


@app.get("/accueil")
def home(request: Request):
    from app.models import Tournoi, Resultat, ResultatAnonyme
    from app.routes.hof import _meilleur_europeen
    from sqlalchemy import func, exists
    db = SessionLocal()
    try:
        today = date.today()
        semaine_date = lundi_semaine(today)

        # Stats globales
        nb_joueurs   = db.query(Joueur).filter(Joueur.statut == "europeen").count()
        nb_tournois  = db.query(Tournoi).count()
        nb_classes_mcr = db.query(ClassementHistorique.joueur_id).filter(
            ClassementHistorique.semaine == semaine_date,
            ClassementHistorique.regles  == "MCR",
        ).distinct().count()
        nb_classes_rcr = db.query(ClassementHistorique.joueur_id).filter(
            ClassementHistorique.semaine == semaine_date,
            ClassementHistorique.regles  == "RCR",
        ).distinct().count()

        # Top 5 MCR et RCR
        def top5(regles):
            rows = (
                db.query(ClassementHistorique, Joueur)
                .join(Joueur, ClassementHistorique.joueur_id == Joueur.id)
                .filter(
                    ClassementHistorique.semaine == semaine_date,
                    ClassementHistorique.regles  == regles,
                )
                .order_by(ClassementHistorique.position)
                .limit(5).all()
            )
            return [{"position": ch.position, "joueur": j, "score": ch.score} for ch, j in rows]

        # Derniers tournois joués : avec résultats ET date passée
        has_resultats = exists().where(Resultat.tournoi_id == Tournoi.id)
        from datetime import date as _date
        derniers = (
            db.query(Tournoi)
            .filter(
                Tournoi.date_debut <= today,
                Tournoi.date_debut != _date(1900, 1, 1),
                has_resultats,
            )
            .order_by(Tournoi.date_debut.desc())
            .limit(6).all()
        )

        # Prochains tournois : date future ET sans résultats
        has_no_resultats = ~exists().where(Resultat.tournoi_id == Tournoi.id)
        prochains = (
            db.query(Tournoi)
            .filter(
                Tournoi.date_debut > today,
                has_no_resultats,
                Tournoi.type_tournoi == "normal",
            )
            .order_by(Tournoi.date_debut)
            .limit(6).all()
        )

        # Calendrier (pour le partial compact de la home)
        from collections import defaultdict
        MOIS_FR = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
                   "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
        cal_tournois = (
            db.query(Tournoi)
            .filter(Tournoi.statut == "calendrier")
            .order_by(Tournoi.date_debut)
            .all()
        )
        cal_par_mois_raw = defaultdict(list)
        for t in cal_tournois:
            cal_par_mois_raw[(t.date_debut.year, t.date_debut.month)].append(t)
        calendrier_par_mois = [
            {"label": f"{MOIS_FR[m]} {y}", "tournois": ts}
            for (y, m), ts in sorted(cal_par_mois_raw.items())
        ]

        # Champions en titre
        champions = {
            "oemc": _meilleur_europeen(db, "oemc"),
            "wmc":  _meilleur_europeen(db, "wmc"),
            "oerc": _meilleur_europeen(db, "oerc"),
            "wrc":  _meilleur_europeen(db, "wrc"),
        }

    finally:
        db.close()

    return templates.TemplateResponse(request, "home.html", {
        "nb_joueurs":    nb_joueurs,
        "nb_tournois":   nb_tournois,
        "nb_classes_mcr": nb_classes_mcr,
        "nb_classes_rcr": nb_classes_rcr,
        "top_mcr":       top5("MCR"),
        "top_rcr":       top5("RCR"),
        "derniers":           derniers,
        "prochains":          prochains,
        "champions":          champions,
        "calendrier_par_mois": calendrier_par_mois,
    })


@app.get("/classement")
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

    return templates.TemplateResponse(request, "classement.html", {
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


@app.get("/")
def root():
    return RedirectResponse(url="/accueil")

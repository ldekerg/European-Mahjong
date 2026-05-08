import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, Depends, Request, Form, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
from database import get_db
from models import Tournoi, Resultat, Joueur
from ranking import lundi_semaine, tournois_actifs

router = APIRouter(prefix="/tournois")
from app.templates_config import templates


@router.get("/")
def liste_tournois(
    request: Request,
    vue: str = Query("tous"),
    regles: str = Query("tous"),
    tri: str = Query("date"),
    asc: int = Query(0),       # 1 = ascendant, 0 = descendant (défaut desc pour date/coeff/joueurs)
    ville: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    semaine = lundi_semaine(date.today())
    regles_list = ["MCR", "RCR"] if regles == "tous" else [regles]
    actifs_ids: dict = {}
    for r in regles_list:
        actifs_ids.update({t.id: c for t, c in tournois_actifs(db, semaine, r)})

    q = db.query(Tournoi)
    if regles != "tous":
        q = q.filter(Tournoi.regles == regles)

    if vue == "actifs":
        q = q.filter(Tournoi.id.in_(actifs_ids.keys()))
    elif vue == "speciaux":
        q = q.filter(Tournoi.type_tournoi.in_(["wmc", "wrc", "oemc", "oerc"]))
    # "tous" = pas de filtre supplémentaire

    # Tri
    col_map = {
        "date":    Tournoi.date_debut,
        "coeff":   Tournoi.coefficient,
        "joueurs": Tournoi.nb_joueurs,
        "nom":     Tournoi.nom,
    }
    col = col_map.get(tri, Tournoi.date_debut)
    q = q.order_by(col if asc else col.desc())

    if ville:
        q = q.filter(Tournoi.lieu == ville)

    tournois_list = q.filter(Tournoi.date_debut != date(1900, 1, 1)).all()

    # Points carte : villes avec coordonnées
    from sqlalchemy import func
    villes_q = db.query(
        Tournoi.lieu, Tournoi.pays,
        Tournoi.latitude, Tournoi.longitude,
        func.count(Tournoi.id).label("nb"),
    ).filter(
        Tournoi.latitude.isnot(None),
        Tournoi.lieu != "",
    )
    if regles != "tous":
        villes_q = villes_q.filter(Tournoi.regles == regles)
    villes = villes_q.group_by(Tournoi.lieu, Tournoi.pays, Tournoi.latitude, Tournoi.longitude).all()

    return templates.TemplateResponse(request, "tournois/liste.html", {
        "tournois": tournois_list,
        "actifs_ids": actifs_ids,
        "vue": vue,
        "regles": regles,
        "tri": tri,
        "asc": asc,
        "semaine": semaine,
        "villes": [{"lieu": v.lieu, "pays": v.pays, "lat": v.latitude, "lon": v.longitude, "nb": v.nb} for v in villes],
        "ville_filtre": ville,
    })


@router.get("/nouveau")
def nouveau_tournoi_form(request: Request):
    return templates.TemplateResponse(request, "tournois/form.html", {"tournoi": None})


@router.post("/nouveau")
def creer_tournoi(
    request: Request,
    id: int = Form(...),
    nom: str = Form(...),
    lieu: str = Form(...),
    pays: str = Form(...),
    date_debut: date = Form(...),
    date_fin: date = Form(...),
    nb_joueurs: int = Form(...),
    coefficient: float = Form(...),
    regles: str = Form(...),
    db: Session = Depends(get_db),
):
    tournoi = Tournoi(
        id=id, nom=nom, lieu=lieu, pays=pays,
        date_debut=date_debut, date_fin=date_fin,
        nb_joueurs=nb_joueurs, coefficient=coefficient, regles=regles,
    )
    db.add(tournoi)
    db.commit()
    return RedirectResponse(url="/tournois/", status_code=303)


@router.get("/{regles}_{ema_id}")
def detail_tournoi_ema(regles: str, ema_id: int, request: Request, db: Session = Depends(get_db)):
    tournoi = db.query(Tournoi).filter(Tournoi.ema_id == ema_id, Tournoi.regles == regles.upper()).first()
    if not tournoi:
        return templates.TemplateResponse(request, "404.html", status_code=404)
    return detail_tournoi(tournoi.id, request, db)


@router.get("/{tournoi_id}")
def detail_tournoi(tournoi_id: int, request: Request, db: Session = Depends(get_db)):
    tournoi = db.query(Tournoi).filter(Tournoi.id == tournoi_id).first()
    resultats = (
        db.query(Resultat)
        .filter(Resultat.tournoi_id == tournoi_id)
        .order_by(Resultat.position)
        .all()
    )
    joueurs = db.query(Joueur).order_by(Joueur.nom).all()
    return templates.TemplateResponse(request, "tournois/detail.html",
        {"tournoi": tournoi, "resultats": resultats, "joueurs": joueurs})


@router.post("/{tournoi_id}/resultats")
def ajouter_resultat(
    tournoi_id: int,
    joueur_id: str = Form(...),
    position: int = Form(...),
    points: int = Form(...),
    mahjong: int = Form(...),
    ranking: int = Form(...),
    db: Session = Depends(get_db),
):
    resultat = Resultat(
        tournoi_id=tournoi_id, joueur_id=joueur_id,
        position=position, points=points, mahjong=mahjong, ranking=ranking,
    )
    db.add(resultat)
    db.commit()
    return RedirectResponse(url=f"/tournois/{tournoi_id}", status_code=303)

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from datetime import date

from database import get_db
from models import Joueur, Tournoi, Resultat, ClassementHistorique, ChangementNationalite
from ranking import lundi_semaine, tournois_actifs, _resultats_actifs, contribution, FREEZE_DEBUT, FREEZE_FIN

router = APIRouter(prefix="/joueurs")
from app.templates_config import templates


@router.get("/")
def liste_joueurs(
    request: Request,
    tri: str = "nom",          # id | nom | prenom | nationalite | nb_mcr | nb_rcr | nb_total
    asc: int = 1,              # 1 = ascendant, 0 = descendant
    regles: str = "tous",      # tous | MCR | RCR
    q: str = "",               # recherche textuelle
    db: Session = Depends(get_db),
):
    from models import Resultat, Tournoi as T
    from sqlalchemy import func

    # Sous-requêtes pour compter les tournois par joueur/règle + date premier tournoi
    mcr_count = (
        db.query(Resultat.joueur_id, func.count(Resultat.id).label("nb"))
        .join(T).filter(T.regles == "MCR").group_by(Resultat.joueur_id).subquery()
    )
    rcr_count = (
        db.query(Resultat.joueur_id, func.count(Resultat.id).label("nb"))
        .join(T).filter(T.regles == "RCR").group_by(Resultat.joueur_id).subquery()
    )
    premier_tournoi = (
        db.query(Resultat.joueur_id, func.min(T.date_debut).label("premier"))
        .join(T).filter(T.date_debut != date(1900, 1, 1))
        .group_by(Resultat.joueur_id).subquery()
    )

    qr = db.query(
        Joueur,
        func.coalesce(mcr_count.c.nb, 0).label("nb_mcr"),
        func.coalesce(rcr_count.c.nb, 0).label("nb_rcr"),
        premier_tournoi.c.premier.label("premier"),
    ).outerjoin(mcr_count, Joueur.id == mcr_count.c.joueur_id
    ).outerjoin(rcr_count, Joueur.id == rcr_count.c.joueur_id
    ).outerjoin(premier_tournoi, Joueur.id == premier_tournoi.c.joueur_id)

    if regles == "MCR":
        qr = qr.filter(mcr_count.c.nb > 0)
    elif regles == "RCR":
        qr = qr.filter(rcr_count.c.nb > 0)

    if q:
        like = f"%{q.upper()}%"
        qr = qr.filter((Joueur.nom.ilike(like)) | (Joueur.prenom.ilike(like)) | (Joueur.id.ilike(like)))

    col_map = {
        "id":          Joueur.id,
        "nom":         Joueur.nom,
        "prenom":      Joueur.prenom,
        "nationalite": Joueur.nationalite,
        "nb_mcr":      func.coalesce(mcr_count.c.nb, 0),
        "nb_rcr":      func.coalesce(rcr_count.c.nb, 0),
        "nb_total":    func.coalesce(mcr_count.c.nb, 0) + func.coalesce(rcr_count.c.nb, 0),
        "premier":     premier_tournoi.c.premier,
    }
    col = col_map.get(tri, Joueur.nom)
    qr = qr.order_by(col if asc else col.desc())

    rows = qr.all()
    joueurs_list = [{"joueur": r[0], "nb_mcr": r[1], "nb_rcr": r[2], "nb_total": r[1]+r[2], "premier": r[3]} for r in rows]

    return templates.TemplateResponse(request, "joueurs/liste.html", {
        "joueurs":          joueurs_list,
        "tri":              tri,
        "asc":              asc,
        "regles":           regles,
        "q":                q,
        "total":            len(joueurs_list),
        "semaine_actuelle": lundi_semaine(date.today()),
    })



@router.get("/{joueur_id}")
def detail_joueur(joueur_id: str, request: Request, db: Session = Depends(get_db)):
    joueur = db.query(Joueur).filter(Joueur.id == joueur_id).first()
    if not joueur:
        return templates.TemplateResponse(request, "404.html", status_code=404)

    semaine = lundi_semaine(date.today())

    def build_tab(regles: str):
        # Classement actuel
        rang = db.query(ClassementHistorique).filter(
            ClassementHistorique.joueur_id == joueur_id,
            ClassementHistorique.regles == regles,
            ClassementHistorique.semaine == semaine,
        ).first()

        # Historique classement (toutes les semaines)
        historique = (
            db.query(ClassementHistorique)
            .filter(
                ClassementHistorique.joueur_id == joueur_id,
                ClassementHistorique.regles == regles,
            )
            .order_by(ClassementHistorique.semaine)
            .all()
        )

        # Meilleur classement et score max
        meilleur = min((h.position for h in historique), default=None)
        score_max = max((h.score for h in historique), default=None)
        score_max = round(score_max, 2) if score_max else None
        # Dates des maxima pour le graphique
        date_meilleur = next((h.semaine.isoformat() for h in historique if h.position == meilleur), None)
        date_score_max = next((h.semaine.isoformat() for h in historique if score_max and round(h.score,2) == score_max), None)

        # Tournois joués avec détails
        actifs = {t.id: (t, c) for t, c in tournois_actifs(db, semaine, regles)}
        resultats = (
            db.query(Resultat)
            .join(Tournoi)
            .filter(Resultat.joueur_id == joueur_id, Tournoi.regles == regles,
                    Tournoi.ema_id.isnot(None))
            .order_by(Tournoi.date_debut.desc())
            .all()
        )

        tournois_data = []
        for r in resultats:
            t = r.tournoi
            c = contribution(t.date_debut, semaine) if t.date_debut.year != 1900 else 0.0
            tournois_data.append({
                "date": t.date_debut,
                "duree": max(1, (t.date_fin - t.date_debut).days + 1) if t.date_fin and t.date_debut.year != 1900 else 1,
                "nom": t.nom,
                "lieu": t.lieu,
                "pays": t.pays,
                "ema_id": t.ema_id,
                "contrib": c,
                "coeff": t.coefficient,
                "points": r.points,
                "mahjong": r.mahjong,
                "position": r.position,
                "nb_joueurs": t.nb_joueurs,
                "ranking": r.ranking,
                "type": t.type_tournoi,
                "actif": t.id in actifs or (
                    t.type_tournoi in ("wmc", "wrc") and
                    t.date_debut.year != 1900 and
                    (semaine - t.date_debut).days <= 730
                ),
                "nat_tournoi": r.nationalite or joueur.nationalite,
            })

        historique_chart = [
            {"semaine": h.semaine.isoformat(), "position": h.position, "score": round(h.score, 2)}
            for h in historique
        ]

        # Meilleur score Mahjong — on exclut les formats inhabituels (han-count < 100, anonymes WRC = 1)
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
            "tournois": tournois_data,
            "nb_actifs": sum(1 for td in tournois_data if td["actif"]),
            "best_points":  best_points,
            "best_mahjong": best_mahjong,
        }

    changements = db.query(ChangementNationalite).filter(
        ChangementNationalite.joueur_id == joueur_id
    ).order_by(ChangementNationalite.date_changement).all()

    return templates.TemplateResponse(request, "joueurs/detail.html", {
        "joueur": joueur,
        "mcr": build_tab("MCR"),
        "rcr": build_tab("RCR"),
        "semaine": semaine,
        "changements_nat": changements,
        "freeze_debut": FREEZE_DEBUT.isoformat(),
        "freeze_fin": FREEZE_FIN.isoformat(),
    })


@router.get("/{joueur_id}/apercu")
def apercu_joueur(
    joueur_id: str, request: Request,
    semaine: str = None,
    regles: str = "MCR",
    db: Session = Depends(get_db)
):
    """Fragment HTML pour le panneau latéral du classement."""
    joueur = db.query(Joueur).filter(Joueur.id == joueur_id).first()
    if not joueur:
        return templates.TemplateResponse(request, "joueurs/apercu.html", {"joueur": None})
    try:
        semaine_date = lundi_semaine(date.fromisoformat(semaine)) if semaine else lundi_semaine(date.today())
    except ValueError:
        semaine_date = lundi_semaine(date.today())
    semaine = semaine_date

    def rang(regles):
        from models import ClassementHistorique
        r = db.query(ClassementHistorique).filter(
            ClassementHistorique.joueur_id == joueur_id,
            ClassementHistorique.regles == regles,
            ClassementHistorique.semaine == semaine,
        ).first()
        return r

    actifs_mcr = {t.id: (t, c) for t, c in tournois_actifs(db, semaine, "MCR")}
    actifs_rcr = {t.id: (t, c) for t, c in tournois_actifs(db, semaine, "RCR")}

    def nb_actifs(regles):
        from models import Resultat, Tournoi as T
        ids = actifs_mcr if regles == "MCR" else actifs_rcr
        return db.query(Resultat).join(T).filter(
            Resultat.joueur_id == joueur_id,
            Resultat.tournoi_id.in_(ids),
        ).count()

    def stats(regles):
        from models import ClassementHistorique, Resultat, Tournoi as T
        rang_actuel = db.query(ClassementHistorique).filter(
            ClassementHistorique.joueur_id == joueur_id,
            ClassementHistorique.regles == regles,
            ClassementHistorique.semaine == semaine,
        ).first()

        meilleur = db.query(ClassementHistorique).filter(
            ClassementHistorique.joueur_id == joueur_id,
            ClassementHistorique.regles == regles,
        ).order_by(ClassementHistorique.position).first()

        nb_total = db.query(Resultat).join(T).filter(
            Resultat.joueur_id == joueur_id,
            T.regles == regles,
            T.type_tournoi.notin_(["wmc", "wrc"]),
            T.ema_id.isnot(None),
        ).count()

        ids_dict = actifs_mcr if regles == "MCR" else actifs_rcr
        resultats_actifs = db.query(Resultat).join(T).filter(
            Resultat.joueur_id == joueur_id,
            Resultat.tournoi_id.in_(ids_dict.keys()),
        ).all()

        snapshot = sorted([
            {
                "date":      ids_dict[r.tournoi_id][0].date_debut,
                "nom":       ids_dict[r.tournoi_id][0].nom,
                "ema_id":    ids_dict[r.tournoi_id][0].ema_id,
                "contrib":   ids_dict[r.tournoi_id][1],
                "coeff":     ids_dict[r.tournoi_id][0].coefficient,
                "position":  r.position,
                "nb_joueurs":ids_dict[r.tournoi_id][0].nb_joueurs,
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

    regles_active = regles.upper() if regles else "MCR"
    return templates.TemplateResponse(request, "joueurs/apercu.html", {
        "joueur":  joueur,
        "mcr":     stats("MCR"),
        "rcr":     stats("RCR"),
        "regles":  regles_active,
        "semaine": semaine,
    })



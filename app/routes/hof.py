import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from typing import Optional

from app.database import get_db
from app.models import ClassementHistorique, Joueur, Resultat, ResultatAnonyme, Tournoi
from app.i18n import templates, PAYS_EMA

router = APIRouter(prefix="/hallfame")


def _hof_data(db: Session, regles: str, actifs_ids=None):
    """Calcule les stats Hall of Fame pour une discipline."""
    # Agrégations sur classement_historique
    stats = db.query(
        ClassementHistorique.joueur_id,
        func.count(ClassementHistorique.id).label("nb_semaines"),
        func.sum(case((ClassementHistorique.position == 1,  1), else_=0)).label("nb_or"),
        func.sum(case((ClassementHistorique.position <= 2,  1), else_=0)).label("nb_argent"),
        func.sum(case((ClassementHistorique.position <= 3,  1), else_=0)).label("nb_bronze"),
        func.sum(case((ClassementHistorique.position <= 10, 1), else_=0)).label("nb_top10"),
        func.sum(case((ClassementHistorique.position <= 20, 1), else_=0)).label("nb_top20"),
        func.sum(case((ClassementHistorique.position <= 50, 1), else_=0)).label("nb_top50"),
        func.min(case((ClassementHistorique.position == 1, ClassementHistorique.semaine), else_=None)).label("premiere_1"),
        func.min(case((ClassementHistorique.position <= 10, ClassementHistorique.semaine), else_=None)).label("premiere_top10"),
        func.min(ClassementHistorique.position).label("meilleur_rang"),
        func.max(ClassementHistorique.score).label("score_max"),
    ).filter(
        ClassementHistorique.regles == regles,
    ).group_by(ClassementHistorique.joueur_id).subquery()

    qr = db.query(stats, Joueur).join(Joueur, stats.c.joueur_id == Joueur.id)
    if actifs_ids is not None:
        qr = qr.filter(stats.c.joueur_id.in_(actifs_ids))
    rows = qr.all()

    result = []
    for row in rows:
        j = row.Joueur
        result.append({
            "joueur":        j,
            "nb_semaines":   row.nb_semaines or 0,
            "nb_or":         row.nb_or or 0,
            "nb_argent":     row.nb_argent or 0,
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
    """Résultats OEMC/WMC/OERC/WRC."""
    types = ["wmc", "oemc"] if regles == "MCR" else ["wrc", "oerc"]
    rows = db.query(Resultat, Tournoi, Joueur).join(
        Tournoi, Resultat.tournoi_id == Tournoi.id
    ).join(
        Joueur, Resultat.joueur_id == Joueur.id
    ).filter(
        Tournoi.type_tournoi.in_(types),
        Tournoi.date_debut.isnot(None),
    ).order_by(Tournoi.date_debut.desc(), Resultat.position).all()
    return rows


def _meilleur_europeen(db: Session, type_tournoi: str):
    """Meilleur joueur européen du dernier tournoi de ce type."""
    from sqlalchemy import func
    # Date du dernier tournoi de ce type AVEC des résultats
    dernier = db.query(func.max(Tournoi.date_debut)).join(
        Resultat, Resultat.tournoi_id == Tournoi.id
    ).filter(
        Tournoi.type_tournoi == type_tournoi
    ).scalar()
    if not dernier:
        return None

    tournoi = db.query(Tournoi).filter(
        Tournoi.type_tournoi == type_tournoi,
        Tournoi.date_debut == dernier,
    ).first()

    resultat = db.query(Resultat, Joueur).join(
        Joueur, Resultat.joueur_id == Joueur.id
    ).filter(
        Resultat.tournoi_id == tournoi.id,
        Joueur.statut == "europeen",
    ).order_by(Resultat.position).first()

    if not resultat:
        return None

    r, j = resultat
    return {
        "tournoi":  tournoi,
        "joueur":   j,
        "position": r.position,
        "est_champion": r.position == 1,
        "est_vice":     r.position == 2,
        "est_bronze":   r.position == 3,
    }


def _palmares_championnats(db: Session, regles: str) -> list:
    """Pour chaque tournoi majeur avec résultats, retourne les 3 meilleurs (identifiés + anonymes fusionnés)."""
    types = ["wmc", "oemc"] if regles == "MCR" else ["wrc", "oerc"]
    tournois = db.query(Tournoi).filter(
        Tournoi.type_tournoi.in_(types),
        Tournoi.date_debut.isnot(None),
        Tournoi.date_debut != __import__('datetime').date(1900, 1, 1),
    ).order_by(Tournoi.date_debut.desc()).all()

    result = []
    for t in tournois:
        identifies = db.query(Resultat, Joueur).join(
            Joueur, Resultat.joueur_id == Joueur.id
        ).filter(
            Resultat.tournoi_id == t.id,
            Joueur.statut == "europeen",
        ).order_by(Resultat.position).all()

        anonymes = db.query(ResultatAnonyme).filter(
            ResultatAnonyme.tournoi_id == t.id,
            ResultatAnonyme.nationalite.in_(PAYS_EMA),
        ).order_by(ResultatAnonyme.position).all()

        # Fusionner et trier par position, garder top3
        all_entries = [
            {"joueur": j, "position": r.position, "nationalite": r.nationalite, "anonyme": False}
            for r, j in identifies
        ] + [
            {"joueur": None, "position": a.position, "nationalite": a.nationalite,
             "prenom": a.prenom, "nom": a.nom, "anonyme": True}
            for a in anonymes
        ]
        all_entries.sort(key=lambda x: x["position"])

        if not all_entries:
            continue  # Tournoi sans résultats

        result.append({
            "tournoi": t,
            "top3":    all_entries[:3],
        })
    return result


def _compute_hof(db: Session, regles: str, periode: str) -> dict:
    """Calcule toutes les données HoF pour une discipline et une période."""
    from app.ranking import lundi_semaine, FREEZE_DEBUT, FREEZE_FIN
    from datetime import date as dt
    from collections import defaultdict

    semaine_actuelle = lundi_semaine(dt.today())
    actifs_ids = None
    streak_map = {}

    if periode == "encours":
        toutes = db.query(
            ClassementHistorique.joueur_id,
            ClassementHistorique.semaine,
        ).filter(
            ClassementHistorique.regles == regles,
        ).order_by(
            ClassementHistorique.joueur_id,
            ClassementHistorique.semaine.desc(),
        ).all()

        par_joueur = defaultdict(list)
        for jid, sem in toutes:
            par_joueur[jid].append(sem)

        freeze_gap = (FREEZE_FIN - FREEZE_DEBUT).days // 7 + 1

        for jid, semaines in par_joueur.items():
            if semaines[0] != semaine_actuelle:
                continue
            streak = 1
            for k in range(1, len(semaines)):
                diff = (semaines[k-1] - semaines[k]).days // 7
                if diff == 1:
                    streak += 1
                elif diff == freeze_gap:
                    streak += 1
                else:
                    break
            streak_map[jid] = streak

        actifs_ids = set(streak_map.keys())

    data = _hof_data(db, regles, actifs_ids)
    championnats = _championnats(db, regles)

    medals_q = db.query(
        Resultat.joueur_id,
        func.sum(case((Resultat.position == 1, 1), else_=0)).label("or_t"),
        func.sum(case((Resultat.position == 2, 1), else_=0)).label("argent_t"),
        func.sum(case((Resultat.position == 3, 1), else_=0)).label("bronze_t"),
        func.count(Resultat.id).label("total_t"),
    ).join(Tournoi, Resultat.tournoi_id == Tournoi.id
    ).filter(Tournoi.regles == regles
    ).group_by(Resultat.joueur_id).subquery()

    medals_rows = db.query(medals_q, Joueur).join(Joueur, medals_q.c.joueur_id == Joueur.id).all()
    medals_data = [{
        "joueur":   row.Joueur,
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
            jid = d["joueur"].id
            total_streak = streak_map.get(jid, 0)
            toutes_serie = db.query(
                ClassementHistorique.semaine,
                ClassementHistorique.position,
            ).filter(
                ClassementHistorique.joueur_id == jid,
                ClassementHistorique.regles == regles,
            ).order_by(ClassementHistorique.semaine.desc()).limit(total_streak).all()

            d["nb_semaines"] = total_streak
            d["nb_or"]    = streak_for(toutes_serie, 1)
            d["nb_argent"] = streak_for(toutes_serie, 2)
            d["nb_bronze"] = streak_for(toutes_serie, 3)
            d["nb_top10"]  = streak_for(toutes_serie, 10)
            d["nb_top20"]  = streak_for(toutes_serie, 20)
            d["nb_top50"]  = streak_for(toutes_serie, 50)

    if periode == "encours":
        data.sort(key=lambda x: (-x["nb_or"], -x["nb_bronze"], -x["nb_top10"], -x["nb_top20"], -x["nb_top50"]))
        data = [d for d in data if d["nb_top50"] > 0]
    else:
        data.sort(key=lambda x: (-x["nb_or"], -x["nb_argent"], -x["nb_bronze"]))
        data = [d for d in data if d["nb_semaines"] > 0]

    return {"data": data, "medals_data": medals_data, "championnats": championnats}


def _records(db: Session, regles: str) -> dict:
    """Top 20 scores mahjong et (MCR seulement) top 20 points tournoi."""
    base = db.query(
        Resultat, Tournoi, Joueur,
    ).join(Tournoi, Resultat.tournoi_id == Tournoi.id
    ).join(Joueur, Resultat.joueur_id == Joueur.id
    ).filter(
        Tournoi.regles == regles,
        Tournoi.type_tournoi.notin_(["wmc", "wrc"]),
    )

    def _row(r, t, j):
        return {
            "joueur":        j,
            "points":        r.points,
            "mahjong":       r.mahjong,
            "tournoi_nom":   t.nom,
            "tournoi_regles": t.regles,
            "tournoi_ema_id": t.ema_id,
            "nb_joueurs":    t.nb_joueurs,
            "date":          t.date_debut,
        }

    from datetime import timedelta

    seuil_mah = 10000 if regles == "RCR" else 100

    def _top_mahjong(q, limit=20):
        return [_row(r, t, j) for r, t, j in
                q.filter(Resultat.mahjong > seuil_mah)
                 .order_by(Resultat.mahjong.desc())
                 .limit(limit).all()]

    def _top_points(q, limit=20):
        return [_row(r, t, j) for r, t, j in
                q.filter(Resultat.points.between(1, 99))
                 .order_by(Resultat.points.desc())
                 .limit(limit).all()]

    # Filtre tournois 2 jours (date_fin - date_debut <= 1 jour)
    base_2j = base.filter(
        (func.julianday(Tournoi.date_fin) - func.julianday(Tournoi.date_debut)) <= 1
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
    vue: str = Query("medailles"),   # medailles | semaines | championnats | records
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

    from app.routes.tournois import _incomplets_ids
    tous_ids = [item["tournoi"].id for item in palmares_mcr + palmares_rcr]
    incomplets = _incomplets_ids(db, tous_ids)

    records_mcr = _records(db, "MCR")
    records_rcr = _records(db, "RCR")

    return templates.TemplateResponse(request, "hallfame.html", {
        "mcr":          mcr,
        "rcr":          rcr,
        "vue":          vue,
        "periode":      periode,
        "champions":    champions,
        "palmares_mcr": palmares_mcr,
        "palmares_rcr": palmares_rcr,
        "incomplets":    incomplets,
        "records_mcr":   records_mcr,
        "records_rcr":   records_rcr,
    })

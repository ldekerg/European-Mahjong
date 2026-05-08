import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text, case
from datetime import date as dt, timedelta
from typing import Optional
from collections import defaultdict

from database import get_db
from models import Joueur, Tournoi, Resultat, ClassementHistorique
from ranking import lundi_semaine, tournois_actifs, FREEZE_DEBUT, FREEZE_FIN
from app.templates_config import templates, ISO_NOM_PAYS, _PAYS_ISO

router = APIRouter(prefix="/pays")

def _chart_joueurs_liste(db):
    """Deux courbes globales MCR + RCR (total joueurs classés par semaine)."""
    rows = db.execute(text('''
        SELECT ch.semaine, ch.regles, COUNT(DISTINCT ch.joueur_id) AS nb
        FROM classement_historique ch
        JOIN joueurs j ON j.id = ch.joueur_id
        WHERE j.nationalite NOT IN ('', 'GUEST')
        GROUP BY ch.semaine, ch.regles
        ORDER BY ch.semaine
    ''')).fetchall()

    par_regles: dict = defaultdict(dict)
    semaines_set: set = set()
    for sem, r, nb in rows:
        par_regles[r][sem] = nb
        semaines_set.add(sem)

    labels = sorted(semaines_set)
    mcr = par_regles['MCR']
    rcr = par_regles['RCR']

    return {
        'labels': [s.isoformat() if hasattr(s, 'isoformat') else str(s) for s in labels],
        'datasets': [
            {'label': 'Tout', 'cssColor': '--chart-tout', 'width': 2.5,
             'data': [mcr.get(s, 0) + rcr.get(s, 0) for s in labels]},
            {'label': 'MCR',  'cssColor': '--chart-mcr',  'width': 2,
             'data': [mcr.get(s, 0) for s in labels]},
            {'label': 'RCR',  'cssColor': '--chart-rcr',  'width': 2,
             'data': [rcr.get(s, 0) for s in labels]},
        ],
    }


def _chart_joueurs_detail(db, code):
    """
    Retourne MCR, RCR et Total (MCR+RCR) pour un seul pays.
    Format : {labels, datasets: [{label, color, width, data}]}
    """
    rows = db.execute(text('''
        SELECT ch.semaine, ch.regles, COUNT(DISTINCT ch.joueur_id) AS nb
        FROM classement_historique ch
        JOIN joueurs j ON j.id = ch.joueur_id
        WHERE j.nationalite = :c
        GROUP BY ch.semaine, ch.regles
        ORDER BY ch.semaine
    '''), {'c': code}).fetchall()

    par_regles: dict = defaultdict(dict)
    semaines_set: set = set()
    for sem, r, nb in rows:
        par_regles[r][sem] = nb
        semaines_set.add(sem)

    labels = sorted(semaines_set)
    mcr = par_regles['MCR']
    rcr = par_regles['RCR']

    return {
        'labels': [s.isoformat() if hasattr(s, 'isoformat') else str(s) for s in labels],
        'datasets': [
            {'label': 'Tout', 'cssColor': '--chart-tout', 'width': 2,
             'data': [mcr.get(s, 0) + rcr.get(s, 0) for s in labels]},
            {'label': 'MCR',  'cssColor': '--chart-mcr',  'width': 2,
             'data': [mcr.get(s, 0) for s in labels]},
            {'label': 'RCR',  'cssColor': '--chart-rcr',  'width': 2,
             'data': [rcr.get(s, 0) for s in labels]},
        ],
    }


def _pays_name(code: str) -> str:
    return ISO_NOM_PAYS.get(code.upper(), code)


def _pays_tournois_name(code: str) -> str:
    """Retourne le nom de pays tel qu'il apparaît dans la table tournois."""
    return ISO_NOM_PAYS.get(code.upper(), code)


def _classement_pays(db, semaine, regles, code):
    """Classement global filtré aux joueurs du pays code."""
    rows = (
        db.query(ClassementHistorique, Joueur)
        .join(Joueur, ClassementHistorique.joueur_id == Joueur.id)
        .filter(
            ClassementHistorique.semaine == semaine,
            ClassementHistorique.regles == regles,
            Joueur.nationalite == code,
        )
        .order_by(ClassementHistorique.position)
        .all()
    )
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
            "delta":       None,
        }
        for ch, j in rows
    ]


def _rang_national_semaine(db, semaine, regles, code):
    """Retourne {joueur_id: rang_national} pour une semaine donnée."""
    rows = (
        db.query(ClassementHistorique.joueur_id)
        .join(Joueur, ClassementHistorique.joueur_id == Joueur.id)
        .filter(
            ClassementHistorique.semaine == semaine,
            ClassementHistorique.regles == regles,
            Joueur.nationalite == code,
        )
        .order_by(ClassementHistorique.position)
        .all()
    )
    return {row[0]: i + 1 for i, row in enumerate(rows)}


def _semaines_nav(db):
    """Retourne la liste des semaines disponibles (depuis MCR)."""
    return [
        row[0] for row in
        db.query(ClassementHistorique.semaine)
        .filter(ClassementHistorique.regles == "MCR")
        .distinct()
        .order_by(ClassementHistorique.semaine)
        .all()
    ]


def _score_equipe(top3: list) -> float:
    """Moyenne des 3 meilleurs scores (0 pour les joueurs manquants)."""
    scores = [r["score"] for r in top3[:3]]
    while len(scores) < 3:
        scores.append(0.0)
    return round(sum(scores) / 3, 2)


def _classement_equipes(db, semaine, regles):
    """
    Pour chaque pays : top 3 joueurs classés à semaine/regles,
    score équipe = moyenne des 3 (0 si absent).
    Retourne une liste triée par score_equipe desc.
    """
    rows = (
        db.query(ClassementHistorique, Joueur)
        .join(Joueur, ClassementHistorique.joueur_id == Joueur.id)
        .filter(
            ClassementHistorique.semaine == semaine,
            ClassementHistorique.regles == regles,
            Joueur.nationalite.notin_(["", "GUEST"]),
        )
        .order_by(ClassementHistorique.position)
        .all()
    )

    # Grouper par pays, garder top 3
    par_pays: dict[str, list] = defaultdict(list)
    for ch, j in rows:
        if len(par_pays[j.nationalite]) < 3:
            par_pays[j.nationalite].append({
                "joueur_id":   ch.joueur_id,
                "nom":         j.nom,
                "prenom":      j.prenom,
                "nationalite": j.nationalite,
                "position":    ch.position,
                "score":       round(ch.score, 2),
            })

    equipes = []
    for code, top3 in par_pays.items():
        equipes.append({
            "code":         code,
            "nom":          _pays_name(code),
            "top3":         top3,
            "score_equipe": _score_equipe(top3),
            "nb_classes":   len(top3),
        })

    equipes.sort(key=lambda x: -x["score_equipe"])
    for i, e in enumerate(equipes):
        e["rang"] = i + 1

    return equipes


@router.get("/")
def pays_liste(
    request: Request,
    semaine: Optional[str] = Query(None),
    onglet: str = Query("liste"),
    db: Session = Depends(get_db),
):
    if semaine:
        try:
            semaine_date = lundi_semaine(dt.fromisoformat(semaine))
        except ValueError:
            semaine_date = lundi_semaine(dt.today())
    else:
        semaine_date = lundi_semaine(dt.today())

    # ── Classement équipes ────────────────────────────────────────────────
    equipes_mcr = _classement_equipes(db, semaine_date, "MCR")
    equipes_rcr = _classement_equipes(db, semaine_date, "RCR")

    # Navigation semaines
    semaines_raw = _semaines_nav(db)
    total = len(semaines_raw)
    idx = next((i for i, s in enumerate(semaines_raw) if s == semaine_date), total - 1)
    semaine_prev = semaines_raw[idx - 1].isoformat() if idx > 0 else None
    semaine_next = semaines_raw[idx + 1].isoformat() if idx < total - 1 else None
    par_annee: dict = defaultdict(list)
    for i, s in enumerate(semaines_raw):
        par_annee[s.year].append({"date": s, "num": i + 1})
    semaines_dispo = [
        {"annee": yr, "semaines": list(reversed(wks))}
        for yr, wks in sorted(par_annee.items(), reverse=True)
    ]

    # ── Stats générales par pays ──────────────────────────────────────────
    joueurs_par_pays = dict(
        db.query(Joueur.nationalite, func.count(Joueur.id))
        .filter(Joueur.nationalite.notin_(["", "GUEST"]))
        .group_by(Joueur.nationalite)
        .all()
    )

    tournois_par_pays_nom = dict(
        db.query(Tournoi.pays, func.count(Tournoi.id))
        .filter(Tournoi.pays != "")
        .group_by(Tournoi.pays)
        .all()
    )
    tournois_par_code: dict = defaultdict(int)
    for nom, nb in tournois_par_pays_nom.items():
        iso = _PAYS_ISO.get(nom.lower().strip())
        if iso:
            tournois_par_code[iso] += nb

    # Joueurs actifs (classés cette semaine, MCR ou RCR)
    actifs_par_pays = dict(
        db.query(Joueur.nationalite, func.count(ClassementHistorique.joueur_id.distinct()))
        .join(ClassementHistorique, ClassementHistorique.joueur_id == Joueur.id)
        .filter(
            ClassementHistorique.semaine == semaine_date,
            Joueur.nationalite.notin_(["", "GUEST"]),
        )
        .group_by(Joueur.nationalite)
        .all()
    )

    # Tous les pays connus
    tous_codes = set(joueurs_par_pays.keys()) - {"", "GUEST"}
    pays_list = sorted([
        {
            "code":          code,
            "nom":           _pays_name(code),
            "nb_joueurs":    joueurs_par_pays.get(code, 0),
            "nb_actifs":     actifs_par_pays.get(code, 0),
            "nb_tournois":   tournois_par_code.get(code, 0),
        }
        for code in tous_codes
    ], key=lambda x: (-x["nb_joueurs"], x["nom"]))

    import json
    chart_liste = _chart_joueurs_liste(db)

    # ── Stats globales ────────────────────────────────────────────────────────
    stats_raw = db.execute(text('''
        SELECT
            (SELECT COUNT(*) FROM joueurs WHERE nationalite NOT IN ('', 'GUEST')) AS nb_joueurs,
            (SELECT COUNT(DISTINCT nationalite) FROM joueurs WHERE nationalite NOT IN ('', 'GUEST')) AS nb_pays,
            (SELECT COUNT(*) FROM tournois WHERE regles='MCR') AS nb_tournois_mcr,
            (SELECT COUNT(*) FROM tournois WHERE regles='RCR') AS nb_tournois_rcr,
            (SELECT COUNT(*) FROM classement_historique
             WHERE semaine=(SELECT MAX(semaine) FROM classement_historique WHERE regles='MCR')
               AND regles='MCR') AS classes_mcr,
            (SELECT COUNT(*) FROM classement_historique
             WHERE semaine=(SELECT MAX(semaine) FROM classement_historique WHERE regles='RCR')
               AND regles='RCR') AS classes_rcr
    ''')).fetchone()
    stats_globales = {
        "nb_joueurs":      stats_raw[0],
        "nb_pays":         stats_raw[1],
        "nb_tournois_mcr": stats_raw[2],
        "nb_tournois_rcr": stats_raw[3],
        "classes_mcr":     stats_raw[4],
        "classes_rcr":     stats_raw[5],
    }

    return templates.TemplateResponse(request, "pays/liste.html", {
        "equipes_mcr":    equipes_mcr,
        "equipes_rcr":    equipes_rcr,
        "pays_list":      pays_list,
        "onglet":         onglet,
        "stats":          stats_globales,
        "semaine":        semaine_date,
        "semaine_num":    idx + 1,
        "semaine_prev":   semaine_prev,
        "semaine_next":   semaine_next,
        "semaines_dispo": semaines_dispo,
        "aujourd_hui":    dt.today(),
        "chart_json":     json.dumps(chart_liste),
    })


@router.get("/{code}")
def pays_detail(
    request: Request,
    code: str,
    semaine: Optional[str] = Query(None),
    regles: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    code = code.upper()
    nom_pays = _pays_name(code)

    # Semaine courante
    if semaine:
        try:
            semaine_date = lundi_semaine(dt.fromisoformat(semaine))
        except ValueError:
            semaine_date = lundi_semaine(dt.today())
    else:
        semaine_date = lundi_semaine(dt.today())

    onglet_actif = (regles or "MCR").upper()

    # ── Classement ───────────────────────────────────────────────────────────
    mcr = _classement_pays(db, semaine_date, "MCR", code)
    rcr = _classement_pays(db, semaine_date, "RCR", code)

    semaine_prec = semaine_date - timedelta(weeks=1)
    for lst, r in [(mcr, "MCR"), (rcr, "RCR")]:
        rang_courant  = {row["joueur_id"]: i + 1 for i, row in enumerate(lst)}
        rang_precedent = _rang_national_semaine(db, semaine_prec, r, code)
        for row in lst:
            jid = row["joueur_id"]
            p = rang_precedent.get(jid)
            row["delta"] = (p - rang_courant[jid]) if p else None

    # Navigation semaines
    semaines_raw = _semaines_nav(db)
    total = len(semaines_raw)
    idx = next((i for i, s in enumerate(semaines_raw) if s == semaine_date), total - 1)
    semaine_prev = semaines_raw[idx - 1].isoformat() if idx > 0 else None
    semaine_next = semaines_raw[idx + 1].isoformat() if idx < total - 1 else None

    par_annee: dict = defaultdict(list)
    for i, s in enumerate(semaines_raw):
        par_annee[s.year].append({"date": s, "num": i + 1})
    semaines_dispo = [
        {"annee": yr, "semaines": list(reversed(wks))}
        for yr, wks in sorted(par_annee.items(), reverse=True)
    ]

    # Joueurs par défaut pour le panneau aperçu
    joueur_defaut_mcr = mcr[0]["joueur_id"] if mcr else None
    joueur_defaut_rcr = rcr[0]["joueur_id"] if rcr else None
    joueur_defaut = joueur_defaut_mcr if onglet_actif == "MCR" else joueur_defaut_rcr

    # ── Tournois du pays ─────────────────────────────────────────────────────
    pays_nom = _pays_tournois_name(code)
    tous_tournois = (
        db.query(Tournoi)
        .filter(Tournoi.pays == pays_nom)
        .order_by(Tournoi.date_debut.desc())
        .all()
    )
    actifs_dict = {t.id: c for t, c in tournois_actifs(db, semaine_date, "MCR")}
    actifs_dict.update({t.id: c for t, c in tournois_actifs(db, semaine_date, "RCR")})

    # Villes pour la carte
    villes_q = (
        db.query(Tournoi.lieu, Tournoi.pays, Tournoi.latitude, Tournoi.longitude,
                 func.count(Tournoi.id).label("nb"))
        .filter(Tournoi.pays == pays_nom, Tournoi.latitude.isnot(None))
        .group_by(Tournoi.lieu, Tournoi.pays, Tournoi.latitude, Tournoi.longitude)
        .all()
    )
    villes = [{"lieu": v.lieu, "pays": v.pays, "lat": v.latitude, "lon": v.longitude, "nb": v.nb}
              for v in villes_q]

    # ── Liste joueurs ─────────────────────────────────────────────────────────
    joueurs_q = db.query(Joueur).filter(Joueur.nationalite == code).order_by(Joueur.nom).all()
    _tpj = {
        row.joueur_id: row
        for row in db.query(
            Resultat.joueur_id,
            func.sum(case((Tournoi.regles == "MCR", 1), else_=0)).label("nb_mcr"),
            func.sum(case((Tournoi.regles == "RCR", 1), else_=0)).label("nb_rcr"),
        )
        .join(Tournoi, Resultat.tournoi_id == Tournoi.id)
        .filter(Resultat.joueur_id.in_([j.id for j in joueurs_q]))
        .group_by(Resultat.joueur_id)
        .all()
    }
    joueurs_data = [
        {
            "joueur":   j,
            "nb_mcr":   (_tpj[j.id].nb_mcr if j.id in _tpj else 0) or 0,
            "nb_rcr":   (_tpj[j.id].nb_rcr if j.id in _tpj else 0) or 0,
            "nb_total": ((_tpj[j.id].nb_mcr if j.id in _tpj else 0) or 0)
                       + ((_tpj[j.id].nb_rcr if j.id in _tpj else 0) or 0),
        }
        for j in joueurs_q
    ]

    nb_classes_mcr = len(mcr)
    nb_classes_rcr = len(rcr)
    meilleur_actuel_mcr = mcr[0]["position"] if mcr else None
    meilleur_actuel_rcr = rcr[0]["position"] if rcr else None

    import json
    chart_detail = _chart_joueurs_detail(db, code)

    return templates.TemplateResponse(request, "pays/detail.html", {
        "code":             code,
        "nom_pays":         nom_pays,
        # Stats
        "nb_joueurs":       len(joueurs_data),
        "nb_tournois_org":  len(tous_tournois),
        "nb_classes_mcr":       nb_classes_mcr,
        "nb_classes_rcr":       nb_classes_rcr,
        "meilleur_actuel_mcr":  meilleur_actuel_mcr,
        "meilleur_actuel_rcr":  meilleur_actuel_rcr,
        # Classement
        "mcr":              mcr,
        "rcr":              rcr,
        "semaine":          semaine_date,
        "semaine_num":      idx + 1,
        "semaine_prev":     semaine_prev,
        "semaine_next":     semaine_next,
        "semaines_dispo":   semaines_dispo,
        "aujourd_hui":      dt.today(),
        "onglet_actif":     onglet_actif,
        "joueur_defaut":         joueur_defaut,
        "joueur_defaut_mcr":     joueur_defaut_mcr,
        "joueur_defaut_rcr":     joueur_defaut_rcr,
        # Tournois
        "tournois":         tous_tournois,
        "actifs_ids":       actifs_dict,
        "villes":           villes,
        "ville_filtre":     None,
        # Joueurs
        "joueurs":          joueurs_data,
        # Graphique
        "chart_json":       json.dumps(chart_detail),
    })

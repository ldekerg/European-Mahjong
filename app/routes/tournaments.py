import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
from app.database import get_db
from app.models import Tournoi, Resultat, ResultatAnonyme, Joueur
from app.ranking import lundi_semaine, tournois_actifs

router = APIRouter(prefix="/tournois")
from app.i18n import templates, PAYS_EMA


def _incomplets_ids(db, tournoi_ids: list) -> set:
    """IDs de tournois avec au moins un anonyme européen sans nom (joueur EMA non identifié)."""
    if not tournoi_ids:
        return set()
    rows = db.query(ResultatAnonyme.tournoi_id).filter(
        ResultatAnonyme.tournoi_id.in_(tournoi_ids),
        ResultatAnonyme.nationalite.in_(PAYS_EMA),
        ResultatAnonyme.prenom.is_(None),
        ResultatAnonyme.nom.is_(None),
    ).distinct().all()
    return {row.tournoi_id for row in rows}


def _tournois_tab(db, regles: str, vue: str, tri: str, asc: int, ville) -> dict:
    from sqlalchemy import func
    semaine = lundi_semaine(date.today())
    actifs_ids = {t.id: c for t, c in tournois_actifs(db, semaine, regles)}

    q = db.query(Tournoi).filter(Tournoi.regles == regles, Tournoi.ema_id.isnot(None))
    if vue == "actifs":
        q = q.filter(Tournoi.id.in_(actifs_ids.keys()))
    elif vue == "speciaux":
        q = q.filter(Tournoi.type_tournoi.in_(["wmc", "wrc", "oemc", "oerc"]))

    col_map = {"date": Tournoi.date_debut, "coeff": Tournoi.coefficient,
               "joueurs": Tournoi.nb_joueurs, "nom": Tournoi.nom,
               "lieu": Tournoi.lieu, "pays": Tournoi.pays}
    col = col_map.get(tri, Tournoi.date_debut)
    q = q.order_by(col if asc else col.desc())
    if ville:
        q = q.filter(Tournoi.lieu == ville)
    tournois_list = q.filter(Tournoi.date_debut != date(1900, 1, 1)).all()

    from app.models import Ville
    vq = db.query(
        Tournoi.lieu, Tournoi.pays, Ville.latitude, Ville.longitude,
        func.count(Tournoi.id).label("nb"),
    ).join(Ville, Tournoi.ville_id == Ville.id
    ).filter(
        Tournoi.lieu != "", Tournoi.regles == regles,
        Tournoi.ema_id.isnot(None),
    )
    if vue == "actifs":
        vq = vq.filter(Tournoi.id.in_(actifs_ids.keys()))
    elif vue == "speciaux":
        vq = vq.filter(Tournoi.type_tournoi.in_(["wmc", "wrc", "oemc", "oerc"]))
    villes = [{"lieu": v.lieu, "pays": v.pays, "lat": v.latitude,
               "lon": v.longitude, "nb": v.nb}
              for v in vq.group_by(Tournoi.lieu, Tournoi.pays,
                                    Ville.latitude, Ville.longitude).all()]

    # Bounds pour la carte : fitBounds sur tout si vue=speciaux, sinon Europe par défaut
    carte_bounds = None
    if vue == "speciaux" and villes:
        lats = [v["lat"] for v in villes]
        lons = [v["lon"] for v in villes]
        carte_bounds = [[min(lats), min(lons)], [max(lats), max(lons)]]

    incomplets = _incomplets_ids(db, [t.id for t in tournois_list])

    return {
        "tournois":     tournois_list,
        "actifs_ids":   actifs_ids,
        "villes":       villes,
        "carte_bounds": carte_bounds,
        "incomplets":   incomplets,
    }


@router.get("/")
def liste_tournois(
    request: Request,
    vue: str = Query("tous"),
    tri: str = Query("date"),
    asc: int = Query(0),
    ville: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    mcr = _tournois_tab(db, "MCR", vue, tri, asc, ville)
    rcr = _tournois_tab(db, "RCR", vue, tri, asc, ville)

    return templates.TemplateResponse(request, "tournois/liste.html", {
        "mcr": mcr,
        "rcr": rcr,
        "vue": vue,
        "tri": tri,
        "asc": asc,
        "ville_filtre": ville,
        "carte_bounds_mcr": mcr["carte_bounds"],
        "carte_bounds_rcr": rcr["carte_bounds"],
    })


@router.get("/calendrier")
def calendrier(request: Request, db: Session = Depends(get_db)):
    from collections import defaultdict
    from datetime import date as _date
    MOIS_FR = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
               "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]

    tournois = (
        db.query(Tournoi)
        .filter(Tournoi.statut == "calendrier")
        .order_by(Tournoi.date_debut)
        .all()
    )

    par_mois = defaultdict(list)
    for t in tournois:
        par_mois[(t.date_debut.year, t.date_debut.month)].append(t)

    tournois_par_mois = [
        {"label": f"{MOIS_FR[m]} {y}", "tournois": ts}
        for (y, m), ts in sorted(par_mois.items())
    ]

    return templates.TemplateResponse(request, "tournois/calendrier.html", {
        "tournois_par_mois": tournois_par_mois,
        "nb_total": len(tournois),
    })



@router.get("/{regles}_{ema_id}")
def detail_tournoi_ema(regles: str, ema_id: int, request: Request, db: Session = Depends(get_db)):
    tournoi = db.query(Tournoi).filter(Tournoi.ema_id == ema_id, Tournoi.regles == regles.upper()).first()
    if not tournoi:
        return templates.TemplateResponse(request, "404.html", status_code=404)
    return detail_tournoi(tournoi.id, request, db)


@router.get("/{tournoi_id}")
def detail_tournoi(tournoi_id: int, request: Request, db: Session = Depends(get_db)):
    from collections import Counter
    tournoi = db.query(Tournoi).filter(Tournoi.id == tournoi_id).first()
    resultats_identifies = (
        db.query(Resultat)
        .filter(Resultat.tournoi_id == tournoi_id)
        .order_by(Resultat.position)
        .all()
    )
    resultats_anonymes = (
        db.query(ResultatAnonyme)
        .filter(ResultatAnonyme.tournoi_id == tournoi_id)
        .order_by(ResultatAnonyme.position)
        .all()
    )
    joueurs = db.query(Joueur).order_by(Joueur.nom).all()
    joueurs_map = {j.id: j for j in joueurs}

    # Liste unifiée triée par position : chaque entrée a les champs nécessaires au template
    def _as_row(r, joueur=None):
        return {
            "position":    r.position,
            "nationalite": r.nationalite or "",
            "joueur":      joueur,
            "ranking":     getattr(r, "ranking", None),
            "points":      getattr(r, "points", None),
            "mahjong":     getattr(r, "mahjong", None),
            "anonyme":     joueur is None,
            "prenom":      getattr(r, "prenom", None) or (joueur.prenom if joueur else ""),
            "nom":         getattr(r, "nom", None)    or (joueur.nom    if joueur else ""),
        }

    resultats_unifies = sorted(
        [_as_row(r, joueurs_map.get(r.joueur_id)) for r in resultats_identifies]
        + [_as_row(r) for r in resultats_anonymes],
        key=lambda x: x["position"],
    )

    # Pour rétrocompatibilité avec le reste du template (podium, pays_stats, etc.)
    resultats = resultats_identifies

    # Stats par pays (identifiés + anonymes avec drapeau)
    nat_list = [
        joueurs_map[r.joueur_id].nationalite
        for r in resultats_identifies
        if r.joueur_id in joueurs_map
    ] + [
        r.nationalite for r in resultats_anonymes if r.nationalite
    ]
    pays_count = Counter(nat_list)
    pays_stats = sorted(
        [{"code": k, "nb": v} for k, v in pays_count.items() if k and k != "GUEST"],
        key=lambda x: -x["nb"]
    )

    # Podium : top 3 avec rang de la médaille (combien de fois ce joueur a fini à cette position avant)
    from sqlalchemy import text as _text
    podium = []
    positions_podium = set()

    for r in resultats_identifies:
        if r.position > 3:
            break
        j = joueurs_map.get(r.joueur_id)
        if not j:
            continue
        rang_med = db.execute(_text('''
            SELECT COUNT(*) FROM resultats r2
            JOIN tournois t2 ON t2.id = r2.tournoi_id
            WHERE r2.joueur_id = :jid
              AND r2.position = :pos
              AND t2.regles   = :reg
              AND t2.date_debut < :ddate
        '''), {"jid": r.joueur_id, "pos": r.position,
               "reg": tournoi.regles, "ddate": tournoi.date_debut}).scalar() or 0
        podium.append({
            "position":      r.position,
            "joueur":        j,
            "rang_medaille": rang_med + 1,
            "anonyme":       False,
        })
        positions_podium.add(r.position)

    for r in resultats_anonymes:
        if r.position > 3:
            continue
        if r.position in positions_podium:
            continue
        podium.append({
            "position":      r.position,
            "joueur":        None,
            "rang_medaille": None,
            "anonyme":       True,
            "nationalite":   r.nationalite or "",
            "prenom":        r.prenom or "",
            "nom":           r.nom or "",
        })
        positions_podium.add(r.position)

    podium.sort(key=lambda x: x["position"])

    nb_resultats = len(resultats_identifies) + len(resultats_anonymes)
    nb_anon_europeens = sum(
        1 for r in resultats_anonymes
        if r.nationalite and r.nationalite.upper() in PAYS_EMA
        and not (r.prenom or r.nom)
    )  # PAYS_EMA défini en tête de module
    resultats_incomplets = nb_anon_europeens > 0

    # Championnat dont fait partie ce tournoi (s'il existe)
    from app.models import ChampionnatTournoi, Championnat, SerieChampionnat
    lien_champ = db.query(ChampionnatTournoi).filter_by(tournoi_id=tournoi_id).first()
    circuit_tournois = []
    circuit_serie = None
    circuit_edition = None
    if lien_champ:
        circuit_edition = db.query(Championnat).filter_by(id=lien_champ.championnat_id).first()
        circuit_serie = db.query(SerieChampionnat).filter_by(id=circuit_edition.serie_id).first()
        circuit_tournois = [
            l.tournoi for l in circuit_edition.liens
            if l.tournoi.ville_id
        ]

    return templates.TemplateResponse(request, "tournois/detail.html", {
        "tournoi":              tournoi,
        "resultats":            resultats_unifies,
        "joueurs":              joueurs,
        "pays_stats":           pays_stats,
        "nb_pays":              len(pays_stats),
        "podium":               podium,
        "resultats_incomplets":  resultats_incomplets,
        "nb_resultats":          nb_resultats,
        "nb_anon_europeens":     nb_anon_europeens,
        "is_mondial":            tournoi.type_tournoi in ('wmc', 'wrc'),
        "circuit_tournois":      circuit_tournois,
        "circuit_serie":         circuit_serie,
        "circuit_edition":       circuit_edition,
    })



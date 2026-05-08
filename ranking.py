from datetime import date, timedelta
from sqlalchemy.orm import Session
from models import Tournoi

# Période COVID : semaines exclues du décompte des 104 semaines
FREEZE_DEBUT = date(2020, 2, 24)  # début réel du freeze (tournois annulés)
FREEZE_FIN   = date(2022, 3, 28)  # reprise des tournois
FREEZE_SEMAINES = (FREEZE_FIN - FREEZE_DEBUT).days // 7


def lundi_semaine(d: date) -> date:
    """Retourne le lundi de la semaine contenant d."""
    return d - timedelta(days=d.weekday())


def semaine_debut_tournoi(date_debut: date) -> date:
    """Lundi de la semaine X+1 : première semaine où le tournoi compte."""
    return lundi_semaine(date_debut) + timedelta(weeks=1)


def semaines_actives(debut: date, cible: date) -> int:
    """
    Nombre de semaines non-freeze entre debut (inclus) et cible (inclus).
    Chaque semaine est identifiée par son lundi.
    """
    if cible < debut:
        return 0
    total = (cible - debut).days // 7 + 1  # semaines de debut à cible incluses

    # Semaines freeze qui chevauchent l'intervalle [debut, cible]
    overlap_debut = max(debut, FREEZE_DEBUT)
    overlap_fin   = min(cible, FREEZE_FIN - timedelta(weeks=1))  # dernière semaine freeze
    if overlap_fin >= overlap_debut:
        freeze = (overlap_fin - overlap_debut).days // 7 + 1
    else:
        freeze = 0

    return total - freeze


def contribution(date_debut_tournoi: date, semaine_cible: date) -> float:
    """
    Contribution d'un tournoi pour une semaine cible (un lundi).
    Basé sur le nombre de semaines actives (hors freeze) depuis semaine_debut.
    Le freeze prolonge la durée de vie des tournois (les semaines freeze ne comptent pas).
    - Semaines actives 1-52  : 1.0
    - Semaines actives 53-104 : 0.5
    - Au-delà de 104          : 0.0
    """
    debut = semaine_debut_tournoi(date_debut_tournoi)

    # Le tournoi compte à partir de la semaine APRÈS semaine_debut (strict)
    if semaine_cible <= debut:
        return 0.0

    n = semaines_actives(debut, semaine_cible)
    if n <= 52:
        return 1.0
    if n <= 104:
        return 0.5
    return 0.0


def tournois_actifs(db: Session, semaine_cible: date, regles: str):
    """
    Retourne [(tournoi, contribution)] pour tous les tournois actifs
    à semaine_cible, filtrés par règles (MCR ou RCR), hors WMC/WRC.
    """
    # Borne basse large : 104 semaines actives + 122 semaines freeze max
    limite_basse = semaine_cible - timedelta(weeks=104 + FREEZE_SEMAINES)

    tournois = (
        db.query(Tournoi)
        .filter(
            Tournoi.regles == regles,
            Tournoi.type_tournoi.notin_(["wmc", "wrc"]),
            Tournoi.date_debut >= limite_basse,
            Tournoi.date_debut != date(1900, 1, 1),
        )
        .all()
    )

    result = []
    for t in tournois:
        c = contribution(t.date_debut, semaine_cible)
        if c > 0:
            result.append((t, c))

    return result


import math


def _nb_tournois_part_a(n: int) -> int:
    """Nombre de tournois retenus pour la Part A : 5 + ceil(80% du reste)."""
    return 5 + math.ceil(0.8 * max(0, n - 5))


def _moyenne_ponderee(entries: list, manquants: int) -> float:
    """
    Moyenne pondérée sur entries = [(ranking, poids)] avec `manquants`
    tournois virtuels (ranking=0, poids=1) ajoutés au dénominateur.
    """
    numerateur   = sum(r * p for r, p in entries)
    denominateur = sum(p for _, p in entries) + manquants
    return numerateur / denominateur if denominateur > 0 else 0.0


def _resultats_actifs(db, joueur_id: str, actifs: dict):
    """Retourne les résultats du joueur dans les tournois actifs."""
    from models import Resultat
    return (
        db.query(Resultat)
        .filter(
            Resultat.joueur_id == joueur_id,
            Resultat.tournoi_id.in_(actifs.keys()),
        )
        .all()
    )


def _score_pour_joueur(resultats: list, actifs: dict) -> float:
    """Calcule le score à partir des résultats et du dict actifs déjà chargés."""
    n = len(resultats)
    garder = _nb_tournois_part_a(n)
    def poids(r): return actifs[r.tournoi_id][0].coefficient * actifs[r.tournoi_id][1]
    def date_t(r): return actifs[r.tournoi_id][0].date_debut
    # Part A : à ranking égal, garder le plus récent (date DESC)
    top_a = sorted(resultats, key=lambda r: (-r.ranking, -date_t(r).toordinal()))
    # Part B : à ranking égal, garder le plus lourd (poids DESC)
    top_b = sorted(resultats, key=lambda r: (-r.ranking, -poids(r)))

    def entries(subset):
        return [(r.ranking, actifs[r.tournoi_id][0].coefficient * actifs[r.tournoi_id][1])
                for r in subset]

    part_a = _moyenne_ponderee(entries(top_a[:garder]), max(0, garder - n))
    part_b = _moyenne_ponderee(entries(top_b[:4]),      max(0, 4 - n))
    return 0.5 * part_a + 0.5 * part_b


def calcul_score(db: Session, joueur_id: str, semaine_cible: date, regles: str) -> float | None:
    """
    Score final = 0.5 * Part A + 0.5 * Part B.
    Retourne None si le joueur a moins de 2 tournois actifs.
    """
    actifs = {t.id: (t, c) for t, c in tournois_actifs(db, semaine_cible, regles)}
    resultats = _resultats_actifs(db, joueur_id, actifs)
    if len(resultats) < 2:
        return None
    return _score_pour_joueur(resultats, actifs)


def classement(db: Session, semaine_cible: date, regles: str) -> list[dict]:
    """
    Retourne le classement complet pour une semaine et une discipline.
    Seuls les joueurs avec ≥2 tournois actifs apparaissent.
    Les tournois actifs sont calculés une seule fois.
    """
    from models import Resultat
    from sqlalchemy import func

    actifs = {t.id: (t, c) for t, c in tournois_actifs(db, semaine_cible, regles)}
    if not actifs:
        return []

    # Joueurs éligibles en une seule requête SQL
    eligibles = (
        db.query(Resultat.joueur_id)
        .filter(Resultat.tournoi_id.in_(actifs.keys()))
        .group_by(Resultat.joueur_id)
        .having(func.count(Resultat.tournoi_id) >= 2)
        .all()
    )
    joueur_ids = [row[0] for row in eligibles]

    # Charger tous les résultats actifs en une seule requête
    tous_resultats = (
        db.query(Resultat)
        .filter(
            Resultat.joueur_id.in_(joueur_ids),
            Resultat.tournoi_id.in_(actifs.keys()),
        )
        .all()
    )

    # Regrouper par joueur
    par_joueur: dict[str, list] = {jid: [] for jid in joueur_ids}
    for r in tous_resultats:
        par_joueur[r.joueur_id].append(r)

    # Calculer les scores + podiums dans les tournois actifs
    scores = []
    for joueur_id, resultats in par_joueur.items():
        score = _score_pour_joueur(resultats, actifs)
        scores.append({
            "joueur_id":   joueur_id,
            "score":       score,
            "nb_tournois": len(resultats),
            "nb_or":       sum(1 for r in resultats if r.position == 1),
            "nb_argent":   sum(1 for r in resultats if r.position == 2),
            "nb_bronze":   sum(1 for r in resultats if r.position == 3),
        })

    # Tri : score DESC, puis EMA ID ASC pour les égalités exactes
    scores.sort(key=lambda x: (-x["score"], x["joueur_id"]))
    for i, s in enumerate(scores):
        s["position"] = i + 1

    return scores

"""
Logique métier pour le calcul et le stockage du classement historique.
Appelable depuis un script CLI ou depuis l'application FastAPI.
"""

import threading
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models import Base, ClassementHistorique
from app.ranking import classement, lundi_semaine, FREEZE_DEBUT, FREEZE_FIN

Base.metadata.create_all(bind=engine)

with engine.connect() as conn:
    conn.execute(text("PRAGMA journal_mode=WAL"))

PREMIERE_SEMAINE = date(2005, 6, 27)

_write_lock = threading.Lock()


def semaines_entre(debut: date, fin: date):
    s = lundi_semaine(debut)
    while s <= fin:
        yield s
        s += timedelta(weeks=1)


def semaines_actives(semaines: list[date]) -> list[date]:
    return [s for s in semaines if not (FREEZE_DEBUT <= s < FREEZE_FIN)]


def semaines_manquantes(db: Session, regles: str) -> list[date]:
    existantes = {row[0] for row in db.query(ClassementHistorique.semaine)
                  .filter(ClassementHistorique.regles == regles).distinct().all()}
    fin = lundi_semaine(date.today())
    toutes = list(semaines_entre(PREMIERE_SEMAINE, fin))
    return [s for s in semaines_actives(toutes) if s not in existantes]


def calculer_semaine(semaine: date, regles: str) -> int:
    """Calcule et stocke le classement pour une semaine donnée. Retourne le nombre de joueurs classés."""
    db = SessionLocal()
    try:
        resultats = classement(db, semaine, regles)
        if not resultats:
            return 0

        rows = [
            {
                "semaine":     semaine,
                "regles":      regles,
                "joueur_id":   r["joueur_id"],
                "position":    r["position"],
                "score":       r["score"],
                "nb_tournois": r["nb_tournois"],
                "nb_or":       r["nb_or"],
                "nb_argent":   r["nb_argent"],
                "nb_bronze":   r["nb_bronze"],
            }
            for r in resultats
        ]

        with _write_lock:
            for row in rows:
                stmt = insert(ClassementHistorique).values(**row).on_conflict_do_update(
                    index_elements=["semaine", "regles", "joueur_id"],
                    set_={"position": row["position"], "score": row["score"],
                          "nb_tournois": row["nb_tournois"],
                          "nb_or": row["nb_or"], "nb_argent": row["nb_argent"], "nb_bronze": row["nb_bronze"]},
                )
                db.execute(stmt)
            db.commit()

        return len(resultats)
    finally:
        db.close()


def calculer_semaines(semaines: list[date], regles: str, workers: int = 4,
                      on_progress=None) -> None:
    """Calcule et stocke le classement pour une liste de semaines en parallèle.

    on_progress(semaine, n_joueurs, done, total) — callback optionnel appelé tous les 50 pas.
    """
    total = len(semaines)
    done = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(calculer_semaine, s, regles): s for s in semaines}
        for future in as_completed(futures):
            done += 1
            if on_progress and (done % 50 == 0 or done == total):
                on_progress(futures[future], future.result(), done, total)

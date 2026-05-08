"""
Calcule et stocke le classement historique semaine par semaine.

Usage :
  python3 calcul_historique.py                        # toutes les semaines depuis le 1er tournoi
  python3 calcul_historique.py --depuis 2022-01-03    # depuis une date précise (lundi)
  python3 calcul_historique.py --semaine 2026-04-27   # une seule semaine
  python3 calcul_historique.py --update               # uniquement les semaines manquantes
  python3 calcul_historique.py --workers 4            # paralléliser sur N threads
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
import threading
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from database import SessionLocal, engine
from models import Base, ClassementHistorique
from ranking import classement, lundi_semaine, FREEZE_DEBUT, FREEZE_FIN
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert

Base.metadata.create_all(bind=engine)

# Mode WAL pour permettre les lectures concurrentes sous SQLite
with engine.connect() as conn:
    conn.execute(__import__("sqlalchemy").text("PRAGMA journal_mode=WAL"))

PREMIERE_SEMAINE = date(2005, 6, 27)  # lundi avant le 1er tournoi MCR connu

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


def _calculer_et_ecrire(semaine: date, regles: str) -> int:
    """Calcule le classement dans son propre thread avec sa propre session."""
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--depuis", type=date.fromisoformat)
    parser.add_argument("--semaine", type=date.fromisoformat)
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--regles", choices=["MCR", "RCR", "all"], default="all")
    parser.add_argument("--workers", type=int, default=4, help="Nombre de threads (défaut: 4)")
    args = parser.parse_args()

    regles_list = ["MCR", "RCR"] if args.regles == "all" else [args.regles]

    for regles in regles_list:
        print(f"\n=== {regles} ===")

        db_tmp = SessionLocal()
        if args.semaine:
            semaines = [lundi_semaine(args.semaine)]
        elif args.update:
            semaines = semaines_manquantes(db_tmp, regles)
        elif args.depuis:
            fin = lundi_semaine(date.today())
            semaines = semaines_actives(list(semaines_entre(args.depuis, fin)))
        else:
            fin = lundi_semaine(date.today())
            semaines = semaines_actives(list(semaines_entre(PREMIERE_SEMAINE, fin)))
        db_tmp.close()

        total = len(semaines)
        print(f"{total} semaines à calculer (workers={args.workers})")

        done = 0
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_calculer_et_ecrire, s, regles): s for s in semaines}
            for future in as_completed(futures):
                done += 1
                if done % 50 == 0 or done == total:
                    semaine = futures[future]
                    n = future.result()
                    print(f"  {semaine}  {n:4} joueurs  ({done}/{total})", flush=True)

    print("\nTerminé.")


if __name__ == "__main__":
    main()

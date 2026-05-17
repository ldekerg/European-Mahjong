"""
CLI pour le calcul du classement historique.

Usage :
  python3 run_ranking_history.py                        # toutes les semaines
  python3 run_ranking_history.py --depuis 2022-01-03    # depuis une date précise (lundi)
  python3 run_ranking_history.py --semaine 2026-04-27   # une seule semaine
  python3 run_ranking_history.py --update               # uniquement les semaines manquantes
  python3 run_ranking_history.py --workers 8            # paralléliser sur N threads
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
from datetime import date

from app.database import SessionLocal
from app.ranking import lundi_semaine
from app.ranking_history import (
    PREMIERE_SEMAINE,
    semaines_entre,
    semaines_actives,
    semaines_manquantes,
    calculer_semaines,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--depuis",  type=date.fromisoformat)
    parser.add_argument("--semaine", type=date.fromisoformat)
    parser.add_argument("--update",  action="store_true")
    parser.add_argument("--regles",  choices=["MCR", "RCR", "all"], default="all")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    regles_list = ["MCR", "RCR"] if args.regles == "all" else [args.regles]

    for regles in regles_list:
        print(f"\n=== {regles} ===")

        db = SessionLocal()
        if args.semaine:
            semaines = [lundi_semaine(args.semaine)]
        elif args.update:
            semaines = semaines_manquantes(db, regles)
        elif args.depuis:
            fin = lundi_semaine(date.today())
            semaines = semaines_actives(list(semaines_entre(args.depuis, fin)))
        else:
            fin = lundi_semaine(date.today())
            semaines = semaines_actives(list(semaines_entre(PREMIERE_SEMAINE, fin)))
        db.close()

        print(f"{len(semaines)} semaines à calculer (workers={args.workers})")

        def progress(semaine, n, done, total):
            print(f"  {semaine}  {n:4} joueurs  ({done}/{total})", flush=True)

        calculer_semaines(semaines, regles, workers=args.workers, on_progress=progress)

    print("\nTerminé.")


if __name__ == "__main__":
    main()

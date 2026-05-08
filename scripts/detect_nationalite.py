"""
Détecte les changements de nationalité à partir des résultats par tournoi.
Usage : python3 detect_nationalite.py [--dry-run]
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
import sqlite3

DB = os.path.join(os.path.dirname(__file__), "..", "data", "ema_ranking.db")


def detect():
    con = sqlite3.connect(DB)
    # Pour chaque joueur, récupérer les nationalités distinctes par date
    rows = con.execute("""
        SELECT r.joueur_id, t.date_debut, r.nationalite
        FROM resultats r
        JOIN tournois t ON t.id = r.tournoi_id
        WHERE r.nationalite IS NOT NULL AND r.nationalite != ''
          AND t.date_debut != '1900-01-01'
        ORDER BY r.joueur_id, t.date_debut
    """).fetchall()

    changements = {}
    joueur_hist = {}
    for joueur_id, date, nat in rows:
        if joueur_id not in joueur_hist:
            joueur_hist[joueur_id] = nat
        elif joueur_hist[joueur_id] != nat:
            if joueur_id not in changements:
                changements[joueur_id] = []
            # Nouvelle nationalité détectée
            if not changements[joueur_id] or changements[joueur_id][-1]["vers"] != nat:
                changements[joueur_id].append({
                    "de": joueur_hist[joueur_id],
                    "vers": nat,
                    "date": date,
                })
            joueur_hist[joueur_id] = nat

    con.close()
    return changements


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    changements = detect()
    print(f"{len(changements)} joueurs avec changement de nationalité :\n")
    for joueur_id, hist in sorted(changements.items()):
        for c in hist:
            print(f"  {joueur_id}: {c['de']} → {c['vers']} à partir du {c['date']}")

    if not args.dry_run:
        # Sauvegarder dans la table
        con = sqlite3.connect(DB)
        try:
            con.execute("""CREATE TABLE IF NOT EXISTS changements_nationalite (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                joueur_id TEXT NOT NULL,
                nationalite_avant TEXT NOT NULL,
                nationalite_apres TEXT NOT NULL,
                date_changement TEXT NOT NULL,
                UNIQUE(joueur_id, date_changement)
            )""")
        except Exception:
            pass
        for joueur_id, hist in changements.items():
            for c in hist:
                con.execute("""INSERT OR IGNORE INTO changements_nationalite
                    (joueur_id, nationalite_avant, nationalite_apres, date_changement)
                    VALUES (?, ?, ?, ?)""",
                    (joueur_id, c["de"], c["vers"], c["date"]))
        con.commit()
        total = con.execute("SELECT COUNT(*) FROM changements_nationalite").fetchone()[0]
        con.close()
        print(f"\n{total} changements enregistrés.")


if __name__ == "__main__":
    main()

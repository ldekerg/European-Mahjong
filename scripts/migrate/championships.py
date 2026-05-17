"""
Migration: creates the serie_championnat, championnat, championnat_tournoi tables.
"""

import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ema_ranking.db")
con = sqlite3.connect(DB_PATH)

for sql in [
    """CREATE TABLE IF NOT EXISTS serie_championnat (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        slug        TEXT    NOT NULL UNIQUE,
        nom         TEXT    NOT NULL,
        regles      TEXT    NOT NULL,
        pays        TEXT    NOT NULL,
        description TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS championnat (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        serie_id INTEGER NOT NULL REFERENCES serie_championnat(id),
        annee    INTEGER NOT NULL,
        nom      TEXT,
        formule  TEXT NOT NULL DEFAULT 'moyenne_n_meilleurs',
        params   TEXT NOT NULL DEFAULT '{"n": 3}'
    )""",
    """CREATE TABLE IF NOT EXISTS championnat_tournoi (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        championnat_id INTEGER NOT NULL REFERENCES championnat(id),
        tournoi_id     INTEGER NOT NULL REFERENCES tournois(id),
        UNIQUE(championnat_id, tournoi_id)
    )""",
]:
    try:
        con.execute(sql)
        print(f"OK : {sql[:60]}...")
    except sqlite3.OperationalError as e:
        print(f"(ignored) {e}")

con.commit()
con.close()
print("\nChampionships migration complete.")

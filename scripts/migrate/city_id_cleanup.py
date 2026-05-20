"""
Migration: consolidate city data into cities table.
- Create missing cities for Cambridge and Guildford (GB)
- Leave the cruise liner tournament with city_id = NULL
- Drop deprecated columns city (string), latitude, longitude from tournaments
  (SQLite doesn't support DROP COLUMN before 3.35 — we recreate the table)
"""

import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ema_ranking.db")
con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row

# -- 1. Create missing cities and link tournaments ---------------------------

MISSING = [
    # (tournament_id, city_name, country, lat, lon)  — cruise liner gets NULL city_id
    (877, "Cambridge",  "GB", 52.2053,  0.1218),
    (891, "Guildford",  "GB", 51.2362, -0.5704),
]

for tid, name, country, lat, lon in MISSING:
    # Insert city if not already present
    existing = con.execute(
        "SELECT id FROM cities WHERE name=? AND country=?", (name, country)
    ).fetchone()
    if existing:
        city_id = existing["id"]
        print(f"City already exists: {name} ({country}) → id={city_id}")
    else:
        cur = con.execute(
            "INSERT INTO cities (name, country, latitude, longitude) VALUES (?,?,?,?)",
            (name, country, lat, lon),
        )
        city_id = cur.lastrowid
        print(f"Created city: {name} ({country}) → id={city_id}")

    con.execute("UPDATE tournaments SET city_id=? WHERE id=?", (city_id, tid))
    print(f"  Linked tournament {tid} → city_id={city_id}")

# Cruise liner (id=910) — leave city_id NULL intentionally
print("Tournament 910 (cruise liner): city_id left NULL")

con.commit()

# -- 2. Verify coverage -----------------------------------------------------
total = con.execute("SELECT COUNT(*) FROM tournaments").fetchone()[0]
linked = con.execute("SELECT COUNT(*) FROM tournaments WHERE city_id IS NOT NULL").fetchone()[0]
print(f"\nCoverage: {linked}/{total} tournaments have city_id")

# -- 3. Drop deprecated columns from tournaments ----------------------------
# SQLite < 3.35 doesn't support DROP COLUMN — recreate the table

print("\nRecreating tournaments table without deprecated columns...")

con.executescript("""
PRAGMA foreign_keys = OFF;

CREATE TABLE tournaments_new (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ema_id           INTEGER,
    rules            TEXT    NOT NULL,
    name             TEXT    NOT NULL,
    city_id          INTEGER REFERENCES cities(id),
    country          TEXT    NOT NULL,
    start_date       DATE    NOT NULL,
    end_date         DATE    NOT NULL,
    nb_players       INTEGER NOT NULL,
    coefficient      REAL    NOT NULL,
    tournament_type  TEXT    NOT NULL DEFAULT 'normal',
    status           TEXT    NOT NULL DEFAULT 'actif',
    approval         TEXT,
    website          TEXT
);

INSERT INTO tournaments_new
    (id, ema_id, rules, name, city_id, country,
     start_date, end_date, nb_players, coefficient,
     tournament_type, status, approval, website)
SELECT
    id, ema_id, rules, name, city_id, country,
    start_date, end_date, nb_players, coefficient,
    tournament_type, status, approval, website
FROM tournaments;

DROP TABLE tournaments;
ALTER TABLE tournaments_new RENAME TO tournaments;

-- Recreate indexes
CREATE UNIQUE INDEX IF NOT EXISTS uq_tournoi_ema_regles
    ON tournaments(ema_id, rules) WHERE ema_id IS NOT NULL;

PRAGMA foreign_keys = ON;
""")

con.commit()
print("Done.")

# -- 4. Final check ---------------------------------------------------------
cols = [r[1] for r in con.execute("PRAGMA table_info(tournaments)").fetchall()]
print(f"\ntournaments columns: {cols}")
assert "city" not in cols, "ERROR: old 'city' column still present"
assert "latitude" not in cols, "ERROR: old 'latitude' column still present"
assert "longitude" not in cols, "ERROR: old 'longitude' column still present"
assert "city_id" in cols, "ERROR: city_id column missing"
print("All checks passed.")

con.close()

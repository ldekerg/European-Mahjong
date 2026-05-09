"""
Migration : crée la table villes, migre les coordonnées existantes depuis tournois,
ajoute la colonne ville_id dans tournois.
"""

import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ema_ranking.db")
con = sqlite3.connect(DB_PATH)

# 1. Créer la table villes
con.execute("""
    CREATE TABLE IF NOT EXISTS villes (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        nom       TEXT NOT NULL,
        pays      TEXT NOT NULL,
        latitude  REAL NOT NULL,
        longitude REAL NOT NULL,
        UNIQUE(nom, pays)
    )
""")
print("Table villes créée.")

# 2. Ajouter ville_id dans tournois
try:
    con.execute("ALTER TABLE tournois ADD COLUMN ville_id INTEGER REFERENCES villes(id)")
    print("Colonne ville_id ajoutée dans tournois.")
except sqlite3.OperationalError as e:
    print(f"(ignoré) {e}")

# 3. Migrer les coordonnées existantes depuis tournois → villes
rows = con.execute("""
    SELECT DISTINCT lieu, pays, latitude, longitude
    FROM tournois
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND lieu != ''
""").fetchall()

print(f"\n{len(rows)} villes à migrer depuis tournois...")
for lieu, pays, lat, lon in rows:
    try:
        con.execute(
            "INSERT OR IGNORE INTO villes (nom, pays, latitude, longitude) VALUES (?, ?, ?, ?)",
            (lieu, pays, lat, lon)
        )
    except Exception as e:
        print(f"  WARN {lieu}/{pays}: {e}")

# 4. Relier tournois → villes via ville_id
updated = con.execute("""
    UPDATE tournois SET ville_id = (
        SELECT v.id FROM villes v
        WHERE v.nom = tournois.lieu AND v.pays = tournois.pays
    )
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL
""").rowcount
print(f"{updated} tournois liés à une ville.")

con.commit()

nb_villes = con.execute("SELECT COUNT(*) FROM villes").fetchone()[0]
print(f"\nTotal villes en base : {nb_villes}")
print("Migration villes terminée.")
con.close()

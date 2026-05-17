"""
Migration: creates the cities table, migrates existing coordinates from tournois,
adds the city_id column in tournois.
"""

import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ema_ranking.db")
con = sqlite3.connect(DB_PATH)

# 1. Create the cities table
con.execute("""
    CREATE TABLE IF NOT EXISTS cities (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        name      TEXT NOT NULL,
        country   TEXT NOT NULL,
        latitude  REAL NOT NULL,
        longitude REAL NOT NULL,
        UNIQUE(name, country)
    )
""")
print("Table cities created.")

# 2. Add city_id in tournois
try:
    con.execute("ALTER TABLE tournaments ADD COLUMN city_id INTEGER REFERENCES cities(id)")
    print("Column city_id added to tournois.")
except sqlite3.OperationalError as e:
    print(f"(ignored) {e}")

# 3. Migrate existing coordinates from tournois → cities
rows = con.execute("""
    SELECT DISTINCT city, country, latitude, longitude
    FROM tournaments
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND city != ''
""").fetchall()

print(f"\n{len(rows)} cities to migrate from tournois...")
for city_name, country_code, lat, lon in rows:
    try:
        con.execute(
            "INSERT OR IGNORE INTO cities (name, country, latitude, longitude) VALUES (?, ?, ?, ?)",
            (city_name, country_code, lat, lon)
        )
    except Exception as e:
        print(f"  WARN {city_name}/{country_code}: {e}")

# 4. Link tournois → cities via city_id
updated = con.execute("""
    UPDATE tournaments SET city_id = (
        SELECT v.id FROM cities v
        WHERE v.name = tournaments.city AND v.country = tournaments.country
    )
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL
""").rowcount
print(f"{updated} tournaments linked to a city.")

con.commit()

nb_villes = con.execute("SELECT COUNT(*) FROM cities").fetchone()[0]
print(f"\nTotal cities in database: {nb_villes}")
print("Cities migration complete.")
con.close()

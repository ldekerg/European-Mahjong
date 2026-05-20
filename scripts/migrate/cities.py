"""
Migration: cities table and city_id column.
Already applied — this script is now a no-op kept for compatibility with update_weekly.sh.
The full migration was run via scripts/migrate/city_id_cleanup.py.
"""
import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ema_ranking.db")
con = sqlite3.connect(DB_PATH)

# Ensure cities table exists (idempotent)
con.execute("""
    CREATE TABLE IF NOT EXISTS cities (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        name      TEXT NOT NULL,
        country   TEXT NOT NULL,
        latitude  REAL NOT NULL DEFAULT 0.0,
        longitude REAL NOT NULL DEFAULT 0.0,
        UNIQUE(name, country)
    )
""")

# Ensure city_id column exists on tournaments (idempotent)
try:
    con.execute("ALTER TABLE tournaments ADD COLUMN city_id INTEGER REFERENCES cities(id)")
    print("Column city_id added to tournaments.")
except sqlite3.OperationalError:
    pass  # already exists

con.commit()
con.close()
print("Cities migration: OK (no-op if already applied).")

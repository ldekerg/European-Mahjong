"""Create referees table."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.database import engine
from sqlalchemy import text

with engine.begin() as conn:
    cols = [r[1] for r in conn.execute(text("PRAGMA table_info(referees)"))]
    if not cols:
        conn.execute(text("""
            CREATE TABLE referees (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT NOT NULL,
                country          TEXT NOT NULL,
                rules            TEXT NOT NULL,
                seminar_year     INTEGER,
                seminar_location TEXT,
                seminar_city_id  INTEGER REFERENCES cities(id),
                player_id        TEXT REFERENCES players(id)
            )
        """))
        print("Created table: referees")
    else:
        print("Table already exists: referees")

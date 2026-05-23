"""
Create tournament_referees table.
Run with: python3 scripts/migrate/tournament_referees.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.database import engine
from sqlalchemy import text

with engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS tournament_referees (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL REFERENCES tournaments(id),
            referee_id    INTEGER REFERENCES referees(id),
            player_id     TEXT    REFERENCES players(id),
            name          TEXT    NOT NULL
        )
    """))
    print("  Created table: tournament_referees")

print("Done.")

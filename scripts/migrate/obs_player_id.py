"""
Add obs_player_id column to tournaments table.
Run with: python3 scripts/migrate/obs_player_id.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.database import engine
from sqlalchemy import text

with engine.begin() as conn:
    try:
        conn.execute(text('ALTER TABLE tournaments ADD COLUMN "obs_player_id" TEXT REFERENCES players(id)'))
        print("  Added column: obs_player_id")
    except Exception as e:
        print(f"  obs_player_id: skipped ({e})")

print("Done.")

"""Add registration_open column to tournaments table."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    cols = [r[1] for r in conn.execute(text("PRAGMA table_info(tournaments)"))]
    if "registration_open" not in cols:
        conn.execute(text("ALTER TABLE tournaments ADD COLUMN registration_open DATE"))
        conn.commit()
        print("Added column: registration_open")
    else:
        print("Column already exists: registration_open")

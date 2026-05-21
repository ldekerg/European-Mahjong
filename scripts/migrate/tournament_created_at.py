"""Migration: add created_at column to tournaments table."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.database import engine
from sqlalchemy import text

if __name__ == "__main__":
    with engine.connect() as conn:
        # Add column — NULL for existing rows (unknown creation date)
        try:
            conn.execute(text("ALTER TABLE tournaments ADD COLUMN created_at DATETIME"))
            conn.commit()
            print("Column created_at added to tournaments.")
        except Exception as e:
            if "duplicate column" in str(e).lower():
                print("Column already exists, skipping.")
            else:
                raise

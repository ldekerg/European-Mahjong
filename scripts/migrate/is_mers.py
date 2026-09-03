"""Migration: add is_mers column to tournaments table.

Splits the two meanings ema_id used to carry. It stays the EMA number (used to
scrape TR_<n>.html); is_mers becomes the "official MERS tournament" flag that
makes a tournament eligible for the ranking.

Backfill keeps behaviour identical: every row that had an ema_id was, by the old
predicate, an official tournament.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.database import engine
from sqlalchemy import text

if __name__ == "__main__":
    with engine.begin() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE tournaments ADD COLUMN is_mers BOOLEAN NOT NULL DEFAULT 0"
            ))
            print("Column is_mers added to tournaments.")
        except Exception as e:
            if "duplicate column" in str(e).lower():
                print("Column already exists, skipping.")
            else:
                raise

        # Backfill: ema_id IS NOT NULL was the old "official tournament" predicate.
        result = conn.execute(text(
            "UPDATE tournaments SET is_mers=1 WHERE ema_id IS NOT NULL AND is_mers=0"
        ))
        print(f"Rows marked is_mers=1: {result.rowcount}")

        # Safety check: the new flag must match the old predicate exactly.
        diff = conn.execute(text(
            "SELECT COUNT(*) FROM tournaments WHERE (ema_id IS NOT NULL) <> (is_mers=1)"
        )).scalar()
        if diff:
            raise SystemExit(f"ABORT: {diff} rows diverge from the old predicate.")
        print("Check OK: is_mers matches the previous ema_id predicate on every row.")

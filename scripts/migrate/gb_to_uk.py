"""
Rename country code GB → UK in all database tables.
Run with: python3 scripts/migrate/gb_to_uk.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.database import engine
from sqlalchemy import text

UPDATES = [
    ("players",          "nationality"),
    ("results",          "nationality"),
    ("anonymous_results","nationality"),
    ("cities",           "country"),
    ("tournaments",      "country"),
    ("referees",         "country"),
]

with engine.begin() as conn:
    for table, col in UPDATES:
        try:
            result = conn.execute(
                text(f'UPDATE "{table}" SET "{col}" = \'UK\' WHERE "{col}" = \'GB\'')
            )
            print(f"  {table}.{col}: {result.rowcount} rows updated")
        except Exception as e:
            print(f"  {table}.{col}: skipped ({e})")

print("Done.")

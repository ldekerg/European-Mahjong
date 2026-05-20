"""
Creates cities entries for tournaments that have no city_id yet.
Inserts with lat=0/lon=0 so geocode.py can then resolve coordinates.
Run before geocode.py in the weekly update pipeline.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sqlite3

DB = os.path.join(os.path.dirname(__file__), "..", "data", "ema_ranking.db")
con = sqlite3.connect(DB)

# Find tournaments with a non-empty city string in their EMA page data,
# but no city_id yet. We reconstruct city name from the EMA data stored
# in the tournaments table — but since we dropped the city column, we
# must rely on a different approach: check tournaments imported recently
# (ema_id not null) without a city_id.
#
# The importer now calls _resolve_city_id which returns None if the city
# doesn't exist yet. So we need to re-link after cities are created.
#
# Strategy: this script is intentionally simple — it just reports
# orphaned tournaments so the operator can add cities manually or via geocode.

rows = con.execute("""
    SELECT id, ema_id, rules, name, country
    FROM tournaments
    WHERE ema_id IS NOT NULL AND city_id IS NULL
    ORDER BY ema_id DESC
    LIMIT 50
""").fetchall()

if rows:
    print(f"{len(rows)} tournaments without city_id (most recent):")
    for tid, eid, rules, name, country in rows:
        print(f"  [{rules}_{eid}] {name[:50]} ({country})")
else:
    print("All EMA tournaments have a city_id. OK.")

con.close()

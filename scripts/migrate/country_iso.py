"""
Migration: normalize country values to ISO 2-letter codes in cities and tournaments.
Handles duplicate cities that arise from the normalization (e.g. 'France'→'FR' clashes with existing 'FR').
"""

import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ema_ranking.db")

NAME_TO_ISO = {
    "austria":                "AT",
    "belarus":                "BY",
    "belgium":                "BE",
    "canada":                 "CA",
    "china":                  "CN",
    "czech republic":         "CZ",
    "denmark":                "DK",
    "finland":                "FI",
    "fr":                     "FR",
    "france":                 "FR",
    "gb":                     "GB",
    "germany":                "DE",
    "great britain":          "GB",
    "hungary":                "HU",
    "ireland":                "IE",
    "italy":                  "IT",
    "japan":                  "JP",
    "netherlands":            "NL",
    "norway":                 "NO",
    "poland":                 "PL",
    "portugal":               "PT",
    "romania":                "RO",
    "russia":                 "RU",
    "slovakia":               "SK",
    "south korea":            "KR",
    "spain":                  "ES",
    "sweden":                 "SE",
    "switzerland":            "CH",
    "ukraine":                "UA",
    "united states":          "US",
    "farnham, great britain": "GB",
    # Special — leave country unchanged, city_id → NULL on tournaments
    "cruise liner mariner of the seas": "__SKIP__",
}

con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row

# -- Step 1: fix tournaments.country (no unique constraint there) -----------
print("=== Normalizing tournaments.country ===")
rows = con.execute("SELECT DISTINCT country FROM tournaments").fetchall()
for row in rows:
    original = row["country"]
    iso = NAME_TO_ISO.get(original.strip().lower())
    if iso and iso != "__SKIP__" and iso != original:
        cur = con.execute("UPDATE tournaments SET country=? WHERE country=?", (iso, original))
        print(f"  {original!r} → {iso!r}  ({cur.rowcount} rows)")
con.commit()

# -- Step 2: normalize cities.country with duplicate merging ----------------
print("\n=== Normalizing cities.country (with duplicate merging) ===")

city_rows = con.execute("SELECT id, name, country FROM cities ORDER BY id").fetchall()

for city in city_rows:
    original = city["country"]
    iso = NAME_TO_ISO.get(original.strip().lower())
    if not iso or iso == "__SKIP__" or iso == original:
        continue

    # Check if a city with the same name already exists under the target ISO code
    existing = con.execute(
        "SELECT id FROM cities WHERE name=? AND country=?",
        (city["name"], iso)
    ).fetchone()

    if existing:
        # Merge: reroute all tournaments pointing to this city → existing city
        keep_id = existing["id"]
        drop_id = city["id"]
        con.execute("UPDATE tournaments SET city_id=? WHERE city_id=?", (keep_id, drop_id))
        con.execute("DELETE FROM cities WHERE id=?", (drop_id,))
        print(f"  Merged city {drop_id} ({city['name']}, {original!r}) → {keep_id} ({iso!r})")
    else:
        con.execute("UPDATE cities SET country=? WHERE id=?", (iso, city["id"]))
        print(f"  Updated city {city['id']} ({city['name']}): {original!r} → {iso!r}")

con.commit()

# -- Final check ------------------------------------------------------------
print("\n=== Final country values ===")
for table in ("cities", "tournaments"):
    rows = con.execute(
        f"SELECT DISTINCT country, COUNT(*) as nb FROM {table} GROUP BY country ORDER BY country"
    ).fetchall()
    print(f"\n{table}:")
    for r in rows:
        print(f"  {r['country']!r:10} {r['nb']}")

con.close()
print("\nDone.")

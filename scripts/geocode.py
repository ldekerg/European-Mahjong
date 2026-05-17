"""
Géocode les villes des tournois via Nominatim (OpenStreetMap).
Usage : python3 geocode.py [--dry-run]
"""
import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
import urllib.request
import urllib.parse
import sqlite3

DB = os.path.join(os.path.dirname(__file__), "..", "data", "ema_ranking.db")
HEADERS = {"User-Agent": "EMA-Ranking-App/1.0 (mahjong ranking project)"}

# Corrections manuelles pour les villes ambiguës ou mal résolues par Nominatim
CORRECTIONS: dict[tuple[str, str], tuple[float, float]] = {
    ("Saint-Denis (Réunion)", "France"): (-20.8823, 55.4504),
    ("Saint-Pierre (Réunion)", "France"): (-21.3393, 55.4781),
}


def nominatim(city_name: str, country_code: str) -> tuple[float, float] | None:
    query = f"{city_name}, {country_code}" if country_code else city_name
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "q": query, "format": "json", "limit": 1,
    })
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            results = json.loads(r.read())
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        print(f"  Erreur Nominatim pour '{query}': {e}")
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    con = sqlite3.connect(DB)

    # Villes uniques sans coordonnées
    rows = con.execute("""
        SELECT DISTINCT city, country FROM tournaments
        WHERE city != '' AND latitude IS NULL
        ORDER BY country, city
    """).fetchall()

    print(f"{len(rows)} cities to geocode")
    ok = 0
    for city_name, country_code in rows:
        coords = CORRECTIONS.get((city_name, country_code)) or nominatim(city_name, country_code)
        if coords:
            lat, lon = coords
            print(f"  ✓ {city_name}, {country_code} → {lat:.4f}, {lon:.4f}")
            if not args.dry_run:
                con.execute(
                    "UPDATE tournaments SET latitude=?, longitude=? WHERE city=? AND country=?",
                    (lat, lon, city_name, country_code)
                )
            ok += 1
        else:
            print(f"  ✗ {city_name}, {country_code}")
        time.sleep(1.1)  # Respecter le rate limit Nominatim (1 req/s)

    if not args.dry_run:
        con.commit()
    print(f"\n{ok}/{len(rows)} cities geocoded.")
    con.close()


if __name__ == "__main__":
    main()

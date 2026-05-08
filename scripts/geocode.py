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


def nominatim(lieu: str, pays: str) -> tuple[float, float] | None:
    query = f"{lieu}, {pays}" if pays else lieu
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
        SELECT DISTINCT lieu, pays FROM tournois
        WHERE lieu != '' AND latitude IS NULL
        ORDER BY pays, lieu
    """).fetchall()

    print(f"{len(rows)} villes à géocoder")
    ok = 0
    for lieu, pays in rows:
        coords = CORRECTIONS.get((lieu, pays)) or nominatim(lieu, pays)
        if coords:
            lat, lon = coords
            print(f"  ✓ {lieu}, {pays} → {lat:.4f}, {lon:.4f}")
            if not args.dry_run:
                con.execute(
                    "UPDATE tournois SET latitude=?, longitude=? WHERE lieu=? AND pays=?",
                    (lat, lon, lieu, pays)
                )
            ok += 1
        else:
            print(f"  ✗ {lieu}, {pays}")
        time.sleep(1.1)  # Respecter le rate limit Nominatim (1 req/s)

    if not args.dry_run:
        con.commit()
    print(f"\n{ok}/{len(rows)} villes géocodées.")
    con.close()


if __name__ == "__main__":
    main()

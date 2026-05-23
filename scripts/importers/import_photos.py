"""
Download player photos from mahjong-europe.org.
Saves to app/static/photos/{player_id}.jpg
Skips placeholder (Vide.jpg = 5682 bytes) and already-downloaded photos.

Run with: python3 scripts/importers/import_photos.py [--force] [--player ID]
"""
import sys, os, time, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import requests
from app.database import SessionLocal
from app.models import Player

BASE_URL = "http://mahjong-europe.org/ranking/Players/photo/{}.jpg"
VIDE_SIZE = 5682  # bytes — placeholder image size
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "../../app/static/photos")

os.makedirs(OUTPUT_DIR, exist_ok=True)


def download_photo(player_id: str, force: bool = False) -> str:
    """Returns 'saved', 'skipped_placeholder', 'already_exists', 'error'"""
    dest = os.path.join(OUTPUT_DIR, f"{player_id}.jpg")
    if os.path.exists(dest) and not force:
        return "already_exists"

    url = BASE_URL.format(player_id)
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return "error"
        if len(r.content) <= VIDE_SIZE:
            return "skipped_placeholder"
        with open(dest, "wb") as f:
            f.write(r.content)
        return "saved"
    except Exception as e:
        print(f"  Error {player_id}: {e}")
        return "error"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Re-download even if file exists")
    parser.add_argument("--player", help="Download a single player ID")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.player:
            players = db.query(Player).filter(Player.id == args.player).all()
        else:
            players = db.query(Player).order_by(Player.id).all()
    finally:
        db.close()

    counts = {"saved": 0, "skipped_placeholder": 0, "already_exists": 0, "error": 0}

    for i, player in enumerate(players):
        result = download_photo(player.id, force=args.force)
        counts[result] += 1
        if result == "saved":
            print(f"  [{i+1}/{len(players)}] {player.id} {player.last_name} — saved")
        elif result == "error":
            print(f"  [{i+1}/{len(players)}] {player.id} — error")
        time.sleep(0.05)  # be gentle with the server

    print(f"\nDone: {counts['saved']} saved, {counts['skipped_placeholder']} no photo, "
          f"{counts['already_exists']} already present, {counts['error']} errors")


if __name__ == "__main__":
    main()

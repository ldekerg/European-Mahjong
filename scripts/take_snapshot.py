"""Take a DB snapshot. Usage: python scripts/take_snapshot.py [label]"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import shutil
from pathlib import Path
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/ema_ranking.db")
DB_PATH      = Path(DATABASE_URL.replace("sqlite:///", ""))
BACKUPS_DIR  = Path(os.environ.get("BACKUPS_DIR", "./backups"))

if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "update_weekly"
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    slug = label.replace(" ", "_")[:40]
    dest = BACKUPS_DIR / f"ranking_{ts}_{slug}.db"
    shutil.copy2(DB_PATH, dest)
    # Keep only the 30 most recent backups
    backups = sorted(BACKUPS_DIR.glob("ranking_*.db"))
    for old in backups[:-30]:
        old.unlink(missing_ok=True)
    print(f"Snapshot: {dest}")

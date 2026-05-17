#!/bin/bash
# Import complet des championnats régionaux (Golden League + Rhône-Alpes)
# À lancer une fois pour initialiser la DB sur le serveur

set -e
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR/scripts"

if [ -f "$APP_DIR/venv/bin/python" ]; then
    PYTHON=$APP_DIR/venv/bin/python
else
    PYTHON=python3
fi

export DATABASE_URL="sqlite:///$APP_DIR/data/ema_ranking.db"
export PYTHONPATH="$APP_DIR"

echo "=== Import championnats — $(date) ==="

echo "--- Migration tables championnats ---"
$PYTHON migrate/championships.py

echo "--- Golden League MCR ---"
$PYTHON importers/golden_league.py

echo "--- Rhône-Alpes MCR 2023-2024 ---"
$PYTHON importers/rhone_alpes_2324.py

echo "--- Rhône-Alpes MCR 2024-2025 ---"
$PYTHON importers/rhone_alpes_2425.py

echo "--- Rhône-Alpes MCR (courant) ---"
$PYTHON importers/rhone_alpes.py

echo "=== Terminé — $(date) ==="

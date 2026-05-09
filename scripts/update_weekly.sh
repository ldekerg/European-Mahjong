#!/bin/bash
# Mise à jour hebdomadaire des tournois EMA (MCR + RCR)
# À lancer via cron chaque lundi matin

set -e
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR/scripts"
if [ -f "$APP_DIR/venv/bin/python" ]; then
    PYTHON=$APP_DIR/venv/bin/python
else
    PYTHON=python3
fi
export DATABASE_URL="sqlite:///$APP_DIR/data/ema_ranking.db"
LOG=$APP_DIR/logs/update_$(date +%Y%m%d).log

mkdir -p "$(dirname "$LOG")"
exec >> "$LOG" 2>&1

echo "=== Mise à jour hebdomadaire EMA — $(date) ==="

# Importe les 30 derniers IDs MCR et RCR (couvre les nouveaux tournois)
echo "--- MCR : 30 derniers IDs ---"
$PYTHON import_ema.py --start 425 --end 454 
echo "--- RCR : 30 derniers IDs ---"
$PYTHON import_ema.py --prefix TR_RCR --start 383 --end 412 
echo "--- Calendrier ---"
$PYTHON import_calendar.py

echo "--- Import tournois passés (calendrier → résultats) ---"
$PYTHON import_nouveaux.py

echo "--- Migrations ---"
$PYTHON migrate.py
$PYTHON migrate_villes.py
$PYTHON migrate_championnats.py

echo "--- Géolocalisation des nouvelles villes ---"
$PYTHON geocode.py

echo "--- Recalcul classement (semaines manquantes) ---"
$PYTHON calcul_historique.py --update

echo "=== Terminé — $(date) ==="

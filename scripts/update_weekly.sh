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

# Calcule dynamiquement les IDs à partir du dernier en base + 10 de marge
MCR_MAX=$($PYTHON -c "
import sys, os; sys.path.insert(0, '..')
from database import SessionLocal; from models import Tournoi
db = SessionLocal()
t = db.query(Tournoi).filter(Tournoi.regles=='MCR', Tournoi.ema_id < 1000000).order_by(Tournoi.ema_id.desc()).first()
print(t.ema_id if t else 0)
")
RCR_MAX=$($PYTHON -c "
import sys, os; sys.path.insert(0, '..')
from database import SessionLocal; from models import Tournoi
db = SessionLocal()
t = db.query(Tournoi).filter(Tournoi.regles=='RCR', Tournoi.ema_id < 1000000).order_by(Tournoi.ema_id.desc()).first()
print(t.ema_id if t else 0)
")
MCR_START=$((MCR_MAX + 1))
MCR_END=$((MCR_MAX + 10))
RCR_START=$((RCR_MAX + 1))
RCR_END=$((RCR_MAX + 10))

echo "--- MCR : IDs $MCR_START à $MCR_END ---"
$PYTHON import_ema.py --start $MCR_START --end $MCR_END
echo "--- RCR : IDs $RCR_START à $RCR_END ---"
$PYTHON import_ema.py --prefix TR_RCR --start $RCR_START --end $RCR_END
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

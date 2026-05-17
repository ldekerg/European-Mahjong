#!/bin/bash
# Import complet de tous les tournois EMA (MCR + RCR)
# Usage : ./import_all.sh [--delay 0.3]

set -e
cd "$(dirname "$0")/.."
DELAY=${2:-0.3}
PYTHON=python3

echo "=== Import EMA complet ==="
echo "Délai : ${DELAY}s entre requêtes"
echo ""

# IDs spéciaux à zéro-padding (01-09)
echo "--- MCR : IDs 01-09 ---"
$PYTHON importers/ema.py --ids 01 02 03 04 05 06 07 08 09 --delay $DELAY

echo "--- RCR : IDs 01-09 ---"
$PYTHON importers/ema.py --prefix TR_RCR --ids 01 02 03 04 05 06 07 08 09 --delay $DELAY

# Plage principale
echo "--- MCR : IDs 10-453 ---"
$PYTHON importers/ema.py --start 10 --end 453 --delay $DELAY

echo "--- RCR : IDs 10-411 ---"
$PYTHON importers/ema.py --prefix TR_RCR --start 10 --end 411 --delay $DELAY

# WMC / WRC (IDs 1000001+)
echo "--- WMC : IDs 1000001-1000007 ---"
$PYTHON importers/ema.py --ids 1000001 1000002 1000003 1000004 1000005 1000006 1000007 --delay $DELAY

echo "--- WRC : IDs 1000001-1000004 ---"
$PYTHON importers/ema.py --prefix TR_RCR --ids 1000001 1000002 1000003 1000004 --delay $DELAY

# Reclassifier les tournois et recalculer les statuts joueurs
echo ""
echo "--- Migration (type_tournoi + statut joueurs) ---"
$PYTHON migrate/main.py

echo ""
echo "--- Calcul classement historique (semaines manquantes) ---"
$PYTHON run_ranking_history.py --update

echo ""
echo "=== Import terminé ==="

# Record last update date
date +%Y-%m-%dT%H:%M:%S > "$(dirname "$0")/../data/last_update.txt"

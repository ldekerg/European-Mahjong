"""
Importe les résultats des tournois qui étaient dans le calendrier
et qui ont maintenant un ema_id (résultats disponibles sur le site EMA).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal
from app.models import Tournoi, Resultat
from scripts.import import ema as import_ema

db = SessionLocal()

# Tournois calendrier avec un ema_id mais sans résultats importés
candidats = (
    db.query(Tournoi)
    .filter(
        Tournoi.statut == "calendrier",
        Tournoi.ema_id.isnot(None),
    )
    .all()
)

a_importer = []
for t in candidats:
    nb = db.query(Resultat).filter(Resultat.tournoi_id == t.id).count()
    if nb == 0:
        a_importer.append(t)

if not a_importer:
    print("Aucun nouveau tournoi à importer.")
    db.close()
    sys.exit(0)

for t in a_importer:
    prefix = "TR_RCR" if t.regles == "RCR" else "TR"
    tid = str(t.ema_id)
    print(f"Import {prefix}_{tid} — {t.nom} ({t.date_debut})")
    html = import_ema.fetch_page(tid, prefix)
    if not html:
        print(f"  [ERREUR] page introuvable pour {prefix}_{tid}")
        continue
    data = import_ema.parse_tournament(html, t.ema_id)
    if not data:
        print(f"  [ERREUR] parse échoué pour {prefix}_{tid}")
        continue
    import_ema.import_tournament(db, data)
    print(f"  OK")

db.commit()
db.close()

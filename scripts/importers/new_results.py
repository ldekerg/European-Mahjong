"""
Imports results for tournaments that were in the calendar
and now have an ema_id (results available on the EMA website).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.database import SessionLocal
from app.models import Tournament, Result
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("ema", os.path.join(os.path.dirname(__file__), "ema.py"))
import_ema = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(import_ema)

db = SessionLocal()

# Calendar tournaments with an ema_id but no imported results
candidats = (
    db.query(Tournament)
    .filter(
        Tournament.status == "calendrier",
        Tournament.ema_id.isnot(None),
    )
    .all()
)

a_importer = []
for t in candidats:
    nb = db.query(Result).filter(Result.tournament_id == t.id).count()
    if nb == 0:
        a_importer.append(t)

if not a_importer:
    print("No new tournaments to import.")
    db.close()
    sys.exit(0)

for t in a_importer:
    prefix = "TR_RCR" if t.rules == "RCR" else "TR"
    tid = str(t.ema_id)
    print(f"Import {prefix}_{tid} — {t.name} ({t.start_date})")
    html = import_ema.fetch_page(tid, prefix)
    if not html:
        print(f"  [ERROR] page not found for {prefix}_{tid}")
        continue
    data = import_ema.parse_tournament(html, t.ema_id)
    if not data:
        print(f"  [ERROR] parse failed for {prefix}_{tid}")
        continue
    import_ema.import_tournament(db, data)
    print(f"  OK")

db.commit()
db.close()

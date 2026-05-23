"""
Add obs_report_path and obs_observer columns to tournaments table.
Run with: python3 scripts/migrate/obs_report.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.database import engine
from sqlalchemy import text

with engine.begin() as conn:
    for col, typedef in [
        ("obs_report_path", "TEXT"),
        ("obs_observer",    "TEXT"),
    ]:
        try:
            conn.execute(text(f'ALTER TABLE tournaments ADD COLUMN "{col}" {typedef}'))
            print(f"  Added column: {col}")
        except Exception as e:
            print(f"  {col}: skipped ({e})")

print("Done.")

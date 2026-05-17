"""
Migration: replaces hors_ranking with tournament_type, recomputes player statuses.
"""

import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ema_ranking.db")
con = sqlite3.connect(DB_PATH)

# --- Columns ---
for sql in [
    "ALTER TABLE tournaments ADD COLUMN tournament_type TEXT NOT NULL DEFAULT 'normal'",
    "ALTER TABLE players ADD COLUMN status TEXT NOT NULL DEFAULT 'europeen'",
    "ALTER TABLE tournaments ADD COLUMN website TEXT",
]:
    try:
        con.execute(sql)
        print(f"OK : {sql}")
    except sqlite3.OperationalError as e:
        print(f"(ignored) {e}")

# --- Classify tournaments ---

# WMC: ema_id >= 1000000 and rules = MCR (except the misclassified Russian tournament)
cur = con.execute("""
    UPDATE tournaments SET tournament_type='wmc'
    WHERE rules='MCR' AND ema_id >= 1000000
    AND name NOT LIKE '%RUSSIAN%' AND name NOT LIKE '%DUPLICATE%' AND name NOT LIKE '%DUBLICATE%'
""")
print(f"\nWMC marked: {cur.rowcount}")

# WRC: ema_id >= 1000000 and rules = RCR
cur = con.execute("""
    UPDATE tournaments SET tournament_type='wrc'
    WHERE rules='RCR' AND ema_id >= 1000000
""")
print(f"WRC marked: {cur.rowcount}")

# OEMC: European MCR Championship (numbered 1st to 7th) in the normal range
cur = con.execute("""
    UPDATE tournaments SET tournament_type='oemc'
    WHERE rules='MCR' AND tournament_type='normal'
    AND (name LIKE '%European MCR Championship%' OR name LIKE '%OEMC%')
""")
print(f"OEMC marked: {cur.rowcount}")

# OERC: European Riichi Championship in the normal range
cur = con.execute("""
    UPDATE tournaments SET tournament_type='oerc'
    WHERE rules='RCR' AND tournament_type='normal'
    AND (name LIKE '%European Riichi Championship%' OR name LIKE '%ERMC%' OR name LIKE '%OERC%')
""")
print(f"OERC marked: {cur.rowcount}")

print("\nDetail by type:")
for r in con.execute("SELECT tournament_type, rules, COUNT(*) FROM tournaments GROUP BY tournament_type, rules ORDER BY tournament_type, rules").fetchall():
    print(f"  {r[0]:8} {r[1]:3}  {r[2]}")

print("\nWMC/WRC/OEMC/OERC list:")
for r in con.execute("SELECT tournament_type, ema_id, rules, name FROM tournaments WHERE tournament_type != 'normal' ORDER BY tournament_type, rules, name").fetchall():
    print(f"  [{r[0]:4}] [{str(r[1] or ''):>8}] {r[2]:3}  {r[3]}")

# --- Player statuses ---

# Reset everything to europeen before recomputing
con.execute("UPDATE players SET status='europeen'")

# Guest: ID starts with "24"
cur = con.execute("UPDATE players SET status='guest' WHERE id LIKE '24%'")
print(f"\nGuest players (ID 24...): {cur.rowcount}")

# Foreign: all their results are in wmc or wrc tournaments
cur = con.execute("""
    UPDATE players SET status='etranger'
    WHERE status='europeen'
    AND id NOT IN (
        SELECT DISTINCT r.player_id
        FROM results r
        JOIN tournaments t ON t.id = r.tournament_id
        WHERE t.tournament_type NOT IN ('wmc', 'wrc')
    )
""")
print(f"Foreign players (WMC/WRC only): {cur.rowcount}")

con.commit()

# --- Invert points/mahjong for incorrectly imported MCR tournaments ---
# A tournament is inverted if at least one row has points < 0
# (EMA points are always >= 1) and mahjong > 0.
# Exclude cases with a single row (legitimately partial data).
inversions = con.execute("""
    SELECT t.id, t.name
    FROM tournaments t
    JOIN results r ON r.tournament_id = t.id
    WHERE t.rules = 'MCR'
    GROUP BY t.id
    HAVING SUM(CASE WHEN r.points < 0 THEN 1 ELSE 0 END) > 0
       AND COUNT(*) > 1
       AND MAX(r.mahjong) > 0
""").fetchall()

print(f"\nMCR tournaments with detected points/mahjong inversion: {len(inversions)}")
for tid, nom in inversions:
    cur = con.execute("""
        UPDATE results SET points = mahjong, mahjong = points
        WHERE tournament_id = ?
    """, (tid,))
    print(f"  [{tid}] {nom[:50]} — {cur.rowcount} rows inverted")

con.commit()

print("\nPlayer status summary:")
for r in con.execute("SELECT status, COUNT(*) FROM players GROUP BY status ORDER BY status").fetchall():
    print(f"  {r[0]:12} {r[1]}")

con.close()
print("\nMigration complete.")

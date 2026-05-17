"""
Migration : remplace hors_classement par type_tournoi, recalcule les statuts joueurs.
"""

import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ema_ranking.db")
con = sqlite3.connect(DB_PATH)

# --- Colonnes ---
for sql in [
    "ALTER TABLE tournois ADD COLUMN type_tournoi TEXT NOT NULL DEFAULT 'normal'",
    "ALTER TABLE joueurs ADD COLUMN statut TEXT NOT NULL DEFAULT 'europeen'",
    "ALTER TABLE tournois ADD COLUMN url_site TEXT",
]:
    try:
        con.execute(sql)
        print(f"OK : {sql}")
    except sqlite3.OperationalError as e:
        print(f"(ignoré) {e}")

# --- Classifier les tournois ---

# WMC : ema_id >= 1000000 et regles = MCR (sauf le tournoi russe mal rangé)
cur = con.execute("""
    UPDATE tournois SET type_tournoi='wmc'
    WHERE regles='MCR' AND ema_id >= 1000000
    AND nom NOT LIKE '%RUSSIAN%' AND nom NOT LIKE '%DUPLICATE%' AND nom NOT LIKE '%DUBLICATE%'
""")
print(f"\nWMC marqués : {cur.rowcount}")

# WRC : ema_id >= 1000000 et regles = RCR
cur = con.execute("""
    UPDATE tournois SET type_tournoi='wrc'
    WHERE regles='RCR' AND ema_id >= 1000000
""")
print(f"WRC marqués : {cur.rowcount}")

# OEMC : European MCR Championship (numérotés 1er à 7e) dans la plage normale
cur = con.execute("""
    UPDATE tournois SET type_tournoi='oemc'
    WHERE regles='MCR' AND type_tournoi='normal'
    AND (nom LIKE '%European MCR Championship%' OR nom LIKE '%OEMC%')
""")
print(f"OEMC marqués : {cur.rowcount}")

# OERC : European Riichi Championship dans la plage normale
cur = con.execute("""
    UPDATE tournois SET type_tournoi='oerc'
    WHERE regles='RCR' AND type_tournoi='normal'
    AND (nom LIKE '%European Riichi Championship%' OR nom LIKE '%ERMC%' OR nom LIKE '%OERC%')
""")
print(f"OERC marqués : {cur.rowcount}")

print("\nDétail par type :")
for r in con.execute("SELECT type_tournoi, regles, COUNT(*) FROM tournois GROUP BY type_tournoi, regles ORDER BY type_tournoi, regles").fetchall():
    print(f"  {r[0]:8} {r[1]:3}  {r[2]}")

print("\nListe WMC/WRC/OEMC/OERC :")
for r in con.execute("SELECT type_tournoi, ema_id, regles, nom FROM tournois WHERE type_tournoi != 'normal' ORDER BY type_tournoi, regles, nom").fetchall():
    print(f"  [{r[0]:4}] [{str(r[1] or ''):>8}] {r[2]:3}  {r[3]}")

# --- Statut joueurs ---

# Remettre tout à europeen avant recalcul
con.execute("UPDATE joueurs SET statut='europeen'")

# Guest : ID commence par "24"
cur = con.execute("UPDATE joueurs SET statut='guest' WHERE id LIKE '24%'")
print(f"\nJoueurs guest (ID 24...) : {cur.rowcount}")

# Étranger : tous leurs résultats sont dans des tournois wmc ou wrc
cur = con.execute("""
    UPDATE joueurs SET statut='etranger'
    WHERE statut='europeen'
    AND id NOT IN (
        SELECT DISTINCT r.joueur_id
        FROM resultats r
        JOIN tournois t ON t.id = r.tournoi_id
        WHERE t.type_tournoi NOT IN ('wmc', 'wrc')
    )
""")
print(f"Joueurs étrangers (WMC/WRC uniquement) : {cur.rowcount}")

con.commit()

# --- Inversion points/mahjong pour tournois MCR mal importés ---
# Un tournoi est inversé si au moins une ligne a points < 0
# (les points EMA sont toujours >= 1) et mahjong > 0.
# On exclut les cas avec une seule ligne (données partielles légitimes).
inversions = con.execute("""
    SELECT t.id, t.nom
    FROM tournois t
    JOIN resultats r ON r.tournoi_id = t.id
    WHERE t.regles = 'MCR'
    GROUP BY t.id
    HAVING SUM(CASE WHEN r.points < 0 THEN 1 ELSE 0 END) > 0
       AND COUNT(*) > 1
       AND MAX(r.mahjong) > 0
""").fetchall()

print(f"\nTournois MCR avec inversion points/mahjong détectée : {len(inversions)}")
for tid, nom in inversions:
    cur = con.execute("""
        UPDATE resultats SET points = mahjong, mahjong = points
        WHERE tournoi_id = ?
    """, (tid,))
    print(f"  [{tid}] {nom[:50]} — {cur.rowcount} lignes inversées")

con.commit()

print("\nRésumé statuts joueurs :")
for r in con.execute("SELECT statut, COUNT(*) FROM joueurs GROUP BY statut ORDER BY statut").fetchall():
    print(f"  {r[0]:12} {r[1]}")

con.close()
print("\nMigration terminée.")

"""
Migration: rename all French column names to English across all tables.
SQLite supports RENAME COLUMN since version 3.25.0 (2018-09-15).
"""

import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ema_ranking.db")
con = sqlite3.connect(DB_PATH)

RENAMES = [
    # classement_historique
    ("ranking_history", "semaine",           "week"),
    ("ranking_history", "regles",            "rules"),
    ("ranking_history", "joueur_id",         "player_id"),
    ("ranking_history", "nb_tournois",       "nb_tournaments"),
    ("ranking_history", "nb_or",             "nb_gold"),
    ("ranking_history", "nb_argent",         "nb_silver"),
    # joueurs
    ("players",               "nom",               "last_name"),
    ("players",               "prenom",            "first_name"),
    ("players",               "nationalite",       "nationality"),
    ("players",               "statut",            "status"),
    # tournois
    ("tournaments",              "nom",               "name"),
    ("tournaments",              "lieu",              "city"),
    ("tournaments",              "pays",              "country"),
    ("tournaments",              "date_debut",        "start_date"),
    ("tournaments",              "date_fin",          "end_date"),
    ("tournaments",              "nb_joueurs",        "nb_players"),
    ("tournaments",              "type_tournoi",      "tournament_type"),
    ("tournaments",              "approbation",       "approval"),
    ("tournaments",              "url_site",          "website"),
    ("tournaments",              "regles",            "rules"),
    ("tournaments",              "statut",            "status"),
    ("tournaments",              "ville_id",          "city_id"),
    # resultats
    ("results",             "tournoi_id",        "tournament_id"),
    ("results",             "joueur_id",         "player_id"),
    ("results",             "nationalite",       "nationality"),
    # resultats_anonymes
    ("anonymous_results",    "tournoi_id",        "tournament_id"),
    ("anonymous_results",    "nationalite",       "nationality"),
    ("anonymous_results",    "nom",               "last_name"),
    ("anonymous_results",    "prenom",            "first_name"),
    # changements_nationalite
    ("nationality_changes", "joueur_id",       "player_id"),
    ("nationality_changes", "nationalite_avant","nationality_before"),
    ("nationality_changes", "nationalite_apres","nationality_after"),
    ("nationality_changes", "date_changement", "change_date"),
    # villes
    ("cities",                "nom",               "name"),
    ("cities",                "pays",              "country"),
    # serie_championnat
    ("championship_series",     "nom",               "name"),
    ("championship_series",     "regles",            "rules"),
    ("championship_series",     "pays",              "country"),
    # championnat
    ("championnat",           "serie_id",          "series_id"),
    ("championnat",           "annee",             "year"),
    ("championnat",           "nom",               "name"),
    ("championnat",           "formule",           "formula"),
    ("championnat",           "champion_nom",      "champion_name"),
    # championnat_tournoi
    ("championship_tournaments",   "championnat_id",    "championship_id"),
    ("championship_tournaments",   "tournoi_id",        "tournament_id"),
]

ok = 0
for table, old_col, new_col in RENAMES:
    try:
        con.execute(f'ALTER TABLE "{table}" RENAME COLUMN "{old_col}" TO "{new_col}"')
        print(f"  OK  {table}.{old_col} → {new_col}")
        ok += 1
    except sqlite3.OperationalError as e:
        print(f"  --  {table}.{old_col}: {e}")

con.commit()
con.close()
print(f"\n{ok}/{len(RENAMES)} columns renamed.")

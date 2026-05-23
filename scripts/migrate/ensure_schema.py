"""
Ensure all columns and tables exist in the database.
Safe to run multiple times — skips anything already present.
Run with: python3 scripts/migrate/ensure_schema.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.database import engine
from sqlalchemy import text

COLUMNS = [
    # (table, column, definition)
    ("tournaments", "obs_report_path",       "TEXT"),
    ("tournaments", "obs_observer",          "TEXT"),
    ("tournaments", "obs_player_id",         "TEXT REFERENCES players(id)"),
    ("tournaments", "website",               "TEXT"),
    ("tournaments", "registration_open",     "DATE"),
    ("tournaments", "created_at",            "DATETIME"),
    ("tournaments", "approval",              "TEXT"),
    ("tournaments", "status",                "TEXT NOT NULL DEFAULT 'actif'"),
    ("tournaments", "tournament_type",       "TEXT NOT NULL DEFAULT 'normal'"),
    ("players",     "status",                "TEXT NOT NULL DEFAULT 'europeen'"),
    ("referees",    "seminar_city_id",        "INTEGER REFERENCES cities(id)"),
    ("referees",    "player_id",             "TEXT REFERENCES players(id)"),
]

TABLES = [
    ("cities", """
        CREATE TABLE IF NOT EXISTS cities (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL,
            country   TEXT NOT NULL,
            latitude  REAL NOT NULL,
            longitude REAL NOT NULL
        )
    """),
    ("referees", """
        CREATE TABLE IF NOT EXISTS referees (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT NOT NULL,
            country          TEXT NOT NULL,
            rules            TEXT NOT NULL,
            seminar_year     INTEGER,
            seminar_location TEXT,
            seminar_city_id  INTEGER REFERENCES cities(id),
            player_id        TEXT REFERENCES players(id)
        )
    """),
    ("tournament_referees", """
        CREATE TABLE IF NOT EXISTS tournament_referees (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL REFERENCES tournaments(id),
            referee_id    INTEGER REFERENCES referees(id),
            player_id     TEXT REFERENCES players(id),
            name          TEXT NOT NULL
        )
    """),
    ("championship_series", """
        CREATE TABLE IF NOT EXISTS championship_series (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            slug        TEXT UNIQUE NOT NULL,
            name        TEXT NOT NULL,
            rules       TEXT NOT NULL,
            country     TEXT NOT NULL,
            description TEXT
        )
    """),
    ("championships", """
        CREATE TABLE IF NOT EXISTS championships (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id     INTEGER NOT NULL REFERENCES championship_series(id),
            year          INTEGER NOT NULL,
            name          TEXT,
            formula       TEXT NOT NULL DEFAULT 'moyenne_n_meilleurs',
            params        TEXT NOT NULL DEFAULT '{"n": 3}',
            champion_id   TEXT REFERENCES players(id),
            champion_name TEXT
        )
    """),
    ("championship_tournaments", """
        CREATE TABLE IF NOT EXISTS championship_tournaments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            championship_id INTEGER NOT NULL REFERENCES championships(id),
            tournament_id   INTEGER NOT NULL REFERENCES tournaments(id),
            UNIQUE(championship_id, tournament_id)
        )
    """),
    ("audit_log", """
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   DATETIME NOT NULL,
            admin_user  TEXT NOT NULL,
            action      TEXT NOT NULL,
            table_name  TEXT NOT NULL,
            row_id      TEXT,
            description TEXT,
            old_values  TEXT,
            new_values  TEXT,
            session_id  TEXT
        )
    """),
    ("ranking_history", """
        CREATE TABLE IF NOT EXISTS ranking_history (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            week           DATE NOT NULL,
            rules          TEXT NOT NULL,
            player_id      TEXT NOT NULL REFERENCES players(id),
            position       INTEGER NOT NULL,
            score          REAL NOT NULL,
            nb_tournaments INTEGER,
            nb_gold        INTEGER,
            nb_silver      INTEGER,
            nb_bronze      INTEGER
        )
    """),
    ("admin_users", """
        CREATE TABLE IF NOT EXISTS admin_users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'admin',
            countries     TEXT,
            created_at    DATETIME NOT NULL,
            last_login    DATETIME
        )
    """),
    ("nationality_changes", """
        CREATE TABLE IF NOT EXISTS nationality_changes (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id          TEXT NOT NULL REFERENCES players(id),
            nationality_before TEXT NOT NULL,
            nationality_after  TEXT NOT NULL,
            change_date        DATE NOT NULL
        )
    """),
]

with engine.begin() as conn:
    # Create missing tables
    for table_name, ddl in TABLES:
        try:
            conn.execute(text(ddl))
            print(f"  Table OK : {table_name}")
        except Exception as e:
            print(f"  Table {table_name}: {e}")

    # Add missing columns
    for table, col, definition in COLUMNS:
        try:
            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN "{col}" {definition}'))
            print(f"  Added    : {table}.{col}")
        except Exception as e:
            print(f"  Skip     : {table}.{col} ({e})")

print("\nDone.")

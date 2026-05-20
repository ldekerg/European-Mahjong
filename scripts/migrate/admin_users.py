"""Migration: create admin_users table."""

import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ema_ranking.db")
con = sqlite3.connect(DB_PATH)

con.execute("""
    CREATE TABLE IF NOT EXISTS admin_users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        username      TEXT    NOT NULL UNIQUE,
        password_hash TEXT    NOT NULL,
        role          TEXT    NOT NULL DEFAULT 'admin',
        countries     TEXT,
        created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_login    DATETIME
    )
""")

# Add countries column if table already exists
try:
    con.execute("ALTER TABLE admin_users ADD COLUMN countries TEXT")
    print("Added column: countries")
except Exception:
    pass  # already exists

con.commit()
con.close()
print("Migration complete: admin_users table created.")

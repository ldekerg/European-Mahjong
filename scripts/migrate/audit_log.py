"""Migration: create audit_log table."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.database import engine
from sqlalchemy import text

DDL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   DATETIME NOT NULL DEFAULT (datetime('now')),
    admin_user  TEXT     NOT NULL,
    action      TEXT     NOT NULL,
    table_name  TEXT     NOT NULL,
    row_id      TEXT,
    description TEXT,
    old_values  TEXT,
    new_values  TEXT,
    session_id  TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_log_timestamp ON audit_log (timestamp);
CREATE INDEX IF NOT EXISTS ix_audit_log_table_row  ON audit_log (table_name, row_id);
CREATE INDEX IF NOT EXISTS ix_audit_log_session    ON audit_log (session_id);
"""

if __name__ == "__main__":
    with engine.connect() as conn:
        for stmt in DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()
    print("audit_log table created (or already exists).")

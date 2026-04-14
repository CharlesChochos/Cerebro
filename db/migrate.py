"""
Simple migration runner — executes numbered SQL files in order.
Tracks applied migrations in a `_migrations` table.
"""
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def run_migrations(conn: sqlite3.Connection) -> list[str]:
    """Apply all pending migrations and return list of newly applied filenames."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    applied = {
        row[0]
        for row in conn.execute("SELECT filename FROM _migrations").fetchall()
    }

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    newly_applied = []

    for f in migration_files:
        if f.name not in applied:
            sql = f.read_text()
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO _migrations (filename) VALUES (?)", (f.name,)
            )
            conn.commit()
            newly_applied.append(f.name)

    return newly_applied

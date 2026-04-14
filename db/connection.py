"""
Database connection management for Cerebro.
Provides a single SQLite connection with FTS5 and SpatiaLite extensions.
"""
import sqlite3
from pathlib import Path

from config.settings import DB_PATH


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Create a configured SQLite connection with extensions loaded."""
    path = db_path or DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")

    # Load SpatiaLite for geo queries
    conn.enable_load_extension(True)
    conn.load_extension("mod_spatialite")
    conn.enable_load_extension(False)

    # Initialize SpatiaLite metadata if needed
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='geometry_columns'"
    )
    if cursor.fetchone() is None:
        conn.execute("SELECT InitSpatialMetaData(1)")
        conn.commit()

    return conn

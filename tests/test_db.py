"""
Phase 0 Validation Tests — Database, FTS5, SpatiaLite, Migrations.
"""
import os
import sqlite3
import tempfile

import pytest

# Ensure imports resolve from project root
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection
from db.migrate import run_migrations


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = get_connection(path)
    run_migrations(conn)
    yield conn
    conn.close()
    os.unlink(path)


class TestSchema:
    """Verify core schema creates correctly."""

    def test_core_tables_exist(self, db):
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {
            "events", "entities", "entity_relations", "alerts",
            "source_reliability", "system_log", "audit_log", "_migrations",
        }
        assert expected.issubset(tables)

    def test_fts5_table_exists(self, db):
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "events_fts" in tables

    def test_migrations_tracked(self, db):
        rows = db.execute("SELECT filename FROM _migrations").fetchall()
        filenames = [r[0] for r in rows]
        assert "001_core_schema.sql" in filenames

    def test_migrations_idempotent(self, db):
        """Running migrations twice should not error or duplicate."""
        applied = run_migrations(db)
        assert applied == []  # Nothing new to apply


class TestFTS5:
    """Verify full-text search works end-to-end."""

    def test_insert_and_search(self, db):
        db.execute(
            """INSERT INTO events (id, source, source_id, timestamp, title, summary)
               VALUES ('e1', 'test', 't1', '2026-04-09T00:00:00Z',
                       'Military conflict in eastern region',
                       'Armed forces engaged near the border')"""
        )
        db.commit()

        results = db.execute(
            "SELECT * FROM events_fts WHERE events_fts MATCH 'military'"
        ).fetchall()
        assert len(results) == 1

    def test_search_summary(self, db):
        db.execute(
            """INSERT INTO events (id, source, source_id, timestamp, title, summary)
               VALUES ('e2', 'test', 't2', '2026-04-09T00:00:00Z',
                       'Economic report', 'GDP growth exceeded expectations in Q1')"""
        )
        db.commit()

        results = db.execute(
            "SELECT * FROM events_fts WHERE events_fts MATCH 'GDP'"
        ).fetchall()
        assert len(results) == 1

    def test_fts_sync_on_delete(self, db):
        db.execute(
            """INSERT INTO events (id, source, source_id, timestamp, title, summary)
               VALUES ('e3', 'test', 't3', '2026-04-09T00:00:00Z',
                       'Temporary event', 'Should be removed from search')"""
        )
        db.commit()
        db.execute("DELETE FROM events WHERE id = 'e3'")
        db.commit()

        results = db.execute(
            "SELECT * FROM events_fts WHERE events_fts MATCH 'temporary'"
        ).fetchall()
        assert len(results) == 0

    def test_fts_sync_on_update(self, db):
        db.execute(
            """INSERT INTO events (id, source, source_id, timestamp, title, summary)
               VALUES ('e4', 'test', 't4', '2026-04-09T00:00:00Z',
                       'Zebra crossing alert', 'Zebra spotted near road')"""
        )
        db.commit()
        db.execute(
            "UPDATE events SET title = 'Updated crossing alert', summary = 'Updated spotted near road' WHERE id = 'e4'"
        )
        db.commit()

        old = db.execute(
            "SELECT * FROM events_fts WHERE events_fts MATCH 'Zebra'"
        ).fetchall()
        new = db.execute(
            "SELECT * FROM events_fts WHERE events_fts MATCH 'Updated'"
        ).fetchall()
        assert len(old) == 0
        assert len(new) == 1


class TestSpatiaLite:
    """Verify SpatiaLite geo queries work."""

    def test_distance_query(self, db):
        """Calculate distance between two points (NYC and nearby)."""
        result = db.execute(
            "SELECT ST_Distance(MakePoint(-74.006, 40.7128, 4326), MakePoint(-73.935, 40.7306, 4326))"
        ).fetchone()
        assert result[0] is not None
        assert result[0] > 0

    def test_point_in_polygon(self, db):
        """Test if a point falls within a bounding box polygon."""
        result = db.execute("""
            SELECT ST_Within(
                MakePoint(-74.006, 40.7128, 4326),
                BuildMbr(-75.0, 40.0, -73.0, 41.0, 4326)
            )
        """).fetchone()
        assert result[0] == 1  # Point is within the box

    def test_point_outside_polygon(self, db):
        result = db.execute("""
            SELECT ST_Within(
                MakePoint(0.0, 0.0, 4326),
                BuildMbr(-75.0, 40.0, -73.0, 41.0, 4326)
            )
        """).fetchone()
        assert result[0] == 0  # Point is outside


class TestEventDedup:
    """Verify source+source_id uniqueness constraint."""

    def test_duplicate_rejected(self, db):
        db.execute(
            """INSERT INTO events (id, source, source_id, timestamp, title)
               VALUES ('e10', 'gdelt', 'g100', '2026-04-09T00:00:00Z', 'Event A')"""
        )
        db.commit()

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO events (id, source, source_id, timestamp, title)
                   VALUES ('e11', 'gdelt', 'g100', '2026-04-09T00:00:00Z', 'Event B')"""
            )

    def test_same_source_id_different_source_allowed(self, db):
        db.execute(
            """INSERT INTO events (id, source, source_id, timestamp, title)
               VALUES ('e12', 'gdelt', 'x1', '2026-04-09T00:00:00Z', 'GDELT event')"""
        )
        db.execute(
            """INSERT INTO events (id, source, source_id, timestamp, title)
               VALUES ('e13', 'acled', 'x1', '2026-04-09T00:00:00Z', 'ACLED event')"""
        )
        db.commit()
        count = db.execute("SELECT COUNT(*) FROM events WHERE source_id = 'x1'").fetchone()[0]
        assert count == 2

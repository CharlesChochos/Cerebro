"""
Phase 2 Tests — Sources API endpoint.
"""
import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Override DB path before importing the app
_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["CEREBRO_DB_PATH"] = _test_db_path

from api.main import app, get_db


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        db = get_db()
        # Seed source_reliability (schema: source, total_events, confirmed_events,
        # accuracy, last_ingestion, avg_latency_seconds, status)
        sources = [
            ("gdelt", 2500, 2300, 0.92, "2026-04-09T10:00:00Z", 1.5, "active"),
            ("rss", 700, 560, 0.80, "2026-04-09T09:00:00Z", 2.1, "active"),
            ("yahoo_finance", 21, 21, 1.0, "2026-04-09T08:00:00Z", 0.5, "active"),
        ]
        for src, total, confirmed, accuracy, last, latency, status in sources:
            db.execute(
                """INSERT INTO source_reliability
                   (source, total_events, confirmed_events, accuracy,
                    last_ingestion, avg_latency_seconds, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (src, total, confirmed, accuracy, last, latency, status),
            )

        # Seed events for count/category breakdown
        for i in range(5):
            db.execute(
                """INSERT INTO events
                   (id, source, source_id, timestamp, title, category, severity, confidence)
                   VALUES (?, ?, ?, '2026-04-09T12:00:00Z', ?, ?, 50, 0.8)""",
                (f"src-evt-{i}", "gdelt", f"gdelt-src-{i}", f"Event {i}", "military"),
            )
        for i in range(3):
            db.execute(
                """INSERT INTO events
                   (id, source, source_id, timestamp, title, category, severity, confidence)
                   VALUES (?, ?, ?, '2026-04-09T12:00:00Z', ?, ?, 40, 0.7)""",
                (f"rss-evt-{i}", "rss", f"rss-src-{i}", f"RSS Event {i}", "political"),
            )
        db.commit()
        yield c
    os.unlink(_test_db_path)


class TestSourcesEndpoint:
    def test_returns_sources(self, client):
        resp = client.get("/api/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert "sources" in data
        assert len(data["sources"]) == 3

    def test_source_has_accuracy(self, client):
        resp = client.get("/api/sources")
        sources = resp.json()["sources"]
        gdelt = next(s for s in sources if s["source"] == "gdelt")
        assert gdelt["accuracy"] == 0.92
        assert gdelt["total_events"] == 2500

    def test_source_has_event_count_in_db(self, client):
        resp = client.get("/api/sources")
        sources = resp.json()["sources"]
        gdelt = next(s for s in sources if s["source"] == "gdelt")
        assert gdelt["event_count_in_db"] >= 5

    def test_source_has_category_breakdown(self, client):
        resp = client.get("/api/sources")
        sources = resp.json()["sources"]
        gdelt = next(s for s in sources if s["source"] == "gdelt")
        assert "categories" in gdelt
        assert gdelt["categories"].get("military") >= 5

    def test_ordered_by_total_events(self, client):
        resp = client.get("/api/sources")
        sources = resp.json()["sources"]
        totals = [s["total_events"] for s in sources]
        assert totals == sorted(totals, reverse=True)

"""
Phase 2 Tests — Multi-source event filtering via API.
"""
import json
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
        # Seed events from multiple sources
        events = [
            ("ms-1", "gdelt", "gdelt-001", "GDELT conflict event", "military", 70),
            ("ms-2", "gdelt", "gdelt-002", "GDELT diplomatic event", "political", 40),
            ("ms-3", "rss", "rss-001", "BBC breaking news", "military", 65),
            ("ms-4", "rss", "rss-002", "Guardian health report", "health", 30),
            ("ms-5", "yahoo_finance", "yf-001", "S&P 500 drops 3%", "economic", 80),
            ("ms-6", "worldbank", "wb-001", "GDP growth data 2024", "economic", 25),
        ]
        for eid, src, sid, title, cat, sev in events:
            db.execute(
                """INSERT INTO events
                   (id, source, source_id, timestamp, title, category, severity, confidence)
                   VALUES (?, ?, ?, '2026-04-09T12:00:00Z', ?, ?, ?, 0.8)""",
                (eid, src, sid, title, cat, sev),
            )
        db.commit()
        yield c
    os.unlink(_test_db_path)


class TestMultiSourceFiltering:
    def test_all_sources_returned_unfiltered(self, client):
        resp = client.get("/api/events?limit=200")
        data = resp.json()
        assert data["total"] >= 6
        sources = {e["source"] for e in data["events"]}
        assert {"gdelt", "rss", "yahoo_finance", "worldbank"}.issubset(sources)

    def test_filter_by_source_gdelt(self, client):
        resp = client.get("/api/events?source=gdelt")
        data = resp.json()
        assert data["total"] >= 2
        assert all(e["source"] == "gdelt" for e in data["events"])

    def test_filter_by_source_rss(self, client):
        resp = client.get("/api/events?source=rss")
        data = resp.json()
        assert data["total"] >= 2
        assert all(e["source"] == "rss" for e in data["events"])

    def test_filter_by_source_and_category(self, client):
        resp = client.get("/api/events?source=gdelt&category=military")
        data = resp.json()
        assert data["total"] >= 1
        assert all(e["source"] == "gdelt" for e in data["events"])
        assert all(e["category"] == "military" for e in data["events"])

    def test_filter_by_source_and_severity(self, client):
        resp = client.get("/api/events?source=yahoo_finance&severity_min=50")
        data = resp.json()
        assert data["total"] >= 1
        assert all(e["severity"] >= 50 for e in data["events"])

    def test_filter_nonexistent_source_returns_empty(self, client):
        resp = client.get("/api/events?source=nonexistent")
        data = resp.json()
        assert data["total"] == 0
        assert data["events"] == []

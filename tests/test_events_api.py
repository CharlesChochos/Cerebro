"""
Phase 1 Validation Tests — Events API endpoints.
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
        # Seed some test events
        db = get_db()
        for i in range(5):
            cat = ["military", "political", "economic", "health", "environmental"][i]
            db.execute(
                """INSERT INTO events
                   (id, source, source_id, timestamp, title, summary,
                    category, severity, confidence, latitude, longitude,
                    country_code, entities_json, source_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"test-{i}", "gdelt", f"gdelt-test-{i}",
                    "2026-04-09T12:00:00Z",
                    f"Test event {i} about {cat}",
                    f"Summary for {cat} event",
                    cat, (i + 1) * 20, 0.8,
                    40.0 + i, -74.0 + i,
                    "US",
                    json.dumps([{"name": f"Actor{i}", "type": "actor", "role": "source"}]),
                    f"https://example.com/{i}",
                ),
            )
        db.commit()
        yield c
    os.unlink(_test_db_path)


class TestListEvents:
    def test_returns_events(self, client):
        resp = client.get("/api/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 5
        assert len(data["events"]) >= 5

    def test_filter_by_category(self, client):
        resp = client.get("/api/events?category=military")
        data = resp.json()
        assert data["total"] >= 1
        assert all(e["category"] == "military" for e in data["events"])

    def test_filter_by_severity(self, client):
        resp = client.get("/api/events?severity_min=60")
        data = resp.json()
        assert all(e["severity"] >= 60 for e in data["events"])

    def test_pagination(self, client):
        resp = client.get("/api/events?limit=2&offset=0")
        data = resp.json()
        assert len(data["events"]) == 2
        assert data["total"] >= 5

        resp2 = client.get("/api/events?limit=2&offset=2")
        data2 = resp2.json()
        assert len(data2["events"]) == 2
        assert data2["events"][0]["id"] != data["events"][0]["id"]

    def test_search(self, client):
        resp = client.get("/api/events?search=military")
        data = resp.json()
        assert data["total"] >= 1

    def test_entities_parsed(self, client):
        resp = client.get("/api/events?limit=1")
        event = resp.json()["events"][0]
        assert "entities" in event
        assert isinstance(event["entities"], list)
        assert "entities_json" not in event


class TestGetEvent:
    def test_get_existing_event(self, client):
        resp = client.get("/api/events/test-0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "test-0"
        assert data["category"] == "military"
        assert "entities" in data
        assert "raw_payload" in data

    def test_get_nonexistent_event(self, client):
        resp = client.get("/api/events/does-not-exist")
        assert resp.status_code == 404

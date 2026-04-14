"""
Phase 2 Tests — Entities API endpoints.
"""
import json
import os
import sys
import tempfile
import uuid

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
        # Seed entities
        entities_data = [
            ("ent-api-1", "Russia", "location", '{"country_code":"RU"}', 35),
            ("ent-api-2", "NATO", "organization", '{}', 28),
            ("ent-api-3", "Iran", "location", '{"country_code":"IR"}', 20),
            ("ent-api-4", "United Nations", "organization", '{}', 15),
            ("ent-api-5", "Joe Biden", "actor", '{}', 10),
        ]
        for eid, name, etype, meta, count in entities_data:
            db.execute(
                """INSERT OR IGNORE INTO entities (id, name, entity_type, metadata, event_count,
                   first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, '2026-04-01T00:00:00Z', '2026-04-09T00:00:00Z')""",
                (eid, name, etype, meta, count),
            )

        # Seed events needed for FK on entity_relations
        for eid in ("evt-entapi-1", "evt-entapi-2"):
            db.execute(
                """INSERT OR IGNORE INTO events (id, source, source_id, timestamp, title, severity, confidence)
                   VALUES (?, 'gdelt', ?, '2026-04-09T12:00:00Z', 'Test', 50, 0.8)""",
                (eid, eid),
            )

        # Seed entity relations
        db.execute(
            """INSERT INTO entity_relations
               (id, source_entity_id, target_entity_id, relation_type, confidence, source_event_id)
               VALUES (?, ?, ?, 'co_occurs', 0.5, 'evt-entapi-1')""",
            (str(uuid.uuid4()), "ent-api-1", "ent-api-2"),
        )
        db.execute(
            """INSERT INTO entity_relations
               (id, source_entity_id, target_entity_id, relation_type, confidence, source_event_id)
               VALUES (?, ?, ?, 'co_occurs', 0.5, 'evt-entapi-2')""",
            (str(uuid.uuid4()), "ent-api-1", "ent-api-3"),
        )
        db.commit()
        yield c
    os.unlink(_test_db_path)


class TestListEntities:
    def test_returns_all_entities(self, client):
        resp = client.get("/api/entities")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 5
        assert len(data["entities"]) >= 5

    def test_filter_by_type(self, client):
        resp = client.get("/api/entities?entity_type=location")
        data = resp.json()
        assert data["total"] >= 2
        assert all(e["entity_type"] == "location" for e in data["entities"])

    def test_search_by_name(self, client):
        resp = client.get("/api/entities?search=Russia")
        data = resp.json()
        assert data["total"] >= 1
        assert any(e["name"] == "Russia" for e in data["entities"])

    def test_sort_by_event_count(self, client):
        resp = client.get("/api/entities?sort=event_count")
        data = resp.json()
        counts = [e["event_count"] for e in data["entities"]]
        assert counts == sorted(counts, reverse=True)

    def test_pagination(self, client):
        resp = client.get("/api/entities?limit=2&offset=0")
        data = resp.json()
        assert len(data["entities"]) == 2
        assert data["total"] >= 5

    def test_metadata_parsed(self, client):
        resp = client.get("/api/entities?search=Russia")
        entity = resp.json()["entities"][0]
        assert isinstance(entity["metadata"], dict)
        assert entity["metadata"]["country_code"] == "RU"


class TestGetEntity:
    def test_get_existing_entity(self, client):
        resp = client.get("/api/entities/ent-api-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Russia"
        assert data["entity_type"] == "location"
        assert "relations" in data

    def test_entity_has_relations(self, client):
        resp = client.get("/api/entities/ent-api-1")
        data = resp.json()
        assert len(data["relations"]) >= 2

    def test_get_nonexistent_entity(self, client):
        resp = client.get("/api/entities/does-not-exist")
        assert resp.status_code == 404

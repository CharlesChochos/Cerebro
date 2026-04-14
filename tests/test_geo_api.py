"""
Phase 3 Tests — Geo API endpoints and saved views.
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
        # Seed geo events
        events = [
            ("geo-1", "gdelt", "g1", "Conflict in Kyiv", "military", 80, 0.9, 50.45, 30.52, "UA"),
            ("geo-2", "rss", "r1", "EU summit in Brussels", "political", 40, 0.8, 50.85, 4.35, "BE"),
            ("geo-3", "gdelt", "g2", "Earthquake in Tokyo", "environmental", 70, 0.7, 35.68, 139.69, "JP"),
            ("geo-4", "rss", "r2", "Trade talks in DC", "economic", 35, 0.6, 38.90, -77.04, "US"),
            ("geo-5", "gdelt", "g3", "Military exercise Arctic", "military", 55, 0.5, 71.0, 25.0, "NO"),
            # Event with no coordinates (should be excluded from geo results)
            ("geo-6", "rss", "r3", "Virtual summit online", "political", 30, 0.5, None, None, None),
        ]
        for eid, src, sid, title, cat, sev, conf, lat, lng, cc in events:
            db.execute(
                """INSERT INTO events
                   (id, source, source_id, timestamp, title, category,
                    severity, confidence, latitude, longitude, country_code)
                   VALUES (?, ?, ?, '2026-04-09T12:00:00Z', ?, ?, ?, ?, ?, ?, ?)""",
                (eid, src, sid, title, cat, sev, conf, lat, lng, cc),
            )
        db.commit()
        yield c
    os.unlink(_test_db_path)


class TestGeoEvents:
    def test_global_bbox_returns_all_geo_events(self, client):
        resp = client.get("/api/events/geo?west=-180&south=-90&east=180&north=90")
        assert resp.status_code == 200
        data = resp.json()
        # Should get at least 5 (not geo-6 which has no coordinates)
        assert data["total"] >= 5

    def test_european_bbox(self, client):
        """Bounding box covering Europe should return Kyiv and Brussels."""
        resp = client.get("/api/events/geo?west=-10&south=35&east=45&north=72")
        data = resp.json()
        ids = [f["id"] for f in data["features"]]
        assert "geo-1" in ids  # Kyiv
        assert "geo-2" in ids  # Brussels
        assert "geo-5" in ids  # Arctic Norway
        assert "geo-3" not in ids  # Tokyo
        assert "geo-4" not in ids  # DC

    def test_filter_by_category(self, client):
        resp = client.get("/api/events/geo?west=-180&south=-90&east=180&north=90&category=military")
        data = resp.json()
        assert all(f["category"] == "military" for f in data["features"])
        assert data["total"] >= 2

    def test_filter_by_source(self, client):
        resp = client.get("/api/events/geo?west=-180&south=-90&east=180&north=90&source=rss")
        data = resp.json()
        assert all(f["source"] == "rss" for f in data["features"])

    def test_filter_by_severity(self, client):
        resp = client.get("/api/events/geo?west=-180&south=-90&east=180&north=90&severity_min=60")
        data = resp.json()
        assert all(f["severity"] >= 60 for f in data["features"])

    def test_features_have_required_fields(self, client):
        resp = client.get("/api/events/geo?west=-180&south=-90&east=180&north=90&limit=1")
        feature = resp.json()["features"][0]
        assert "id" in feature
        assert "lat" in feature
        assert "lng" in feature
        assert "title" in feature
        assert "category" in feature
        assert "severity" in feature
        assert "source" in feature

    def test_ordered_by_severity_desc(self, client):
        resp = client.get("/api/events/geo?west=-180&south=-90&east=180&north=90")
        features = resp.json()["features"]
        sevs = [f["severity"] for f in features]
        assert sevs == sorted(sevs, reverse=True)

    def test_limit_respected(self, client):
        resp = client.get("/api/events/geo?west=-180&south=-90&east=180&north=90&limit=2")
        data = resp.json()
        assert data["total"] == 2


class TestSavedViews:
    def test_create_view(self, client):
        resp = client.post("/api/views", json={
            "name": "Europe Overview",
            "description": "Main European hotspots",
            "center_lat": 50.0,
            "center_lng": 10.0,
            "zoom": 4.0,
            "layers": ["gdelt", "rss"],
            "filters": {"category": "military"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["name"] == "Europe Overview"

    def test_list_views(self, client):
        # Create a second view
        client.post("/api/views", json={
            "name": "Asia Pacific",
            "center_lat": 35.0,
            "center_lng": 135.0,
            "zoom": 3.0,
        })
        resp = client.get("/api/views")
        assert resp.status_code == 200
        views = resp.json()["views"]
        assert len(views) >= 2

    def test_get_view(self, client):
        # Create and retrieve
        create = client.post("/api/views", json={
            "name": "Test View",
            "center_lat": 0.0,
            "center_lng": 0.0,
            "zoom": 2.0,
            "layers": ["gdelt"],
            "filters": {"severity_min": 50},
        })
        view_id = create.json()["id"]

        resp = client.get(f"/api/views/{view_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test View"
        assert data["layers"] == ["gdelt"]
        assert data["filters"]["severity_min"] == 50

    def test_delete_view(self, client):
        create = client.post("/api/views", json={
            "name": "To Delete",
            "center_lat": 0.0,
            "center_lng": 0.0,
            "zoom": 1.0,
        })
        view_id = create.json()["id"]

        resp = client.delete(f"/api/views/{view_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == view_id

        # Verify deleted
        resp = client.get(f"/api/views/{view_id}")
        assert resp.status_code == 404

    def test_get_nonexistent_view(self, client):
        resp = client.get("/api/views/does-not-exist")
        assert resp.status_code == 404

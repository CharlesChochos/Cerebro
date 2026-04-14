"""
API Tests — Phase 16: Disease outbreaks, storm tracking, conflict progression.
"""
import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["CEREBRO_DB_PATH"] = _test_db_path

from api.main import app, get_db


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
    os.unlink(_test_db_path)


# ─── Disease Outbreak API ─────────────────────────────────

class TestDiseaseOutbreakAPI:
    _oid = None

    def test_seed_outbreaks(self, client):
        resp = client.post("/api/disease-outbreaks/seed")
        assert resp.status_code == 200
        assert resp.json()["seeded"] >= 0

    def test_create_outbreak(self, client):
        resp = client.post("/api/disease-outbreaks", json={
            "disease": "API Test Virus",
            "lat": 40.7, "lng": -74.0,
            "country_code": "US", "r_naught": 2.8,
        })
        assert resp.status_code == 200
        data = resp.json()
        TestDiseaseOutbreakAPI._oid = data["id"]
        assert data["disease"] == "API Test Virus"
        assert data["days_generated"] == 30

    def test_list_outbreaks(self, client):
        resp = client.get("/api/disease-outbreaks")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_outbreak(self, client):
        resp = client.get(f"/api/disease-outbreaks/{self._oid}")
        assert resp.status_code == 200
        assert resp.json()["disease"] == "API Test Virus"

    def test_get_outbreak_missing(self, client):
        resp = client.get("/api/disease-outbreaks/nonexistent")
        assert resp.status_code == 404

    def test_get_spread(self, client):
        resp = client.get(f"/api/disease-outbreaks/{self._oid}/spread")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) >= 30

    def test_get_spread_with_day(self, client):
        resp = client.get(f"/api/disease-outbreaks/{self._oid}/spread?day=5")
        assert resp.status_code == 200
        for f in resp.json()["features"]:
            assert f["properties"]["day_offset"] <= 5

    def test_get_spread_missing(self, client):
        resp = client.get("/api/disease-outbreaks/nonexistent/spread")
        assert resp.status_code == 404


# ─── Storm Tracking API ───────────────────────────────────

class TestStormTrackingAPI:
    _sid = None

    def test_seed_storms(self, client):
        resp = client.post("/api/storms/seed")
        assert resp.status_code == 200
        assert resp.json()["seeded"] >= 0

    def test_create_storm(self, client):
        resp = client.post("/api/storms", json={
            "storm_name": "API Test Storm",
            "storm_type": "hurricane",
            "category": 4,
            "max_wind_kts": 140,
        })
        assert resp.status_code == 200
        TestStormTrackingAPI._sid = resp.json()["id"]
        assert resp.json()["category"] == 4

    def test_list_storms(self, client):
        resp = client.get("/api/storms")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_storm(self, client):
        resp = client.get(f"/api/storms/{self._sid}")
        assert resp.status_code == 200
        assert resp.json()["storm_name"] == "API Test Storm"

    def test_get_storm_missing(self, client):
        resp = client.get("/api/storms/nonexistent")
        assert resp.status_code == 404

    def test_get_track_empty(self, client):
        resp = client.get(f"/api/storms/{self._sid}/track")
        assert resp.status_code == 200
        assert resp.json()["type"] == "FeatureCollection"

    def test_get_track_missing(self, client):
        resp = client.get("/api/storms/nonexistent/track")
        assert resp.status_code == 404


# ─── Conflict Progression API ─────────────────────────────

class TestConflictProgressionAPI:
    _pid = None

    def test_seed_progressions(self, client):
        resp = client.post("/api/conflict-progressions/seed")
        assert resp.status_code == 200
        assert resp.json()["seeded"] >= 0

    def test_create_progression(self, client):
        resp = client.post("/api/conflict-progressions", json={
            "conflict_name": "API Test Conflict",
            "region": "Test Region",
            "start_date": "2024-01-01",
        })
        assert resp.status_code == 200
        TestConflictProgressionAPI._pid = resp.json()["id"]

    def test_list_progressions(self, client):
        resp = client.get("/api/conflict-progressions")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_progression(self, client):
        resp = client.get(f"/api/conflict-progressions/{self._pid}")
        assert resp.status_code == 200
        assert resp.json()["conflict_name"] == "API Test Conflict"

    def test_get_progression_missing(self, client):
        resp = client.get("/api/conflict-progressions/nonexistent")
        assert resp.status_code == 404

    def test_get_steps_empty(self, client):
        resp = client.get(f"/api/conflict-progressions/{self._pid}/steps")
        assert resp.status_code == 200
        assert len(resp.json()["steps"]) == 0

    def test_get_steps_missing(self, client):
        resp = client.get("/api/conflict-progressions/nonexistent/steps")
        assert resp.status_code == 404

    def test_step_geojson(self, client):
        resp = client.get(f"/api/conflict-progressions/{self._pid}/steps/1/geojson")
        assert resp.status_code == 200
        assert resp.json()["type"] == "FeatureCollection"

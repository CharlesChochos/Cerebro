"""
API Tests — Phase 14: satellite orbits, monitored location beacons,
country extrusions for 3D immersive visualization.
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


# ─── Satellite Orbits API ────────────────────────────────────

class TestSatelliteAPI:
    _sid = None

    def test_seed_satellites(self, client):
        resp = client.post("/api/satellites/seed")
        assert resp.status_code == 200
        assert resp.json()["seeded"] >= 10

    def test_add_satellite(self, client):
        resp = client.post("/api/satellites", json={
            "norad_id": 88888,
            "name": "API-TEST-SAT",
            "category": "comms",
            "country_code": "US",
            "inclination": 53.0,
            "period_min": 95.0,
            "apogee_km": 550,
            "perigee_km": 540,
        })
        assert resp.status_code == 200
        TestSatelliteAPI._sid = resp.json()["satellite_id"]

    def test_list_satellites(self, client):
        resp = client.get("/api/satellites")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 10

    def test_list_by_category(self, client):
        resp = client.get("/api/satellites?category=military")
        assert resp.status_code == 200
        for s in resp.json()["satellites"]:
            assert s["category"] == "military"

    def test_get_satellite(self, client):
        resp = client.get(f"/api/satellites/{self._sid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "API-TEST-SAT"

    def test_get_by_norad(self, client):
        resp = client.get("/api/satellites/norad/25544")
        assert resp.status_code == 200
        assert "ISS" in resp.json()["name"]

    def test_get_nonexistent(self, client):
        resp = client.get("/api/satellites/nonexistent")
        assert resp.status_code == 404

    def test_orbit_geojson(self, client):
        resp = client.get("/api/satellites/orbits/geojson")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) >= 5

    def test_predict_passes(self, client):
        resp = client.get("/api/satellites/passes?norad_id=25544&lat=40.7&lng=-74.0")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["passes"], list)

    def test_predict_passes_out_of_range(self, client):
        resp = client.get("/api/satellites/passes?norad_id=25544&lat=85.0&lng=0.0")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ─── Monitored Location Beacons API ─────────────────────────

class TestBeaconAPI:
    _lid = None

    def test_seed_locations(self, client):
        resp = client.post("/api/beacons/seed")
        assert resp.status_code == 200
        assert resp.json()["seeded"] >= 10

    def test_add_location(self, client):
        resp = client.post("/api/beacons", json={
            "name": "API Test Beacon",
            "latitude": 34.0,
            "longitude": 44.0,
            "location_type": "embassy",
            "country_code": "IQ",
            "alert_level": "elevated",
        })
        assert resp.status_code == 200
        TestBeaconAPI._lid = resp.json()["location_id"]

    def test_add_invalid_type(self, client):
        resp = client.post("/api/beacons", json={
            "name": "Bad",
            "latitude": 0,
            "longitude": 0,
            "location_type": "invalid_type",
        })
        assert resp.status_code == 400

    def test_list_locations(self, client):
        resp = client.get("/api/beacons")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 10

    def test_list_by_type(self, client):
        resp = client.get("/api/beacons?location_type=nuclear")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_location(self, client):
        resp = client.get(f"/api/beacons/{self._lid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "API Test Beacon"

    def test_get_nonexistent(self, client):
        resp = client.get("/api/beacons/nonexistent")
        assert resp.status_code == 404

    def test_update_alert(self, client):
        resp = client.put(f"/api/beacons/{self._lid}/alert", json={
            "alert_level": "critical",
        })
        assert resp.status_code == 200
        # Verify
        resp = client.get(f"/api/beacons/{self._lid}")
        assert resp.json()["alert_level"] == "critical"
        assert resp.json()["pulse_rate"] == 0.5

    def test_update_invalid_alert(self, client):
        resp = client.put(f"/api/beacons/{self._lid}/alert", json={
            "alert_level": "extreme",
        })
        assert resp.status_code == 400

    def test_record_event(self, client):
        resp = client.post(f"/api/beacons/{self._lid}/event")
        assert resp.status_code == 200
        assert resp.json()["recorded"] is True

    def test_beacon_geojson(self, client):
        resp = client.get("/api/beacons/geojson")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) >= 10

    def test_beacon_geojson_filtered(self, client):
        resp = client.get("/api/beacons/geojson?alert_level=critical")
        assert resp.status_code == 200
        for f in resp.json()["features"]:
            assert f["properties"]["alert_level"] == "critical"


# ─── Country Extrusions API ─────────────────────────────────

class TestExtrusionAPI:

    def test_seed_extrusions(self, client):
        resp = client.post("/api/extrusions/seed")
        assert resp.status_code == 200
        assert resp.json()["seeded"] >= 15

    def test_upsert_metric(self, client):
        resp = client.post("/api/extrusions", json={
            "country_code": "JP",
            "metric_name": "event_count",
            "metric_value": 300,
            "normalized": 0.20,
        })
        assert resp.status_code == 200
        assert "extrusion_id" in resp.json()

    def test_upsert_update(self, client):
        resp = client.post("/api/extrusions", json={
            "country_code": "JP",
            "metric_name": "event_count",
            "metric_value": 350,
            "normalized": 0.24,
        })
        assert resp.status_code == 200

    def test_upsert_invalid_metric(self, client):
        resp = client.post("/api/extrusions", json={
            "country_code": "US",
            "metric_name": "invalid_metric",
            "metric_value": 100,
        })
        assert resp.status_code == 400

    def test_list_metrics(self, client):
        resp = client.get("/api/extrusions")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 15

    def test_list_by_metric(self, client):
        resp = client.get("/api/extrusions?metric_name=risk_score")
        assert resp.status_code == 200
        for m in resp.json()["metrics"]:
            assert m["metric_name"] == "risk_score"

    def test_extrusion_data(self, client):
        resp = client.get("/api/extrusions/data/event_count")
        assert resp.status_code == 200
        data = resp.json()
        assert data["metric"] == "event_count"
        assert len(data["data"]) >= 5

    def test_rankings(self, client):
        resp = client.get("/api/extrusions/rankings/risk_score?top_n=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["rankings"]) <= 5
        assert data["rankings"][0]["rank"] == 1

    def test_normalize(self, client):
        resp = client.post("/api/extrusions/normalize/event_count")
        assert resp.status_code == 200
        assert resp.json()["normalized"] >= 5

    def test_get_metric(self, client):
        resp = client.get("/api/extrusions/US/event_count")
        assert resp.status_code == 200
        assert resp.json()["country_code"] == "US"

    def test_get_metric_missing(self, client):
        resp = client.get("/api/extrusions/ZZ/event_count")
        assert resp.status_code == 404

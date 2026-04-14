"""
API Tests — Maritime zones, elevation, vegetation, predictions,
smart clustering, heatmaps, data lineage.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta

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
        db = get_db()
        now = datetime.now(timezone.utc)

        # Seed geo events
        locations = [
            (33.0, 44.0, "IQ", "Middle East"),
            (33.1, 44.1, "IQ", "Middle East"),
            (33.2, 44.2, "IQ", "Middle East"),
            (33.3, 44.0, "IQ", "Middle East"),
            (48.8, 2.3, "FR", "Western Europe"),
            (48.9, 2.4, "FR", "Western Europe"),
        ]
        for idx, (lat, lng, cc, region) in enumerate(locations):
            for day in range(14):
                eid = f"evt-glapi-{idx}-{day}"
                ts = (now - timedelta(days=day)).isoformat()
                sev = 40 + idx * 5 + day % 20
                db.execute(
                    """INSERT OR IGNORE INTO events
                       (id, source, title, category, severity,
                        latitude, longitude, country_code, region, timestamp, summary)
                       VALUES (?, 'test', ?, 'military', ?, ?, ?, ?, ?, ?, ?)""",
                    (eid, f"GL API event {idx}-{day}", min(sev, 100),
                     lat, lng, cc, region, ts, f"Summary {idx}-{day}"),
                )

        # Seed a vegetation reading
        db.execute(
            """INSERT OR IGNORE INTO vegetation_readings
               (id, lat, lng, ndvi, baseline_ndvi, change_pct, classification,
                capture_date, country_code, region)
               VALUES ('veg-api-1', 33.0, 44.0, 0.12, 0.4, -70.0, 'stressed',
                       '2026-04-01', 'IQ', 'Middle East')"""
        )

        db.commit()
        yield c
    os.unlink(_test_db_path)


# ─── Maritime Zones API ──────────────────────────────────────

class TestMaritimeAPI:
    def test_list_zones(self, client):
        resp = client.get("/api/maritime/zones")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 10

    def test_list_zones_by_type(self, client):
        resp = client.get("/api/maritime/zones?zone_type=chokepoint")
        data = resp.json()
        assert all(z["zone_type"] == "chokepoint" for z in data["zones"])

    def test_get_geojson(self, client):
        resp = client.get("/api/maritime/zones/geojson")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) >= 10

    def test_get_zone(self, client):
        resp = client.get("/api/maritime/zones/mz-hormuz")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Strait of Hormuz"

    def test_get_zone_not_found(self, client):
        resp = client.get("/api/maritime/zones/nonexistent")
        assert resp.status_code == 404

    def test_create_zone(self, client):
        resp = client.post("/api/maritime/zones", json={
            "name": "API Test Zone",
            "zone_type": "eez",
            "polygon": [[10, 20], [11, 20], [11, 21], [10, 21], [10, 20]],
        })
        assert resp.status_code == 200
        assert "zone_id" in resp.json()

    def test_lookup_point(self, client):
        resp = client.get("/api/maritime/lookup?lat=26.5&lng=56.2")
        assert resp.status_code == 200
        data = resp.json()
        assert any(z["id"] == "mz-hormuz" for z in data["zones"])


# ─── Elevation API ───────────────────────────────────────────

class TestElevationAPI:
    def test_create_profile(self, client):
        resp = client.post("/api/elevation/profile", json={
            "points": [[28.0, 85.0], [29.0, 86.0]],
            "num_samples": 10,
            "name": "API Test Profile",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "profile_id" in data
        assert len(data["points"]) == 10
        assert data["total_distance_km"] > 0

    def test_create_profile_too_few_points(self, client):
        resp = client.post("/api/elevation/profile", json={"points": [[0, 0]]})
        assert resp.status_code == 400

    def test_list_profiles(self, client):
        resp = client.get("/api/elevation/profiles")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_profile(self, client):
        profiles = client.get("/api/elevation/profiles").json()["profiles"]
        pid = profiles[0]["id"]
        resp = client.get(f"/api/elevation/profiles/{pid}")
        assert resp.status_code == 200
        assert len(resp.json()["points"]) > 0

    def test_get_profile_not_found(self, client):
        resp = client.get("/api/elevation/profiles/nonexistent")
        assert resp.status_code == 404


# ─── Vegetation API ──────────────────────────────────────────

class TestVegetationAPI:
    def test_add_reading(self, client):
        resp = client.post("/api/vegetation/readings", json={
            "lat": 34.0, "lng": 45.0, "ndvi": 0.55,
            "baseline_ndvi": 0.5, "country_code": "IQ",
        })
        assert resp.status_code == 200
        assert "reading_id" in resp.json()

    def test_list_readings(self, client):
        resp = client.get("/api/vegetation/readings?country_code=IQ")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_vegetation_geojson(self, client):
        resp = client.get("/api/vegetation/geojson")
        assert resp.status_code == 200
        assert resp.json()["type"] == "FeatureCollection"

    def test_vegetation_anomalies(self, client):
        resp = client.get("/api/vegetation/anomalies?threshold=-20")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["anomalies"], list)


# ─── Predictive Positioning API ──────────────────────────────

class TestPredictionsAPI:
    def test_run_scan(self, client):
        resp = client.post("/api/predictive/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_predictions"] >= 1

    def test_list_predictions(self, client):
        resp = client.get("/api/predictive/positions?active_only=false")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_predictions_geojson(self, client):
        resp = client.get("/api/predictive/geojson")
        assert resp.status_code == 200
        assert resp.json()["type"] == "FeatureCollection"

    def test_hotspots(self, client):
        resp = client.get("/api/predictive/hotspots")
        assert resp.status_code == 200
        assert len(resp.json()["hotspots"]) >= 1

    def test_escalation_zones(self, client):
        resp = client.get("/api/predictive/escalation-zones")
        assert resp.status_code == 200
        assert isinstance(resp.json()["zones"], list)


# ─── Smart Clustering API ────────────────────────────────────

class TestClusteringAPI:
    def test_density_grid(self, client):
        resp = client.get("/api/clusters/density?days=14")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cells"] >= 1
        assert data["grid_size_deg"] == 2.0

    def test_density_with_category(self, client):
        resp = client.get("/api/clusters/density?category=military&days=14")
        assert resp.status_code == 200


# ─── Heatmap API ─────────────────────────────────────────────

class TestHeatmapAPI:
    def test_heatmap_data(self, client):
        resp = client.get("/api/heatmap/data?days=14")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert "lat" in data["points"][0]
        assert "severity" in data["points"][0]

    def test_heatmap_by_category(self, client):
        resp = client.get("/api/heatmap/data?category=military&days=14")
        assert resp.status_code == 200


# ─── Data Lineage API ────────────────────────────────────────

class TestLineageAPI:
    def test_create_lineage(self, client):
        resp = client.post("/api/lineage", json={
            "entity_type": "event",
            "entity_id": "evt-glapi-0-0",
            "action": "created",
            "actor": "ingestion",
            "details": {"source": "test"},
        })
        assert resp.status_code == 200
        assert "lineage_id" in resp.json()

    def test_create_lineage_chain(self, client):
        r1 = client.post("/api/lineage", json={
            "entity_type": "event", "entity_id": "evt-glapi-1-0",
            "action": "created", "actor": "ingestion",
        }).json()
        r2 = client.post("/api/lineage", json={
            "entity_type": "event", "entity_id": "evt-glapi-1-0",
            "action": "classified", "actor": "classifier",
            "parent_lineage_id": r1["lineage_id"],
        }).json()
        assert r2["lineage_id"] is not None

    def test_get_entity_lineage(self, client):
        resp = client.get("/api/lineage/event/evt-glapi-1-0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2

    def test_list_lineage(self, client):
        resp = client.get("/api/lineage?hours=24")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 2

    def test_lineage_stats(self, client):
        resp = client.get("/api/lineage/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_entries"] >= 1

    def test_trace_sources(self, client):
        resp = client.get("/api/lineage/trace/event/evt-glapi-1-0")
        assert resp.status_code == 200
        assert resp.json()["entity_type"] == "event"

    def test_get_entry(self, client):
        entries = client.get("/api/lineage?hours=24").json()["entries"]
        lid = entries[0]["id"]
        resp = client.get(f"/api/lineage/entry/{lid}")
        assert resp.status_code == 200

    def test_get_entry_not_found(self, client):
        resp = client.get("/api/lineage/entry/nonexistent")
        assert resp.status_code == 404

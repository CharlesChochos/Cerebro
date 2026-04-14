"""
API Tests — Phase 13: webcam feeds, trade flows, conflict frontlines,
map annotations, street imagery, animation export.
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


# ─── Webcam Feeds API ─────────────────────────────────────

class TestWebcamAPI:
    _wid = None

    def test_seed_webcams(self, client):
        resp = client.post("/api/webcams/seed")
        assert resp.status_code == 200

    def test_list_webcams(self, client):
        resp = client.get("/api/webcams")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 10

    def test_add_webcam(self, client):
        resp = client.post("/api/webcams", json={
            "title": "API Test Cam",
            "latitude": 51.5,
            "longitude": -0.1,
            "country_code": "GB",
            "category": "landscape",
        })
        assert resp.status_code == 200
        TestWebcamAPI._wid = resp.json()["webcam_id"]

    def test_get_webcam(self, client):
        resp = client.get(f"/api/webcams/{self._wid}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "API Test Cam"

    def test_geojson(self, client):
        resp = client.get("/api/webcams/geojson")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) >= 10

    def test_near(self, client):
        resp = client.get("/api/webcams/near?lat=41.0&lng=29.0&radius=2.0")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_by_category(self, client):
        resp = client.get("/api/webcams?category=port")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_nonexistent(self, client):
        resp = client.get("/api/webcams/nonexistent")
        assert resp.status_code == 404


# ─── Trade Flows API ──────────────────────────────────────

class TestTradeFlowAPI:
    _tid = None

    def test_seed_flows(self, client):
        resp = client.post("/api/trade-flows/seed")
        assert resp.status_code == 200

    def test_list_flows(self, client):
        resp = client.get("/api/trade-flows")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 10

    def test_add_flow(self, client):
        resp = client.post("/api/trade-flows", json={
            "origin_country": "KR",
            "dest_country": "US",
            "commodity": "electronics",
            "volume_usd": 30e9,
            "flow_type": "trade",
            "origin_lat": 37.6,
            "origin_lng": 127.0,
            "dest_lat": 40.7,
            "dest_lng": -74.0,
        })
        assert resp.status_code == 200
        TestTradeFlowAPI._tid = resp.json()["flow_id"]

    def test_get_flow(self, client):
        resp = client.get(f"/api/trade-flows/{self._tid}")
        assert resp.status_code == 200
        assert resp.json()["origin_country"] == "KR"

    def test_arcs(self, client):
        resp = client.get("/api/trade-flows/arcs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 10
        assert "origin" in data["flows"][0]
        assert "destination" in data["flows"][0]

    def test_arcs_filtered(self, client):
        resp = client.get("/api/trade-flows/arcs?flow_type=energy")
        assert resp.status_code == 200
        for f in resp.json()["flows"]:
            assert f["flow_type"] == "energy"

    def test_by_origin(self, client):
        resp = client.get("/api/trade-flows?origin_country=CN")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_nonexistent(self, client):
        resp = client.get("/api/trade-flows/nonexistent")
        assert resp.status_code == 404


# ─── Conflict Frontlines API ──────────────────────────────

class TestFrontlineAPI:
    _fid = None

    def test_add_frontline(self, client):
        resp = client.post("/api/frontlines", json={
            "conflict_name": "Syria-Civil",
            "date": "2025-06-01",
            "geometry_json": {
                "type": "LineString",
                "coordinates": [[36.0, 35.0], [37.0, 35.5], [38.0, 36.0]]
            },
            "country_code": "SY",
            "side_a": "SAA",
            "side_b": "SDF",
            "status": "active",
        })
        assert resp.status_code == 200
        TestFrontlineAPI._fid = resp.json()["frontline_id"]

    def test_get_frontline(self, client):
        resp = client.get(f"/api/frontlines/{self._fid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["conflict_name"] == "Syria-Civil"

    def test_add_multiple_for_animation(self, client):
        for i in range(3):
            client.post("/api/frontlines", json={
                "conflict_name": "Syria-Civil",
                "date": f"2025-06-{2 + i:02d}",
                "geometry_json": {
                    "type": "LineString",
                    "coordinates": [[36.0 + i * 0.1, 35.0], [37.0 + i * 0.1, 35.5]]
                },
                "country_code": "SY",
                "side_a": "SAA",
                "side_b": "SDF",
            })

    def test_list_frontlines(self, client):
        resp = client.get("/api/frontlines?conflict_name=Syria-Civil")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 4

    def test_geojson(self, client):
        resp = client.get("/api/frontlines/geojson")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"

    def test_animation(self, client):
        resp = client.get("/api/frontlines/animate/Syria-Civil")
        assert resp.status_code == 200
        data = resp.json()
        assert data["frame_count"] >= 4
        dates = [f["date"] for f in data["frames"]]
        assert dates == sorted(dates)

    def test_get_nonexistent(self, client):
        resp = client.get("/api/frontlines/nonexistent")
        assert resp.status_code == 404


# ─── Map Annotations API ──────────────────────────────────

class TestAnnotationAPI:
    _aid = None

    def test_create_marker(self, client):
        resp = client.post("/api/annotations", json={
            "annotation_type": "marker",
            "geometry_json": {"type": "Point", "coordinates": [44.0, 33.0]},
            "properties_json": {"color": "#ef4444"},
            "title": "Observation Point",
            "created_by": "api-test",
            "layer_name": "recon",
        })
        assert resp.status_code == 200
        TestAnnotationAPI._aid = resp.json()["annotation_id"]

    def test_create_polygon(self, client):
        resp = client.post("/api/annotations", json={
            "annotation_type": "polygon",
            "geometry_json": {
                "type": "Polygon",
                "coordinates": [[[44.0, 33.0], [44.5, 33.0], [44.5, 33.5], [44.0, 33.5], [44.0, 33.0]]]
            },
            "title": "Exclusion Zone",
            "layer_name": "recon",
        })
        assert resp.status_code == 200

    def test_get_annotation(self, client):
        resp = client.get(f"/api/annotations/{self._aid}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Observation Point"

    def test_list_annotations(self, client):
        resp = client.get("/api/annotations")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 2

    def test_list_by_layer(self, client):
        resp = client.get("/api/annotations?layer_name=recon")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 2

    def test_geojson(self, client):
        resp = client.get("/api/annotations/geojson")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"

    def test_layers(self, client):
        resp = client.get("/api/annotations/layers")
        assert resp.status_code == 200
        layers = resp.json()["layers"]
        names = [l["layer_name"] for l in layers]
        assert "recon" in names

    def test_update(self, client):
        resp = client.put(f"/api/annotations/{self._aid}", json={
            "title": "Updated Point",
        })
        assert resp.status_code == 200
        assert resp.json()["updated"] is True

    def test_delete(self, client):
        # Create then delete
        resp = client.post("/api/annotations", json={
            "annotation_type": "marker",
            "geometry_json": {"type": "Point", "coordinates": [0, 0]},
            "title": "Temp",
        })
        aid = resp.json()["annotation_id"]
        resp = client.delete(f"/api/annotations/{aid}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_get_nonexistent(self, client):
        resp = client.get("/api/annotations/nonexistent")
        assert resp.status_code == 404


# ─── Street Imagery API ───────────────────────────────────

class TestStreetImageryAPI:
    _sid = None

    def test_store_image(self, client):
        resp = client.post("/api/street-imagery", json={
            "image_id": "api_mapillary_001",
            "latitude": 50.45,
            "longitude": 30.52,
            "compass_angle": 90.0,
            "captured_at": "2025-04-01T12:00:00Z",
            "thumbnail_url": "https://mapillary.com/thumb/001",
            "full_url": "https://mapillary.com/full/001",
        })
        assert resp.status_code == 200
        TestStreetImageryAPI._sid = resp.json()["record_id"]

    def test_get_image(self, client):
        resp = client.get(f"/api/street-imagery/{self._sid}")
        assert resp.status_code == 200
        assert resp.json()["image_id"] == "api_mapillary_001"

    def test_list_images(self, client):
        resp = client.get("/api/street-imagery")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_geojson(self, client):
        resp = client.get("/api/street-imagery/geojson?lat=50.45&lng=30.52&radius=1.0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"

    def test_near(self, client):
        resp = client.get("/api/street-imagery/near?lat=50.45&lng=30.52&radius=0.1")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_nonexistent(self, client):
        resp = client.get("/api/street-imagery/nonexistent")
        assert resp.status_code == 404


# ─── Animation Export API ──────────────────────────────────

class TestAnimExportAPI:
    _eid = None

    def test_create_job(self, client):
        resp = client.post("/api/exports/animation", json={
            "export_type": "gif",
            "parameters": {"center": [44, 33], "zoom": 5, "fps": 15},
            "duration_secs": 5.0,
            "frame_count": 75,
        })
        assert resp.status_code == 200
        TestAnimExportAPI._eid = resp.json()["job_id"]

    def test_get_job(self, client):
        resp = client.get(f"/api/exports/animation/{self._eid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["export_type"] == "gif"
        assert data["status"] == "pending"

    def test_list_jobs(self, client):
        resp = client.get("/api/exports/animation")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_update_rendering(self, client):
        resp = client.put(f"/api/exports/animation/{self._eid}", json={
            "status": "rendering",
        })
        assert resp.status_code == 200

    def test_update_completed(self, client):
        resp = client.put(f"/api/exports/animation/{self._eid}", json={
            "status": "completed",
            "output_path": "/exports/test.gif",
            "file_size": 1500000,
        })
        assert resp.status_code == 200

    def test_update_invalid(self, client):
        resp = client.put(f"/api/exports/animation/{self._eid}", json={
            "status": "invalid_status",
        })
        assert resp.status_code == 400

    def test_get_nonexistent(self, client):
        resp = client.get("/api/exports/animation/nonexistent")
        assert resp.status_code == 404

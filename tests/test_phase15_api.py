"""
API Tests — Phase 15: photo pins, EXIF check, event enrichment.
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


# ─── Photo Pins API ─────────────────────────────────────────

class TestPhotoPinAPI:
    _pid = None

    def test_add_pin(self, client):
        resp = client.post("/api/photo-pins", json={
            "source_url": "https://reuters.com/article/photo1",
            "latitude": 33.3,
            "longitude": 44.4,
            "title": "Baghdad photo",
            "country_code": "IQ",
        })
        assert resp.status_code == 200
        data = resp.json()
        TestPhotoPinAPI._pid = data["pin_id"]
        assert data["exif_mismatch"] is False

    def test_add_more_pins(self, client):
        for title, lat, lng, cc in [
            ("Kyiv photo", 50.4, 30.5, "UA"),
            ("Tokyo photo", 35.7, 139.7, "JP"),
        ]:
            client.post("/api/photo-pins", json={
                "source_url": f"https://news.com/{cc}",
                "latitude": lat, "longitude": lng,
                "title": title, "country_code": cc,
            })

    def test_list_pins(self, client):
        resp = client.get("/api/photo-pins")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 3

    def test_list_by_country(self, client):
        resp = client.get("/api/photo-pins?country_code=IQ")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_pin(self, client):
        resp = client.get(f"/api/photo-pins/{self._pid}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Baghdad photo"

    def test_get_nonexistent(self, client):
        resp = client.get("/api/photo-pins/nonexistent")
        assert resp.status_code == 404

    def test_geojson(self, client):
        resp = client.get("/api/photo-pins/geojson")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) >= 3

    def test_mismatches(self, client):
        resp = client.get("/api/photo-pins/mismatches")
        assert resp.status_code == 200
        assert isinstance(resp.json()["mismatches"], list)


# ─── EXIF Check API ─────────────────────────────────────────

class TestExifAPI:

    def test_check_mismatch_close(self, client):
        resp = client.post("/api/exif/check-mismatch", json={
            "claimed_lat": 33.3, "claimed_lng": 44.4,
            "exif_lat": 33.31, "exif_lng": 44.41,
        })
        assert resp.status_code == 200
        assert resp.json()["mismatch"] is False

    def test_check_mismatch_far(self, client):
        resp = client.post("/api/exif/check-mismatch", json={
            "claimed_lat": 33.3, "claimed_lng": 44.4,
            "exif_lat": 50.0, "exif_lng": 30.0,
        })
        assert resp.status_code == 200
        assert resp.json()["mismatch"] is True

    def test_check_custom_threshold(self, client):
        resp = client.post("/api/exif/check-mismatch", json={
            "claimed_lat": 33.3, "claimed_lng": 44.4,
            "exif_lat": 33.5, "exif_lng": 44.6,
            "threshold_km": 5.0,
        })
        assert resp.status_code == 200
        assert resp.json()["threshold_km"] == 5.0


# ─── Event Enrichment API ───────────────────────────────────

class TestEnrichmentAPI:

    def test_enrichment_stats(self, client):
        resp = client.get("/api/enrichment/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_events_with_coords" in data
        assert "enriched" in data

    def test_batch_enrich(self, client):
        resp = client.post("/api/enrichment/batch?limit=10")
        assert resp.status_code == 200
        assert "enriched" in resp.json()

    def test_enrich_nonexistent_event(self, client):
        resp = client.post("/api/enrichment/enrich/nonexistent")
        assert resp.status_code == 404

    def test_get_enrichment_nonexistent(self, client):
        resp = client.get("/api/enrichment/nonexistent-event")
        assert resp.status_code == 404

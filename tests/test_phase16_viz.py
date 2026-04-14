"""
Tests — Phase 16: Radar coverage, drone/UAV activity, vessel/flight visualization.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from detection.radar_coverage import (
    get_radar_coverage_geojson, list_radar_types, RADAR_INSTALLATIONS,
)
from detection.drone_tracking import (
    get_drone_activity_geojson, list_drone_categories, list_drone_operators,
    DRONE_ZONES,
)


# ─── Radar Coverage Module Tests ──────────────────────────

class TestRadarCoverage:

    def test_geojson_all(self):
        geo = get_radar_coverage_geojson()
        assert geo["type"] == "FeatureCollection"
        # Each installation produces 2 features (coverage + station)
        assert len(geo["features"]) == len(RADAR_INSTALLATIONS) * 2

    def test_geojson_filter_by_type(self):
        geo = get_radar_coverage_geojson(radar_type="missile_defense")
        for f in geo["features"]:
            assert f["properties"]["radar_type"] == "missile_defense"

    def test_coverage_polygon(self):
        geo = get_radar_coverage_geojson()
        coverages = [f for f in geo["features"]
                     if f["properties"]["type"] == "coverage"]
        assert len(coverages) >= 1
        assert coverages[0]["geometry"]["type"] == "Polygon"
        assert len(coverages[0]["geometry"]["coordinates"][0]) >= 10

    def test_station_points(self):
        geo = get_radar_coverage_geojson()
        stations = [f for f in geo["features"]
                    if f["properties"]["type"] == "station"]
        assert len(stations) == len(RADAR_INSTALLATIONS)
        for s in stations:
            assert s["geometry"]["type"] == "Point"

    def test_has_color(self):
        geo = get_radar_coverage_geojson()
        for f in geo["features"]:
            assert "color" in f["properties"]

    def test_list_types(self):
        types = list_radar_types()
        assert "early_warning" in types
        assert "missile_defense" in types
        assert "air_defense" in types

    def test_filter_returns_empty_for_unknown(self):
        geo = get_radar_coverage_geojson(radar_type="nonexistent")
        assert len(geo["features"]) == 0


# ─── Drone/UAV Module Tests ──────────────────────────────

class TestDroneTracking:

    def test_geojson_all(self):
        geo = get_drone_activity_geojson()
        assert geo["type"] == "FeatureCollection"
        # Each zone produces 3 features (patrol_radius + marker + label)
        assert len(geo["features"]) == len(DRONE_ZONES) * 3

    def test_filter_by_category(self):
        geo = get_drone_activity_geojson(category="combat")
        for f in geo["features"]:
            assert f["properties"]["category"] == "combat"

    def test_filter_by_status(self):
        geo = get_drone_activity_geojson(status="active")
        for f in geo["features"]:
            assert f["properties"]["status"] == "active"

    def test_patrol_radius_polygon(self):
        geo = get_drone_activity_geojson()
        patrols = [f for f in geo["features"]
                   if f["properties"]["type"] == "patrol_radius"]
        assert len(patrols) >= 1
        assert patrols[0]["geometry"]["type"] == "Polygon"
        assert len(patrols[0]["geometry"]["coordinates"][0]) >= 10

    def test_diamond_marker(self):
        geo = get_drone_activity_geojson()
        markers = [f for f in geo["features"]
                   if f["properties"]["type"] == "drone_marker"]
        assert len(markers) == len(DRONE_ZONES)
        # Diamond should have 5 coords (4 points + close)
        assert len(markers[0]["geometry"]["coordinates"][0]) == 5

    def test_drone_labels(self):
        geo = get_drone_activity_geojson()
        labels = [f for f in geo["features"]
                  if f["properties"]["type"] == "drone_label"]
        assert len(labels) == len(DRONE_ZONES)
        for l in labels:
            assert l["geometry"]["type"] == "Point"

    def test_list_categories(self):
        cats = list_drone_categories()
        assert "reconnaissance" in cats
        assert "combat" in cats

    def test_list_operators(self):
        ops = list_drone_operators()
        assert "USAF" in ops
        assert len(ops) >= 3

    def test_filter_returns_empty_for_unknown(self):
        geo = get_drone_activity_geojson(category="nonexistent")
        assert len(geo["features"]) == 0


# ─── API Tests ────────────────────────────────────────────

_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["CEREBRO_DB_PATH"] = _test_db_path

from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
    os.unlink(_test_db_path)


class TestRadarAPI:

    def test_get_coverage(self, client):
        resp = client.get("/api/radar/coverage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) >= 2

    def test_get_coverage_filtered(self, client):
        resp = client.get("/api/radar/coverage?radar_type=missile_defense")
        assert resp.status_code == 200
        for f in resp.json()["features"]:
            assert f["properties"]["radar_type"] == "missile_defense"

    def test_get_types(self, client):
        resp = client.get("/api/radar/types")
        assert resp.status_code == 200
        assert len(resp.json()["types"]) >= 3


class TestDroneAPI:

    def test_get_activity(self, client):
        resp = client.get("/api/drones/activity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) >= 3

    def test_get_activity_filtered(self, client):
        resp = client.get("/api/drones/activity?category=combat")
        assert resp.status_code == 200
        for f in resp.json()["features"]:
            assert f["properties"]["category"] == "combat"

    def test_get_categories(self, client):
        resp = client.get("/api/drones/categories")
        assert resp.status_code == 200
        assert "combat" in resp.json()["categories"]

    def test_get_operators(self, client):
        resp = client.get("/api/drones/operators")
        assert resp.status_code == 200
        assert len(resp.json()["operators"]) >= 3

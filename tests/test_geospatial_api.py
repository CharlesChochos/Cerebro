"""
API tests for geospatial endpoints — geofences, measurements, weapons, KML, trajectories.
"""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from api.main import app, get_db


@pytest.fixture(scope="module")
def client():
    """Create test client and seed geospatial data."""
    with TestClient(app) as c:
        conn = get_db()

        # Seed events with coordinates
        for i, (lat, lng, title) in enumerate([
            (34.0, 35.0, "Beirut activity"),
            (50.4, 30.5, "Kyiv event"),
            (38.9, -77.0, "DC event"),
            (0.0, 0.0, "Equator event"),
        ]):
            conn.execute(
                """INSERT OR IGNORE INTO events
                   (id, source, title, category, severity, confidence,
                    latitude, longitude, timestamp)
                   VALUES (?, 'test', ?, 'military', ?, 0.8, ?, ?, datetime('now'))""",
                (f"geo-adv-{i}", title, 60 + i * 10, lat, lng),
            )

        # Seed a geofence (square around Middle East)
        fence_id = str(uuid.uuid4())
        polygon = {"type": "Polygon", "coordinates": [[[30, 25], [40, 25], [40, 38], [30, 38], [30, 25]]]}
        conn.execute(
            """INSERT OR IGNORE INTO geofences
               (id, name, description, polygon_json, bbox_west, bbox_south, bbox_east, bbox_north,
                category, active)
               VALUES (?, 'Middle East Zone', 'Test fence', ?, 30, 25, 40, 38, 'military', 1)""",
            (fence_id, json.dumps(polygon)),
        )

        # Seed a weapons deployment
        dep_id = str(uuid.uuid4())
        conn.execute(
            """INSERT OR IGNORE INTO weapons_deployments
               (id, system_id, name, lat, lng, country_code, status, confidence, source)
               VALUES (?, 'ws-s400', 'Hmeimim AB', 35.41, 35.95, 'SY', 'active', 0.9, 'osint')""",
            (dep_id,),
        )

        # Seed a measurement
        conn.execute(
            """INSERT OR IGNORE INTO measurement_profiles
               (id, name, profile_type, points_json, total_distance_km)
               VALUES (?, 'Test Path', 'distance', ?, 150.5)""",
            (str(uuid.uuid4()), json.dumps([[34, 35], [35, 36]])),
        )

        conn.commit()
        c.fence_id = fence_id
        yield c


# ── Geofence Tests ─────────────────────────────────────────────────────────


def test_create_geofence(client):
    r = client.post("/api/geofences", json={
        "name": "Test Fence",
        "polygon": [[10, 20], [20, 20], [20, 30], [10, 30], [10, 20]],
        "category": "military",
    })
    assert r.status_code == 200
    assert "geofence_id" in r.json()


def test_create_geofence_too_few_points(client):
    r = client.post("/api/geofences", json={
        "name": "Bad",
        "polygon": [[0, 0], [1, 1]],
    })
    assert r.status_code == 400


def test_list_geofences(client):
    r = client.get("/api/geofences")
    assert r.status_code == 200
    data = r.json()
    assert len(data["geofences"]) >= 1


def test_get_geofence(client):
    r = client.get(f"/api/geofences/{client.fence_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "Middle East Zone"
    assert "polygon" in data


def test_geofence_not_found(client):
    r = client.get("/api/geofences/nonexistent")
    assert r.status_code == 404


def test_delete_geofence(client):
    # Create one to delete
    cr = client.post("/api/geofences", json={
        "name": "To Delete",
        "polygon": [[0, 0], [5, 0], [5, 5], [0, 5], [0, 0]],
    })
    fid = cr.json()["geofence_id"]
    r = client.delete(f"/api/geofences/{fid}")
    assert r.status_code == 200
    assert r.json()["deactivated"] == fid


def test_scan_geofences(client):
    r = client.post("/api/geofences/scan?hours=24")
    assert r.status_code == 200
    data = r.json()
    assert "events_scanned" in data
    assert "triggers" in data


# ── Measurement Tests ──────────────────────────────────────────────────────


def test_measure_distance(client):
    r = client.post("/api/measure/distance", json={
        "points": [[51.5074, -0.1278], [48.8566, 2.3522]],
    })
    assert r.status_code == 200
    data = r.json()
    assert 340 < data["total_distance_km"] < 350
    assert "initial_bearing_deg" in data
    assert len(data["segments"]) == 1


def test_measure_distance_multi_point(client):
    r = client.post("/api/measure/distance", json={
        "points": [[0, 0], [0, 1], [1, 1]],
    })
    assert r.status_code == 200
    assert len(r.json()["segments"]) == 2


def test_measure_distance_too_few_points(client):
    r = client.post("/api/measure/distance", json={"points": [[0, 0]]})
    assert r.status_code == 400


def test_measure_area(client):
    r = client.post("/api/measure/area", json={
        "polygon": [[0, 0], [0, 1], [1, 1], [1, 0]],
    })
    assert r.status_code == 200
    data = r.json()
    assert data["area_km2"] > 0
    assert data["perimeter_km"] > 0


def test_measure_area_too_few_points(client):
    r = client.post("/api/measure/area", json={"polygon": [[0, 0], [1, 1]]})
    assert r.status_code == 400


def test_save_measurement(client):
    r = client.post("/api/measurements", json={
        "name": "Test Measure",
        "profile_type": "distance",
        "points": [[34, 35], [35, 36], [36, 37]],
    })
    assert r.status_code == 200
    assert "measurement_id" in r.json()


def test_list_measurements(client):
    r = client.get("/api/measurements")
    assert r.status_code == 200
    assert len(r.json()["measurements"]) >= 1


# ── Weapons Systems Tests ─────────────────────────────────────────────────


def test_list_weapons(client):
    r = client.get("/api/weapons")
    assert r.status_code == 200
    data = r.json()
    assert len(data["weapons_systems"]) >= 10  # 10 seeded


def test_weapons_filter_type(client):
    r = client.get("/api/weapons?system_type=sam")
    assert r.status_code == 200
    data = r.json()
    assert all(s["system_type"] == "sam" for s in data["weapons_systems"])


def test_weapons_filter_country(client):
    r = client.get("/api/weapons?country_code=US")
    assert r.status_code == 200
    data = r.json()
    assert all(s["country_code"] == "US" for s in data["weapons_systems"])


def test_range_rings(client):
    r = client.get("/api/weapons/ws-s400/range-rings?lat=35.41&lng=35.95")
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) >= 2  # min_range + 50% + max
    assert data["system"]["name"] == "S-400 Triumf"


def test_range_rings_not_found(client):
    r = client.get("/api/weapons/nonexistent/range-rings?lat=0&lng=0")
    assert r.status_code == 404


# ── Deployments Tests ──────────────────────────────────────────────────────


def test_create_deployment(client):
    r = client.post("/api/deployments", json={
        "system_id": "ws-patriot",
        "lat": 50.4,
        "lng": 30.5,
        "name": "Kyiv PAC-3",
        "country_code": "UA",
        "confidence": 0.8,
    })
    assert r.status_code == 200
    assert "deployment_id" in r.json()


def test_create_deployment_bad_system(client):
    r = client.post("/api/deployments", json={
        "system_id": "nonexistent",
        "lat": 0, "lng": 0,
    })
    assert r.status_code == 404


def test_list_deployments(client):
    r = client.get("/api/deployments")
    assert r.status_code == 200
    data = r.json()
    assert len(data["deployments"]) >= 1


# ── Trajectory Tests ───────────────────────────────────────────────────────


def test_ballistic_trajectory(client):
    r = client.post("/api/trajectory", json={
        "launch_lat": 34, "launch_lng": 35,
        "target_lat": 50, "target_lng": 10,
        "trajectory_type": "ballistic",
        "max_altitude_km": 150,
        "num_points": 20,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["trajectory_type"] == "ballistic"
    assert len(data["points"]) == 21
    assert data["points"][0]["altitude_km"] == 0
    assert data["points"][-1]["altitude_km"] == 0


def test_cruise_trajectory(client):
    r = client.post("/api/trajectory", json={
        "launch_lat": 34, "launch_lng": 35,
        "target_lat": 38, "target_lng": 44,
        "trajectory_type": "cruise",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["trajectory_type"] == "cruise"
    assert all(p["altitude_km"] <= 0.06 for p in data["points"])


# ── KML Export Tests ───────────────────────────────────────────────────────


def test_export_events_kml(client):
    r = client.get("/api/export/events.kml")
    assert r.status_code == 200
    assert "application/vnd.google-earth.kml+xml" in r.headers["content-type"]
    assert "<kml" in r.text
    assert "Placemark" in r.text


def test_export_geofences_kml(client):
    r = client.get("/api/export/geofences.kml")
    assert r.status_code == 200
    assert "<kml" in r.text


def test_export_deployments_kml(client):
    r = client.get("/api/export/deployments.kml")
    assert r.status_code == 200
    assert "<kml" in r.text


def test_export_events_kmz(client):
    r = client.get("/api/export/events.kmz")
    assert r.status_code == 200
    assert "application/vnd.google-earth.kmz" in r.headers["content-type"]
    assert len(r.content) > 0

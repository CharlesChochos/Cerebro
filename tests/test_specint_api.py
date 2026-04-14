"""
Tests for SPECINT API endpoints:
satellite, fires, nightlights, outbreaks, weather.
"""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from api.main import app, get_db


@pytest.fixture(scope="module")
def client():
    """Create test client and seed SPECINT data."""
    with TestClient(app) as c:
        conn = get_db()

        # Seed satellite imagery
        sat_ids = []
        for i in range(3):
            sid = str(uuid.uuid4())
            sat_ids.append(sid)
            conn.execute(
                """INSERT INTO satellite_cache
                   (id, source, lat, lng, bbox_json, capture_date, cloud_cover,
                    thumbnail_url, resolution_m, annotations, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sid, "sentinel2", 35.0 + i, 33.0 + i,
                    json.dumps([32, 34, 34, 36]),
                    f"2025-01-{10+i}", 15.0 + i * 5,
                    f"https://thumb/{i}", 10.0,
                    json.dumps({"change_detected": i == 1}),
                    json.dumps({"area": "test"}),
                ),
            )

        # Seed fire detections
        for i in range(5):
            conn.execute(
                """INSERT INTO fire_detections
                   (id, lat, lng, brightness, frp, confidence, daynight,
                    capture_date, satellite)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()), 34.0 + i * 0.1, -118.0 + i * 0.1,
                    330.0 + i, 10.0 + i, "high" if i < 3 else "nominal",
                    "D", "2025-01-15", "NOAA-20",
                ),
            )

        # Seed nightlight readings
        for i in range(4):
            change = [-45, -25, 5, 35][i]
            conn.execute(
                """INSERT INTO nightlight_readings
                   (id, lat, lng, country_code, region, radiance,
                    baseline_radiance, change_pct, capture_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()), 30.0 + i, 45.0 + i,
                    ["VE", "SY", "US", "CN"][i], ["South America", "Middle East", "North America", "Asia"][i],
                    100 + change, 100, change, "2025-01-15",
                ),
            )

        # Seed disease outbreaks
        for i in range(3):
            conn.execute(
                """INSERT INTO disease_outbreaks
                   (id, source, disease, title, summary, country_code, region,
                    status, severity, source_url, published_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()), "who",
                    ["Ebola", "Cholera", "Dengue"][i],
                    f"Outbreak of {['Ebola', 'Cholera', 'Dengue'][i]}",
                    "Details here", ["CD", "MZ", "BR"][i], None,
                    "active" if i < 2 else "monitoring", [90, 70, 55][i],
                    "https://who.int/test", "2025-01-15T00:00:00Z",
                ),
            )

        # Seed weather events
        for i in range(3):
            conn.execute(
                """INSERT INTO weather_events
                   (id, event_type, title, description, severity, urgency,
                    lat, lng, area_desc, effective, expires)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    ["Tornado Warning", "Flood Watch", "Hurricane Warning"][i],
                    f"Test {['Tornado', 'Flood', 'Hurricane'][i]} Alert",
                    "Description", ["Severe", "Moderate", "Extreme"][i],
                    "Immediate", 35.0 + i, -95.0 + i, "Oklahoma County",
                    "2025-01-15T00:00:00Z", "2025-01-15T12:00:00Z",
                ),
            )

        conn.commit()
        c.sat_ids = sat_ids
        yield c


# ── Satellite Tests ─────────────────────────────────────────────────────────


def test_list_satellite(client):
    r = client.get("/api/satellite")
    assert r.status_code == 200
    data = r.json()
    assert len(data["images"]) >= 3


def test_satellite_filter_source(client):
    r = client.get("/api/satellite?source=sentinel2")
    assert r.status_code == 200
    assert len(r.json()["images"]) >= 3


def test_satellite_bbox_filter(client):
    r = client.get("/api/satellite?min_lat=34&max_lat=36&min_lng=32&max_lng=35")
    assert r.status_code == 200


def test_get_satellite_detail(client):
    r = client.get(f"/api/satellite/{client.sat_ids[0]}")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "sentinel2"
    assert isinstance(data.get("metadata"), (dict, type(None)))


def test_satellite_not_found(client):
    r = client.get("/api/satellite/nonexistent")
    assert r.status_code == 404


def test_satellite_compare(client):
    r = client.get("/api/satellite/compare?lat=35&lng=33")
    assert r.status_code == 200
    assert "images" in r.json()


# ── Fire Tests ──────────────────────────────────────────────────────────────


def test_list_fires(client):
    r = client.get("/api/fires")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 5


def test_fires_filter_confidence(client):
    r = client.get("/api/fires?confidence=high")
    assert r.status_code == 200
    data = r.json()
    assert all(f["confidence"] == "high" for f in data["fires"])


def test_fires_bbox(client):
    r = client.get("/api/fires?min_lat=34&max_lat=35&min_lng=-119&max_lng=-117")
    assert r.status_code == 200


# ── Nightlight Tests ────────────────────────────────────────────────────────


def test_list_nightlights(client):
    r = client.get("/api/nightlights")
    assert r.status_code == 200
    data = r.json()
    assert len(data["readings"]) >= 1


def test_nightlights_min_change(client):
    r = client.get("/api/nightlights?min_change=20")
    assert r.status_code == 200
    data = r.json()
    for reading in data["readings"]:
        assert abs(reading["change_pct"]) >= 20


def test_nightlights_country_filter(client):
    r = client.get("/api/nightlights?country_code=VE")
    assert r.status_code == 200
    data = r.json()
    assert all(n["country_code"] == "VE" for n in data["readings"])


# ── Outbreak Tests ──────────────────────────────────────────────────────────


def test_list_outbreaks(client):
    r = client.get("/api/outbreaks")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 3


def test_outbreaks_filter_disease(client):
    r = client.get("/api/outbreaks?disease=Ebola")
    assert r.status_code == 200
    data = r.json()
    assert all("Ebola" in o["disease"] for o in data["outbreaks"])


def test_outbreaks_filter_status(client):
    r = client.get("/api/outbreaks?status=active")
    assert r.status_code == 200
    data = r.json()
    assert all(o["status"] == "active" for o in data["outbreaks"])


# ── Weather Tests ───────────────────────────────────────────────────────────


def test_list_weather(client):
    r = client.get("/api/weather")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 3


def test_weather_filter_type(client):
    r = client.get("/api/weather?event_type=Tornado")
    assert r.status_code == 200
    data = r.json()
    assert all("Tornado" in w["event_type"] for w in data["weather_events"])


def test_weather_filter_severity(client):
    r = client.get("/api/weather?severity=Extreme")
    assert r.status_code == 200
    data = r.json()
    assert all(w["severity"] == "Extreme" for w in data["weather_events"])

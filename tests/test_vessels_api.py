"""
Phase 4 Tests — Vessels, flights, and dark pattern detection API.
"""
import json
import os
import sys
import tempfile
import uuid
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

        # Seed vessels
        vessels = [
            ("211000001", "HAMBURG EXPRESS", "cargo", "DE", 53.55, 9.99, 12.5, 180.0, "under_way_engine", None),
            ("240000002", "AEGEAN WARRIOR", "tanker", "GR", 37.95, 23.72, 8.0, 90.0, "under_way_engine", None),
            ("338000003", "USS NIMITZ", "military", "US", 32.70, -117.23, 20.0, 270.0, "under_way_engine", None),
            ("412000004", "HAI FENG 8", "fishing", "CN", 22.30, 114.17, 5.0, 45.0, "engaged_in_fishing", None),
            ("273000005", "DARK VESSEL", "cargo", "RU", 26.50, 56.20, 0.0, 0.0, "at_anchor", "2026-04-07T10:00:00Z"),
        ]
        for mmsi, name, vtype, flag, lat, lng, speed, course, nav, dark in vessels:
            db.execute(
                """INSERT INTO vessels
                   (mmsi, name, vessel_type, flag, latitude, longitude,
                    speed, course, nav_status, dark_since, last_seen, first_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-04-09T12:00:00Z', '2026-04-01T00:00:00Z')""",
                (mmsi, name, vtype, flag, lat, lng, speed, course, nav, dark),
            )

        # Seed vessel tracks for HAMBURG EXPRESS (use relative times so they're always recent)
        now = datetime.now(timezone.utc)
        for i in range(5):
            track_ts = (now - timedelta(hours=5 - i)).isoformat()
            db.execute(
                """INSERT INTO vessel_tracks
                   (mmsi, latitude, longitude, speed, course, timestamp)
                   VALUES (?, ?, ?, 12.5, 180.0, ?)""",
                ("211000001", 53.55 + i * 0.01, 9.99, track_ts),
            )

        # Seed flights
        flights = [
            ("abc123", "DLH123", "Germany", "civilian", 50.03, 8.57, 10000, 250, 180),
            ("def456", "REACH01", "United States", "military", 38.95, -77.45, 8000, 300, 90),
            ("ghi789", "FDX892", "United States", "cargo", 35.20, -80.94, 11000, 280, 270),
        ]
        for icao, cs, country, ftype, lat, lng, alt, vel, hdg in flights:
            db.execute(
                """INSERT INTO flights
                   (icao24, callsign, origin_country, flight_type,
                    latitude, longitude, altitude, velocity, heading,
                    last_seen, first_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-04-09T12:00:00Z', '2026-04-09T11:00:00Z')""",
                (icao, cs, country, ftype, lat, lng, alt, vel, hdg),
            )

        # Seed dark event
        db.execute(
            """INSERT INTO ais_dark_events
               (id, mmsi, vessel_name, last_known_lat, last_known_lng,
                last_known_time, dark_duration_hours, region, severity, resolved)
               VALUES (?, '273000005', 'DARK VESSEL', 26.50, 56.20,
                       '2026-04-07T10:00:00Z', 50.0, 'Strait of Hormuz', 85.0, 0)""",
            (str(uuid.uuid4()),),
        )

        db.commit()
        yield c
    os.unlink(_test_db_path)


class TestVessels:
    def test_list_all_vessels(self, client):
        resp = client.get("/api/vessels")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5

    def test_filter_by_type(self, client):
        resp = client.get("/api/vessels?vessel_type=cargo")
        data = resp.json()
        assert all(v["vessel_type"] == "cargo" for v in data["vessels"])

    def test_filter_dark_only(self, client):
        resp = client.get("/api/vessels?dark_only=true")
        data = resp.json()
        assert data["total"] == 1
        assert data["vessels"][0]["mmsi"] == "273000005"

    def test_bbox_filter(self, client):
        # European waters only
        resp = client.get("/api/vessels?west=-15&south=35&east=30&north=60")
        data = resp.json()
        ids = [v["mmsi"] for v in data["vessels"]]
        assert "211000001" in ids  # Hamburg
        assert "240000002" in ids  # Greece
        assert "338000003" not in ids  # San Diego

    def test_get_vessel_detail(self, client):
        resp = client.get("/api/vessels/211000001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "HAMBURG EXPRESS"
        assert data["vessel_type"] == "cargo"

    def test_vessel_not_found(self, client):
        resp = client.get("/api/vessels/000000000")
        assert resp.status_code == 404


class TestVesselTracks:
    def test_get_track(self, client):
        resp = client.get("/api/vessels/211000001/track")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mmsi"] == "211000001"
        assert len(data["points"]) >= 1

    def test_track_ordered_by_time(self, client):
        resp = client.get("/api/vessels/211000001/track")
        points = resp.json()["points"]
        times = [p["timestamp"] for p in points]
        assert times == sorted(times)


class TestDarkEvents:
    def test_list_dark_events(self, client):
        resp = client.get("/api/vessels/dark")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        de = data["dark_events"][0]
        assert de["mmsi"] == "273000005"
        assert de["region"] == "Strait of Hormuz"
        assert de["severity"] == 85.0

    def test_filter_unresolved(self, client):
        resp = client.get("/api/vessels/dark?resolved=false")
        data = resp.json()
        assert all(d["resolved"] == 0 for d in data["dark_events"])


class TestFlights:
    def test_list_all_flights(self, client):
        resp = client.get("/api/flights")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3

    def test_filter_by_type(self, client):
        resp = client.get("/api/flights?flight_type=military")
        data = resp.json()
        assert data["total"] == 1
        assert data["flights"][0]["callsign"] == "REACH01"

    def test_filter_by_country(self, client):
        resp = client.get("/api/flights?origin_country=Germany")
        data = resp.json()
        assert data["total"] == 1

    def test_flight_has_position_data(self, client):
        resp = client.get("/api/flights?limit=1")
        f = resp.json()["flights"][0]
        assert "latitude" in f
        assert "longitude" in f
        assert "altitude" in f
        assert "velocity" in f

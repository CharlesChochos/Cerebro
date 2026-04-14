"""
Module Tests — Phase 16: Disease outbreaks, storm tracking, conflict progression.
"""
import os
import sys
import sqlite3
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from detection.disease_tracking import (
    create_outbreak, get_outbreak, list_outbreaks,
    get_spread_geojson, seed_sample_outbreaks,
)
from detection.storm_tracking import (
    create_storm, add_track_point, get_storm, list_storms,
    get_storm_track_geojson, seed_sample_storms,
)
from detection.conflict_progression import (
    create_progression, add_step, get_progression,
    list_progressions, get_steps, get_step_geojson,
    seed_sample_progressions,
)


@pytest.fixture(scope="module")
def conn():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE IF NOT EXISTS disease_outbreaks (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            disease TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT,
            country_code TEXT,
            region TEXT,
            lat REAL,
            lng REAL,
            case_count INTEGER,
            death_count INTEGER,
            status TEXT,
            severity REAL DEFAULT 50,
            source_url TEXT,
            published_at TEXT NOT NULL,
            r_naught REAL DEFAULT 2.5,
            mortality_rate REAL DEFAULT 0.01,
            spread_radius_km REAL DEFAULT 10,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS disease_spread_points (
            id TEXT PRIMARY KEY, outbreak_id TEXT NOT NULL,
            latitude REAL NOT NULL, longitude REAL NOT NULL,
            cases INTEGER DEFAULT 0, day_offset INTEGER DEFAULT 0,
            radius_km REAL DEFAULT 5,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS storm_tracks (
            id TEXT PRIMARY KEY, storm_name TEXT NOT NULL,
            storm_type TEXT DEFAULT 'hurricane',
            category INTEGER DEFAULT 1, max_wind_kts INTEGER,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS storm_track_points (
            id TEXT PRIMARY KEY, storm_id TEXT NOT NULL,
            latitude REAL NOT NULL, longitude REAL NOT NULL,
            timestamp TEXT NOT NULL, wind_kts INTEGER,
            pressure_mb INTEGER, is_forecast INTEGER DEFAULT 0,
            uncertainty_radius_km REAL DEFAULT 50,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS conflict_progressions (
            id TEXT PRIMARY KEY, conflict_name TEXT NOT NULL,
            region TEXT, start_date TEXT NOT NULL,
            status TEXT DEFAULT 'ongoing',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS conflict_progression_steps (
            id TEXT PRIMARY KEY, progression_id TEXT NOT NULL,
            step_number INTEGER NOT NULL, title TEXT NOT NULL,
            narration TEXT, center_lat REAL NOT NULL, center_lng REAL NOT NULL,
            zoom REAL DEFAULT 6, bearing REAL DEFAULT 0, pitch REAL DEFAULT 45,
            event_date TEXT, markers_json TEXT, lines_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    yield c
    c.close()
    os.unlink(path)


# ─── Disease Outbreak Tests ───────────────────────────────

class TestDiseaseOutbreak:
    _oid = None

    def test_create_outbreak(self, conn):
        result = create_outbreak(conn, "Test Virus", 23.1, 113.3, "CN", 3.0, 0.02)
        TestDiseaseOutbreak._oid = result["id"]
        assert result["disease"] == "Test Virus"
        assert result["days_generated"] == 30
        assert result["r_naught"] == 3.0

    def test_get_outbreak(self, conn):
        ob = get_outbreak(conn, self._oid)
        assert ob is not None
        assert ob["disease"] == "Test Virus"
        assert ob["country_code"] == "CN"

    def test_get_outbreak_missing(self, conn):
        assert get_outbreak(conn, "nonexistent") is None

    def test_list_outbreaks(self, conn):
        items = list_outbreaks(conn)
        assert len(items) >= 1

    def test_spread_geojson_all_days(self, conn):
        geo = get_spread_geojson(conn, self._oid)
        assert geo["type"] == "FeatureCollection"
        assert len(geo["features"]) >= 30

    def test_spread_geojson_day_filter(self, conn):
        geo = get_spread_geojson(conn, self._oid, day=5)
        for f in geo["features"]:
            assert f["properties"]["day_offset"] <= 5

    def test_spread_has_polygon_geometry(self, conn):
        geo = get_spread_geojson(conn, self._oid, day=10)
        for f in geo["features"]:
            assert f["geometry"]["type"] == "Polygon"
            assert len(f["geometry"]["coordinates"][0]) >= 30

    def test_spread_cases_grow(self, conn):
        geo = get_spread_geojson(conn, self._oid)
        by_day = sorted(geo["features"], key=lambda f: f["properties"]["day_offset"])
        first = by_day[0]["properties"]["cases"]
        last = by_day[-1]["properties"]["cases"]
        # Over 30 days, cases must have grown from initial 1
        assert last >= first

    def test_seed_outbreaks(self, conn):
        count = seed_sample_outbreaks(conn)
        assert count == 0  # Already have data


# ─── Storm Tracking Tests ─────────────────────────────────

class TestStormTracking:
    _sid = None

    def test_create_storm(self, conn):
        result = create_storm(conn, "Test Hurricane", "hurricane", 3, 120)
        TestStormTracking._sid = result["id"]
        assert result["storm_name"] == "Test Hurricane"
        assert result["category"] == 3

    def test_add_track_points(self, conn):
        points = [
            (20.0, -86.0, "2025-09-10T06:00:00", 80, 985, 0, 30),
            (22.0, -88.0, "2025-09-10T18:00:00", 100, 970, 0, 40),
            (24.0, -89.5, "2025-09-11T06:00:00", 120, 950, 0, 50),
            (26.0, -90.0, "2025-09-11T18:00:00", 110, 960, 1, 80),
            (28.0, -89.5, "2025-09-12T06:00:00", 90, 975, 1, 120),
        ]
        for lat, lng, ts, w, p, fc, ur in points:
            result = add_track_point(conn, self._sid, lat, lng, ts, w, p, fc, ur)
            assert result["storm_id"] == self._sid

    def test_get_storm(self, conn):
        storm = get_storm(conn, self._sid)
        assert storm is not None
        assert storm["storm_name"] == "Test Hurricane"

    def test_get_storm_missing(self, conn):
        assert get_storm(conn, "nonexistent") is None

    def test_list_storms(self, conn):
        storms = list_storms(conn)
        assert len(storms) >= 1

    def test_track_geojson(self, conn):
        geo = get_storm_track_geojson(conn, self._sid)
        assert geo["type"] == "FeatureCollection"
        types = [f["properties"]["type"] for f in geo["features"]]
        assert "track_line" in types
        assert "track_point" in types

    def test_track_has_uncertainty_cone(self, conn):
        geo = get_storm_track_geojson(conn, self._sid)
        cone = [f for f in geo["features"]
                if f["properties"].get("type") == "uncertainty_cone"]
        assert len(cone) >= 1
        assert cone[0]["geometry"]["type"] == "Polygon"

    def test_track_point_count(self, conn):
        geo = get_storm_track_geojson(conn, self._sid)
        points = [f for f in geo["features"]
                  if f["properties"].get("type") == "track_point"]
        assert len(points) == 5

    def test_seed_storms(self, conn):
        count = seed_sample_storms(conn)
        assert count == 0


# ─── Conflict Progression Tests ───────────────────────────

class TestConflictProgression:
    _pid = None

    def test_create_progression(self, conn):
        result = create_progression(conn, "Test Conflict", "Test Region", "2024-01-01")
        TestConflictProgression._pid = result["id"]
        assert result["conflict_name"] == "Test Conflict"

    def test_add_steps(self, conn):
        steps = [
            (1, "Phase 1", "Initial offensive begins.", 33.3, 44.4, 7, 0, 45, "2024-01-01",
             [{"lat": 33.3, "lng": 44.4, "label": "City A", "color": "#ef4444"}],
             [[[44.0, 33.0], [44.5, 33.5]]]),
            (2, "Phase 2", "Counter-attack launched.", 33.5, 44.6, 8, 20, 50, "2024-02-15",
             [{"lat": 33.5, "lng": 44.6, "label": "City B", "color": "#22c55e"}],
             []),
            (3, "Phase 3", "Ceasefire negotiations begin.", 33.4, 44.5, 6, 0, 40, "2024-03-01",
             [], []),
        ]
        for sn, title, narr, lat, lng, z, b, pi, d, markers, lines in steps:
            result = add_step(conn, self._pid, sn, title, narr, lat, lng, z, b, pi, d,
                              markers, lines)
            assert result["step_number"] == sn

    def test_get_progression(self, conn):
        p = get_progression(conn, self._pid)
        assert p is not None
        assert p["conflict_name"] == "Test Conflict"

    def test_get_progression_missing(self, conn):
        assert get_progression(conn, "nonexistent") is None

    def test_list_progressions(self, conn):
        items = list_progressions(conn)
        assert len(items) >= 1

    def test_get_steps(self, conn):
        steps = get_steps(conn, self._pid)
        assert len(steps) == 3
        assert steps[0]["step_number"] == 1
        assert steps[2]["step_number"] == 3

    def test_steps_have_markers(self, conn):
        steps = get_steps(conn, self._pid)
        assert len(steps[0]["markers"]) == 1
        assert steps[0]["markers"][0]["label"] == "City A"

    def test_step_geojson(self, conn):
        geo = get_step_geojson(conn, self._pid, 1)
        assert geo["type"] == "FeatureCollection"
        assert len(geo["features"]) >= 1

    def test_step_geojson_has_point(self, conn):
        geo = get_step_geojson(conn, self._pid, 1)
        types = [f["geometry"]["type"] for f in geo["features"]]
        assert "Point" in types

    def test_step_geojson_has_line(self, conn):
        geo = get_step_geojson(conn, self._pid, 1)
        types = [f["geometry"]["type"] for f in geo["features"]]
        assert "LineString" in types

    def test_step_geojson_empty_step(self, conn):
        geo = get_step_geojson(conn, self._pid, 3)
        assert geo["type"] == "FeatureCollection"
        assert len(geo["features"]) == 0

    def test_seed_progressions(self, conn):
        count = seed_sample_progressions(conn)
        assert count == 0

"""
Module Tests — Phase 14: satellite orbits, monitored locations (pulse beacons),
country extrusions (3D visualization data).
"""
import os
import sys
import sqlite3
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from detection.satellite_orbits import (
    seed_satellites, add_satellite, get_satellite, get_by_norad,
    list_satellites, predict_passes, get_orbit_geojson,
)
from detection.monitored_locations import (
    seed_locations, add_location, get_location, list_locations,
    update_alert_level, record_event, get_beacon_geojson,
)
from detection.country_extrusions import (
    seed_extrusions, upsert_metric, get_metric, list_metrics,
    get_extrusion_data, get_rankings, compute_normalized,
)


@pytest.fixture(scope="module")
def conn():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    # Create Phase 14 tables
    c.executescript("""
        CREATE TABLE IF NOT EXISTS satellite_orbits (
            id TEXT PRIMARY KEY, norad_id INTEGER NOT NULL, name TEXT NOT NULL,
            category TEXT DEFAULT 'unknown', country_code TEXT,
            tle_line1 TEXT, tle_line2 TEXT,
            inclination REAL, period_min REAL, apogee_km REAL, perigee_km REAL,
            launch_date TEXT, status TEXT DEFAULT 'active',
            updated_at TEXT DEFAULT (datetime('now')),
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS monitored_locations (
            id TEXT PRIMARY KEY, name TEXT NOT NULL,
            latitude REAL NOT NULL, longitude REAL NOT NULL,
            location_type TEXT DEFAULT 'general', country_code TEXT,
            alert_level TEXT DEFAULT 'normal', pulse_rate REAL DEFAULT 2.0,
            radius_km REAL DEFAULT 50, event_count_24h INTEGER DEFAULT 0,
            last_event_at TEXT, notes TEXT, active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS country_extrusions (
            id TEXT PRIMARY KEY, country_code TEXT NOT NULL,
            metric_name TEXT NOT NULL, metric_value REAL NOT NULL,
            normalized REAL, period TEXT DEFAULT 'current',
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_extrusion_unique
            ON country_extrusions(country_code, metric_name, period);
    """)
    yield c
    c.close()
    os.unlink(path)


# ─── Satellite Orbits ────────────────────────────────────────

class TestSatelliteOrbits:
    _sid = None

    def test_seed_satellites(self, conn):
        count = seed_satellites(conn)
        assert count >= 10

    def test_add_satellite(self, conn):
        sid = add_satellite(conn, norad_id=99999, name="TEST-SAT-14",
                            category="comms", country_code="US",
                            inclination=53.0, period_min=95.0,
                            apogee_km=550, perigee_km=540)
        TestSatelliteOrbits._sid = sid
        assert sid is not None

    def test_get_satellite(self, conn):
        sat = get_satellite(conn, self._sid)
        assert sat is not None
        assert sat["name"] == "TEST-SAT-14"
        assert sat["norad_id"] == 99999

    def test_get_by_norad(self, conn):
        sat = get_by_norad(conn, 25544)
        assert sat is not None
        assert "ISS" in sat["name"]

    def test_get_by_norad_missing(self, conn):
        sat = get_by_norad(conn, 0)
        assert sat is None

    def test_list_satellites(self, conn):
        sats = list_satellites(conn)
        assert len(sats) >= 10

    def test_list_by_category(self, conn):
        sats = list_satellites(conn, category="military")
        assert len(sats) >= 2
        for s in sats:
            assert s["category"] == "military"

    def test_list_by_country(self, conn):
        sats = list_satellites(conn, country_code="US")
        assert len(sats) >= 2

    def test_predict_passes_iss(self, conn):
        passes = predict_passes(conn, 25544, 40.7, -74.0, hours=24)
        assert isinstance(passes, list)
        if passes:
            p = passes[0]
            assert "rise_time" in p
            assert "max_elevation" in p
            assert p["norad_id"] == 25544

    def test_predict_passes_out_of_range(self, conn):
        # Observer at 85°N, ISS inclination ~51.6° — should return empty
        passes = predict_passes(conn, 25544, 85.0, 0.0)
        assert passes == []

    def test_predict_passes_missing_sat(self, conn):
        passes = predict_passes(conn, 0, 40.0, -74.0)
        assert passes == []

    def test_orbit_geojson(self, conn):
        geo = get_orbit_geojson(conn)
        assert geo["type"] == "FeatureCollection"
        assert len(geo["features"]) >= 5
        f = geo["features"][0]
        assert f["geometry"]["type"] == "LineString"
        assert "name" in f["properties"]

    def test_orbit_geojson_by_category(self, conn):
        geo = get_orbit_geojson(conn, category="military")
        for f in geo["features"]:
            assert f["properties"]["category"] == "military"


# ─── Monitored Locations ────────────────────────────────────

class TestMonitoredLocations:
    _lid = None

    def test_seed_locations(self, conn):
        count = seed_locations(conn)
        assert count >= 10

    def test_add_location(self, conn):
        lid = add_location(conn, name="Phase14 Test Base",
                           latitude=35.0, longitude=45.0,
                           location_type="military_base",
                           country_code="IQ",
                           alert_level="elevated")
        TestMonitoredLocations._lid = lid
        assert lid is not None

    def test_add_invalid_type(self, conn):
        with pytest.raises(ValueError):
            add_location(conn, name="Bad", latitude=0, longitude=0,
                         location_type="invalid_type")

    def test_add_invalid_alert(self, conn):
        with pytest.raises(ValueError):
            add_location(conn, name="Bad", latitude=0, longitude=0,
                         alert_level="extreme")

    def test_get_location(self, conn):
        loc = get_location(conn, self._lid)
        assert loc is not None
        assert loc["name"] == "Phase14 Test Base"
        assert loc["alert_level"] == "elevated"

    def test_list_locations(self, conn):
        locs = list_locations(conn)
        assert len(locs) >= 10

    def test_list_by_type(self, conn):
        locs = list_locations(conn, location_type="nuclear")
        assert len(locs) >= 1
        for loc in locs:
            assert loc["location_type"] == "nuclear"

    def test_list_by_alert(self, conn):
        locs = list_locations(conn, alert_level="high")
        assert len(locs) >= 1
        for loc in locs:
            assert loc["alert_level"] == "high"

    def test_update_alert_level(self, conn):
        result = update_alert_level(conn, self._lid, "critical")
        assert result is True
        loc = get_location(conn, self._lid)
        assert loc["alert_level"] == "critical"
        assert loc["pulse_rate"] == 0.5  # Auto-adjusted

    def test_update_alert_with_custom_pulse(self, conn):
        update_alert_level(conn, self._lid, "high", pulse_rate=0.8)
        loc = get_location(conn, self._lid)
        assert loc["alert_level"] == "high"
        assert loc["pulse_rate"] == 0.8

    def test_update_invalid_alert(self, conn):
        with pytest.raises(ValueError):
            update_alert_level(conn, self._lid, "extreme")

    def test_record_event(self, conn):
        loc_before = get_location(conn, self._lid)
        count_before = loc_before["event_count_24h"]
        record_event(conn, self._lid)
        loc_after = get_location(conn, self._lid)
        assert loc_after["event_count_24h"] == count_before + 1
        assert loc_after["last_event_at"] is not None

    def test_beacon_geojson(self, conn):
        geo = get_beacon_geojson(conn)
        assert geo["type"] == "FeatureCollection"
        assert len(geo["features"]) >= 10
        f = geo["features"][0]
        assert f["geometry"]["type"] == "Point"
        assert "pulse_rate" in f["properties"]
        assert "color" in f["properties"]

    def test_beacon_geojson_filtered(self, conn):
        geo = get_beacon_geojson(conn, alert_level="high")
        for f in geo["features"]:
            assert f["properties"]["alert_level"] == "high"


# ─── Country Extrusions ─────────────────────────────────────

class TestCountryExtrusions:

    def test_seed_extrusions(self, conn):
        count = seed_extrusions(conn)
        assert count >= 15

    def test_upsert_new(self, conn):
        eid = upsert_metric(conn, "AU", "event_count", 150, 0.10)
        assert eid is not None

    def test_upsert_update(self, conn):
        eid1 = upsert_metric(conn, "AU", "event_count", 200, 0.14)
        m = get_metric(conn, "AU", "event_count")
        assert m["metric_value"] == 200
        # Should reuse same ID
        eid2 = upsert_metric(conn, "AU", "event_count", 250, 0.17)
        assert eid1 == eid2

    def test_upsert_invalid_metric(self, conn):
        with pytest.raises(ValueError):
            upsert_metric(conn, "US", "invalid_metric", 100)

    def test_get_metric(self, conn):
        m = get_metric(conn, "US", "event_count")
        assert m is not None
        assert m["country_code"] == "US"
        assert m["metric_value"] == 1250

    def test_get_metric_missing(self, conn):
        m = get_metric(conn, "ZZ", "event_count")
        assert m is None

    def test_list_metrics(self, conn):
        metrics = list_metrics(conn)
        assert len(metrics) >= 15

    def test_list_by_metric_name(self, conn):
        metrics = list_metrics(conn, metric_name="risk_score")
        assert len(metrics) >= 8
        for m in metrics:
            assert m["metric_name"] == "risk_score"

    def test_list_by_country(self, conn):
        metrics = list_metrics(conn, country_code="US")
        assert len(metrics) >= 2

    def test_extrusion_data(self, conn):
        data = get_extrusion_data(conn, "event_count")
        assert len(data) >= 5
        assert "country_code" in data[0]
        assert "normalized" in data[0]

    def test_rankings(self, conn):
        ranked = get_rankings(conn, "risk_score", top_n=5)
        assert len(ranked) <= 5
        assert ranked[0]["rank"] == 1
        # Should be sorted descending
        values = [r["metric_value"] for r in ranked]
        assert values == sorted(values, reverse=True)

    def test_compute_normalized(self, conn):
        count = compute_normalized(conn, "event_count")
        assert count >= 5
        # Check that highest value now has normalized = 1.0
        data = get_extrusion_data(conn, "event_count")
        max_norm = max(d["normalized"] for d in data)
        assert abs(max_norm - 1.0) < 0.01

    def test_compute_normalized_empty(self, conn):
        count = compute_normalized(conn, "nonexistent_metric")
        assert count == 0

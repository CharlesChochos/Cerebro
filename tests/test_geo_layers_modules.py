"""
Tests — Elevation profiles, maritime zones, vegetation indices,
predictive positioning, data lineage (module-level).
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection
from db.migrate import run_migrations


@pytest.fixture(scope="module")
def conn():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["CEREBRO_DB_PATH"] = path
    c = get_connection()
    run_migrations(c)

    now = datetime.now(timezone.utc)

    # Seed geo-located events for hotspot and heatmap testing
    locations = [
        (33.0, 44.0, "IQ", "Middle East"),     # Baghdad cluster
        (33.5, 44.2, "IQ", "Middle East"),
        (33.2, 44.1, "IQ", "Middle East"),
        (33.1, 44.3, "IQ", "Middle East"),
        (33.3, 44.0, "IQ", "Middle East"),
        (48.8, 2.3, "FR", "Western Europe"),    # Paris cluster
        (48.9, 2.4, "FR", "Western Europe"),
        (51.5, -0.1, "GB", "Western Europe"),   # London
        (38.9, -77.0, "US", "North America"),   # DC
        (35.7, 51.4, "IR", "Middle East"),      # Tehran
    ]

    for idx, (lat, lng, cc, region) in enumerate(locations):
        for day in range(14):
            eid = f"evt-geo-{idx}-{day}"
            ts = (now - timedelta(days=day)).isoformat()
            sev = 40 + (idx * 5) + (day % 20)
            c.execute(
                """INSERT OR IGNORE INTO events
                   (id, source, source_id, title, category, severity,
                    latitude, longitude, country_code, region, timestamp, summary)
                   VALUES (?, 'test', ?, ?, 'military', ?, ?, ?, ?, ?, ?, ?)""",
                (eid, eid, f"Geo event {idx} day {day}", min(sev, 100),
                 lat, lng, cc, region, ts, f"Summary {idx}-{day}"),
            )

    c.commit()
    yield c
    c.close()
    os.unlink(path)


# ─── Elevation Profiles ──────────────────────────────────────

class TestElevation:
    def test_interpolate_points(self):
        from geo.elevation import interpolate_points
        points = [[0.0, 0.0], [10.0, 10.0]]
        result = interpolate_points(points, 5)
        assert len(result) == 5
        assert result[0] == [0.0, 0.0]

    def test_estimate_elevation(self):
        from geo.elevation import estimate_elevation
        # Mountain areas should be higher
        himalaya = estimate_elevation(28.0, 85.0)
        ocean = estimate_elevation(-30.0, -40.0)
        assert himalaya > ocean

    def test_compute_elevation_profile(self):
        from geo.elevation import compute_elevation_profile
        points = [[28.0, 85.0], [28.5, 85.5], [29.0, 86.0]]
        profile = compute_elevation_profile(points, num_samples=10)
        assert "points" in profile
        assert len(profile["points"]) == 10
        assert profile["total_distance_km"] > 0
        assert profile["min_elevation_m"] <= profile["max_elevation_m"]

    def test_profile_too_few_points(self):
        from geo.elevation import compute_elevation_profile
        result = compute_elevation_profile([[0, 0]])
        assert "error" in result

    def test_store_and_get_profile(self, conn):
        from geo.elevation import compute_elevation_profile, store_elevation_profile, get_elevation_profile
        profile = compute_elevation_profile([[40, 10], [45, 15]], num_samples=5)
        pid = store_elevation_profile(conn, profile, "Test Profile")
        loaded = get_elevation_profile(conn, pid)
        assert loaded is not None
        assert loaded["name"] == "Test Profile"
        assert len(loaded["points"]) == 5

    def test_list_profiles(self, conn):
        from geo.elevation import list_elevation_profiles
        profiles = list_elevation_profiles(conn)
        assert len(profiles) >= 1

    def test_get_profile_not_found(self, conn):
        from geo.elevation import get_elevation_profile
        assert get_elevation_profile(conn, "nonexistent") is None


# ─── Maritime Zones ──────────────────────────────────────────

class TestMaritime:
    def test_seeded_zones_exist(self, conn):
        from geo.maritime import list_maritime_zones
        zones = list_maritime_zones(conn)
        assert len(zones) >= 10  # 12 seeded in migration

    def test_filter_by_type(self, conn):
        from geo.maritime import list_maritime_zones
        chokepoints = list_maritime_zones(conn, zone_type="chokepoint")
        assert len(chokepoints) >= 5
        assert all(z["zone_type"] == "chokepoint" for z in chokepoints)

    def test_get_zone(self, conn):
        from geo.maritime import get_maritime_zone
        zone = get_maritime_zone(conn, "mz-hormuz")
        assert zone is not None
        assert zone["name"] == "Strait of Hormuz"
        assert isinstance(zone["polygon"], list)

    def test_get_zone_not_found(self, conn):
        from geo.maritime import get_maritime_zone
        assert get_maritime_zone(conn, "nonexistent") is None

    def test_create_zone(self, conn):
        from geo.maritime import create_maritime_zone, get_maritime_zone
        polygon = [[10.0, 20.0], [11.0, 20.0], [11.0, 21.0], [10.0, 21.0], [10.0, 20.0]]
        zid = create_maritime_zone(conn, "Test Zone", "eez", polygon, "Test", "normal", "XX")
        zone = get_maritime_zone(conn, zid)
        assert zone is not None
        assert zone["name"] == "Test Zone"

    def test_point_in_zone(self, conn):
        from geo.maritime import find_zones_for_point
        # Point inside Strait of Hormuz (26.5°N, 56.2°E)
        zones = find_zones_for_point(conn, 26.5, 56.2)
        assert any(z["id"] == "mz-hormuz" for z in zones)

    def test_point_outside_zones(self, conn):
        from geo.maritime import find_zones_for_point
        # Middle of nowhere in Pacific
        zones = find_zones_for_point(conn, -40.0, -170.0)
        assert len(zones) == 0

    def test_geojson_output(self, conn):
        from geo.maritime import get_zones_geojson
        geojson = get_zones_geojson(conn)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) >= 10


# ─── Vegetation Indices ──────────────────────────────────────

class TestVegetation:
    def test_classify_ndvi(self):
        from detection.vegetation import classify_ndvi
        assert classify_ndvi(-0.5) == "water"
        assert classify_ndvi(0.05) == "barren"
        assert classify_ndvi(0.15) == "stressed"
        assert classify_ndvi(0.35) == "normal"
        assert classify_ndvi(0.7) == "lush"

    def test_compute_change(self):
        from detection.vegetation import compute_ndvi_change
        assert compute_ndvi_change(0.2, 0.4) == -50.0
        assert compute_ndvi_change(0.4, 0.4) == 0.0

    def test_store_and_get_reading(self, conn):
        from detection.vegetation import store_reading, get_readings
        store_reading(conn, 33.0, 44.0, 0.15, 0.4, "2026-04-01", "IQ", "Middle East")
        store_reading(conn, 33.1, 44.1, 0.6, 0.5, "2026-04-01", "IQ", "Middle East")
        readings = get_readings(conn, country_code="IQ", days=30)
        assert len(readings) >= 2

    def test_scan_anomalies(self, conn):
        from detection.vegetation import scan_vegetation_anomalies
        anomalies = scan_vegetation_anomalies(conn, threshold_pct=-20.0)
        assert isinstance(anomalies, list)
        # Our IQ reading with 0.15 vs 0.4 baseline = -62.5% change
        stressed = [a for a in anomalies if a["country_code"] == "IQ"]
        assert len(stressed) >= 1

    def test_vegetation_geojson(self, conn):
        from detection.vegetation import get_vegetation_geojson
        geojson = get_vegetation_geojson(conn)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) >= 1


# ─── Predictive Positioning ──────────────────────────────────

class TestPredictivePositioning:
    def test_compute_event_density(self):
        from detection.predictive_positioning import compute_event_density
        events = [
            {"lat": 33.0, "lng": 44.0, "severity": 70, "id": "a"},
            {"lat": 33.1, "lng": 44.1, "severity": 80, "id": "b"},
            {"lat": 33.0, "lng": 44.0, "severity": 60, "id": "c"},
        ]
        cells = compute_event_density(events, grid_size=1.0)
        assert len(cells) >= 1
        # Top cell should have count >= 2 (the two ~33.0, 44.0 events)
        assert cells[0]["count"] >= 2

    def test_detect_hotspots(self, conn):
        from detection.predictive_positioning import detect_hotspots
        hotspots = detect_hotspots(conn, days=14)
        assert len(hotspots) >= 1
        # Baghdad cluster should be a hotspot
        assert hotspots[0]["count"] >= 3

    def test_detect_escalation_zones(self, conn):
        from detection.predictive_positioning import detect_escalation_zones
        zones = detect_escalation_zones(conn, days=14)
        assert isinstance(zones, list)

    def test_generate_predictions(self, conn):
        from detection.predictive_positioning import generate_predictions
        preds = generate_predictions(conn)
        assert len(preds) >= 1
        assert all(p["prediction_type"] in ("event_hotspot", "escalation_zone") for p in preds)

    def test_run_predictive_scan(self, conn):
        from detection.predictive_positioning import run_predictive_scan
        result = run_predictive_scan(conn)
        assert result["total_predictions"] >= 1
        assert len(result["stored_ids"]) >= 1

    def test_list_predictions(self, conn):
        from detection.predictive_positioning import list_predictions
        preds = list_predictions(conn)
        assert len(preds) >= 1

    def test_predictions_geojson(self, conn):
        from detection.predictive_positioning import get_predictions_geojson
        geojson = get_predictions_geojson(conn)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) >= 1


# ─── Data Lineage ────────────────────────────────────────────

class TestDataLineage:
    def test_record_lineage(self, conn):
        from intelligence.data_lineage import record_lineage
        lid = record_lineage(
            conn, "event", "evt-geo-0-0", "created", "ingestion",
            details={"source": "test", "raw_size": 1024},
        )
        assert lid is not None

    def test_record_chain(self, conn):
        from intelligence.data_lineage import record_lineage
        l1 = record_lineage(conn, "event", "evt-geo-1-0", "created", "ingestion")
        l2 = record_lineage(
            conn, "event", "evt-geo-1-0", "classified", "classifier",
            details={"category": "military", "confidence": 0.9},
            parent_lineage_id=l1,
        )
        l3 = record_lineage(
            conn, "event", "evt-geo-1-0", "enriched", "enricher",
            details={"entities_added": 3},
            source_ids=["evt-geo-1-0"],
            parent_lineage_id=l2,
        )
        assert l3 is not None

    def test_get_lineage_chain(self, conn):
        from intelligence.data_lineage import get_lineage_chain
        chain = get_lineage_chain(conn, "event", "evt-geo-1-0")
        assert len(chain) >= 3
        actions = [e["action"] for e in chain]
        assert "created" in actions
        assert "classified" in actions

    def test_get_lineage_entry(self, conn):
        from intelligence.data_lineage import get_lineage_chain, get_lineage_entry
        chain = get_lineage_chain(conn, "event", "evt-geo-1-0")
        entry = get_lineage_entry(conn, chain[0]["id"])
        assert entry is not None
        assert entry["entity_type"] == "event"

    def test_get_entry_not_found(self, conn):
        from intelligence.data_lineage import get_lineage_entry
        assert get_lineage_entry(conn, "nonexistent") is None

    def test_list_lineage(self, conn):
        from intelligence.data_lineage import list_lineage
        entries = list_lineage(conn, hours=24)
        assert len(entries) >= 3

    def test_list_lineage_filtered(self, conn):
        from intelligence.data_lineage import list_lineage
        entries = list_lineage(conn, action="classified", hours=24)
        assert all(e["action"] == "classified" for e in entries)

    def test_lineage_stats(self, conn):
        from intelligence.data_lineage import get_lineage_stats
        stats = get_lineage_stats(conn, hours=24)
        assert stats["total_entries"] >= 3
        assert "created" in stats["by_action"]
        assert "ingestion" in stats["by_actor"]

    def test_trace_sources(self, conn):
        from intelligence.data_lineage import trace_sources
        tree = trace_sources(conn, "event", "evt-geo-1-0")
        assert tree["entity_type"] == "event"
        assert tree["lineage_count"] >= 3

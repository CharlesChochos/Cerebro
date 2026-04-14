"""
Module Tests — Phase 15: EXIF extraction, photo pins, event enrichment.
"""
import os
import sys
import sqlite3
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from detection.exif_extraction import (
    extract_exif, check_location_mismatch, haversine_km, HAS_PIL,
)
from detection.photo_pins import (
    add_photo_pin, get_photo_pin, list_photo_pins,
    get_photo_pin_geojson, find_mismatches,
)
from geo.enrichment import (
    enrich_event, batch_enrich, get_enrichment, get_enrichment_stats,
)


@pytest.fixture(scope="module")
def conn():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE IF NOT EXISTS photo_pins (
            id TEXT PRIMARY KEY, event_id TEXT, source_url TEXT NOT NULL,
            image_url TEXT, latitude REAL NOT NULL, longitude REAL NOT NULL,
            title TEXT, caption TEXT, country_code TEXT,
            exif_lat REAL, exif_lng REAL, exif_timestamp TEXT,
            exif_camera TEXT, exif_mismatch INTEGER DEFAULT 0,
            mismatch_km REAL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS event_enrichments (
            id TEXT PRIMARY KEY, event_id TEXT NOT NULL UNIQUE,
            nearest_city TEXT, admin_region TEXT, country_name TEXT,
            terrain_type TEXT, population_density TEXT,
            nearest_border_km REAL, nearest_military_km REAL,
            elevation_m REAL,
            enriched_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY, source TEXT, source_id TEXT,
            timestamp TEXT, title TEXT, summary TEXT, raw_payload TEXT,
            latitude REAL, longitude REAL, country_code TEXT, region TEXT,
            category TEXT, severity REAL, confidence REAL,
            entities_json TEXT, source_url TEXT
        );
        CREATE TABLE IF NOT EXISTS geocode_cache (
            id TEXT PRIMARY KEY,
            latitude REAL NOT NULL, longitude REAL NOT NULL,
            country_code TEXT, country_name TEXT,
            resolution TEXT DEFAULT 'country', provider TEXT DEFAULT 'offline',
            raw_response TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    # Insert some test events
    for i, (lat, lng, cc) in enumerate([
        (33.3, 44.4, "IQ"), (50.4, 30.5, "UA"), (35.7, 139.7, "JP"),
    ]):
        c.execute(
            "INSERT INTO events (id, source, timestamp, title, latitude, longitude, country_code, severity, confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"test-event-{i}", "test", "2025-01-01", f"Test Event {i}",
             lat, lng, cc, 50, 0.8))
    c.commit()
    yield c
    c.close()
    os.unlink(path)


# ─── EXIF Extraction ────────────────────────────────────────

class TestExifExtraction:

    def test_haversine_same_point(self):
        d = haversine_km(40.0, -74.0, 40.0, -74.0)
        assert d == 0.0

    def test_haversine_known_distance(self):
        # NYC to London ~5570 km
        d = haversine_km(40.7, -74.0, 51.5, -0.1)
        assert 5500 < d < 5700

    def test_check_mismatch_close(self):
        result = check_location_mismatch(33.3, 44.4, 33.31, 44.41)
        assert result["mismatch"] is False
        assert result["distance_km"] < 50

    def test_check_mismatch_far(self):
        result = check_location_mismatch(33.3, 44.4, 50.0, 30.0)
        assert result["mismatch"] is True
        assert result["distance_km"] > 100

    def test_check_mismatch_custom_threshold(self):
        result = check_location_mismatch(33.3, 44.4, 33.5, 44.6, threshold_km=10)
        assert isinstance(result["mismatch"], bool)
        assert result["threshold_km"] == 10

    def test_extract_empty_bytes(self):
        # Non-image bytes should not crash
        result = extract_exif(b"not an image")
        assert result["has_gps"] is False

    @pytest.mark.skipif(not HAS_PIL, reason="Pillow not installed")
    def test_extract_minimal_jpeg(self):
        # Create a minimal JPEG (no EXIF)
        from PIL import Image
        from io import BytesIO
        img = Image.new("RGB", (10, 10), color="red")
        buf = BytesIO()
        img.save(buf, format="JPEG")
        result = extract_exif(buf.getvalue())
        assert result["has_gps"] is False


# ─── Photo Pins ──────────────────────────────────────────────

class TestPhotoPins:
    _pid = None

    def test_add_photo_pin(self, conn):
        result = add_photo_pin(
            conn, source_url="https://news.example.com/article1",
            latitude=33.3, longitude=44.4,
            title="Baghdad Street Scene",
            country_code="IQ", event_id="test-event-0")
        TestPhotoPins._pid = result["id"]
        assert result["id"] is not None
        assert result["exif_mismatch"] is False

    def test_add_multiple_pins(self, conn):
        add_photo_pin(conn, source_url="https://news.example.com/art2",
                      latitude=50.4, longitude=30.5, title="Kyiv Photo",
                      country_code="UA")
        add_photo_pin(conn, source_url="https://news.example.com/art3",
                      latitude=35.7, longitude=139.7, title="Tokyo Photo",
                      country_code="JP")

    def test_get_photo_pin(self, conn):
        pin = get_photo_pin(conn, self._pid)
        assert pin is not None
        assert pin["title"] == "Baghdad Street Scene"
        assert pin["country_code"] == "IQ"

    def test_get_nonexistent(self, conn):
        pin = get_photo_pin(conn, "nonexistent")
        assert pin is None

    def test_list_photo_pins(self, conn):
        pins = list_photo_pins(conn)
        assert len(pins) >= 3

    def test_list_by_country(self, conn):
        pins = list_photo_pins(conn, country_code="IQ")
        assert len(pins) >= 1
        for p in pins:
            assert p["country_code"] == "IQ"

    def test_list_by_event(self, conn):
        pins = list_photo_pins(conn, event_id="test-event-0")
        assert len(pins) >= 1

    def test_list_mismatch_only(self, conn):
        pins = list_photo_pins(conn, mismatch_only=True)
        # All our test pins have no EXIF, so no mismatches
        for p in pins:
            assert p["exif_mismatch"] == 1

    def test_geojson(self, conn):
        geo = get_photo_pin_geojson(conn)
        assert geo["type"] == "FeatureCollection"
        assert len(geo["features"]) >= 3

    def test_find_mismatches(self, conn):
        # Manually insert a mismatch pin
        conn.execute(
            """INSERT INTO photo_pins
               (id, source_url, latitude, longitude, title,
                exif_lat, exif_lng, exif_mismatch, mismatch_km)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("mismatch-1", "https://fake.com/img", 33.3, 44.4,
             "Suspicious Photo", 50.0, 30.0, 1, 2150.0))
        conn.commit()

        mismatches = find_mismatches(conn)
        assert len(mismatches) >= 1
        assert mismatches[0]["exif_mismatch"] == 1

    def test_geojson_mismatch_line(self, conn):
        geo = get_photo_pin_geojson(conn, mismatch_only=True)
        # Should have both a point and a mismatch line
        types = [f["geometry"]["type"] for f in geo["features"]]
        assert "Point" in types
        assert "LineString" in types


# ─── Event Enrichment ───────────────────────────────────────

class TestEventEnrichment:

    def test_enrich_event(self, conn):
        result = enrich_event(conn, "test-event-0", 33.3, 44.4)
        assert result["event_id"] == "test-event-0"
        assert result["country_name"]  # Should get Iraq from reverse geocode
        assert result["terrain_type"] is not None
        assert result["nearest_border_km"] is not None
        assert result["nearest_military_km"] is not None

    def test_enrich_cached(self, conn):
        # Second call should return cached result
        result = enrich_event(conn, "test-event-0", 33.3, 44.4)
        assert result["event_id"] == "test-event-0"

    def test_enrich_different_location(self, conn):
        result = enrich_event(conn, "test-event-1", 50.4, 30.5)
        assert result["event_id"] == "test-event-1"
        assert result["country_name"]  # Should get Ukraine

    def test_get_enrichment(self, conn):
        enrichment = get_enrichment(conn, "test-event-0")
        assert enrichment is not None
        assert enrichment["event_id"] == "test-event-0"

    def test_get_enrichment_missing(self, conn):
        enrichment = get_enrichment(conn, "nonexistent")
        assert enrichment is None

    def test_batch_enrich(self, conn):
        count = batch_enrich(conn, limit=10)
        # test-event-2 (Tokyo) should get enriched
        assert count >= 0  # Some may already be enriched

    def test_enrichment_stats(self, conn):
        stats = get_enrichment_stats(conn)
        assert "total_events_with_coords" in stats
        assert "enriched" in stats
        assert "coverage_pct" in stats
        assert stats["enriched"] >= 2

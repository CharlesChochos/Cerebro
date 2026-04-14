"""
Module-level tests — Election monitoring, nuclear proliferation, migration tracking,
cyber incidents, event tagging, EXIF extraction, reverse geocoding, PDF export.
"""
import os
import sys
import json
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

    # Seed a few events for tagging and PDF export
    now = datetime.now(timezone.utc)
    for i in range(10):
        ts = (now - timedelta(hours=i)).isoformat()
        c.execute(
            """INSERT OR IGNORE INTO events
               (id, source, title, category, severity,
                latitude, longitude, country_code, region, timestamp, summary)
               VALUES (?, 'test', ?, 'political', ?, 33.0, 44.0, 'IQ', 'Middle East', ?, ?)""",
            (f"evt-domain-{i}", f"Domain event {i}", 50 + i * 3,
             ts, f"Summary for domain event {i}"),
        )
    c.commit()
    yield c
    os.unlink(path)


# ─── Election Monitoring ──────────────────────────────────

from detection.election_monitor import (
    create_election, get_election, list_elections, update_election,
)


class TestElectionMonitoring:
    _eid = None

    def test_create_election(self, conn):
        eid = create_election(
            conn, "UA", "presidential", "2026-10-15",
            ["Candidate A", "Candidate B"], "elevated",
            ["russian_interference", "media_manipulation"], "Eastern Europe", "analyst1",
        )
        assert eid
        TestElectionMonitoring._eid = eid

    def test_get_election(self, conn):
        item = get_election(conn, self._eid)
        assert item is not None
        assert item["country_code"] == "UA"
        assert item["election_type"] == "presidential"
        assert item["risk_level"] == "elevated"
        assert "russian_interference" in item["risk_factors"]

    def test_list_elections(self, conn):
        items = list_elections(conn, country_code="UA")
        assert len(items) >= 1
        found = any(e["id"] == self._eid for e in items)
        assert found

    def test_list_elections_by_status(self, conn):
        items = list_elections(conn, status="upcoming")
        assert len(items) >= 1

    def test_update_election(self, conn):
        ok = update_election(
            conn, self._eid, status="active",
            irregularities=["ballot_stuffing"], turnout_pct=62.5,
            result_summary="Ongoing", risk_level="high",
        )
        assert ok
        item = get_election(conn, self._eid)
        assert item["status"] == "active"
        assert item["turnout_pct"] == 62.5
        assert item["risk_level"] == "high"
        assert "ballot_stuffing" in item["irregularities"]

    def test_update_nonexistent(self, conn):
        ok = update_election(conn, "nonexistent-election", status="completed")
        assert not ok

    def test_create_second_election(self, conn):
        eid = create_election(conn, "GE", "parliamentary", "2026-11-01")
        assert eid
        item = get_election(conn, eid)
        assert item["country_code"] == "GE"
        assert item["risk_level"] == "normal"

    def test_get_nonexistent(self, conn):
        item = get_election(conn, "nonexistent")
        assert item is None


# ─── Nuclear Proliferation ──────────────────────────────────

from detection.nuclear_proliferation import (
    record_event as record_nuclear_event,
    get_event as get_nuclear_event,
    list_events as list_nuclear_events,
    update_status as update_nuclear_status,
    get_country_profile as get_nuclear_profile,
)


class TestNuclearProliferation:
    _nid = None

    def test_record_event(self, conn):
        nid = record_nuclear_event(
            conn, "IR", "enrichment", 75,
            facility_name="Natanz", lat=33.72, lng=51.72,
            description="Enrichment to 60% purity detected",
            evidence=["satellite_imagery", "iaea_report"],
            source_type="satellite",
        )
        assert nid
        TestNuclearProliferation._nid = nid

    def test_get_event(self, conn):
        item = get_nuclear_event(conn, self._nid)
        assert item is not None
        assert item["country_code"] == "IR"
        assert item["event_type"] == "enrichment"
        assert item["severity"] == 75
        assert item["facility_name"] == "Natanz"
        assert "satellite_imagery" in item["evidence"]

    def test_list_events(self, conn):
        items = list_nuclear_events(conn, country_code="IR")
        assert len(items) >= 1

    def test_list_events_by_type(self, conn):
        items = list_nuclear_events(conn, event_type="enrichment")
        assert len(items) >= 1

    def test_update_status(self, conn):
        ok = update_nuclear_status(conn, self._nid, "confirmed")
        assert ok
        item = get_nuclear_event(conn, self._nid)
        assert item["status"] == "confirmed"

    def test_update_invalid_status(self, conn):
        ok = update_nuclear_status(conn, self._nid, "invalid_status")
        assert not ok

    def test_country_profile(self, conn):
        # Add more events for profile
        record_nuclear_event(conn, "IR", "missile", 65, description="Missile test")
        record_nuclear_event(conn, "IR", "rhetoric", 40, description="Inflammatory speech")
        profile = get_nuclear_profile(conn, "IR")
        assert profile["country_code"] == "IR"
        assert profile["total_events"] >= 3
        assert profile["on_watchlist"] is True

    def test_country_profile_not_watchlisted(self, conn):
        record_nuclear_event(conn, "BR", "facility", 20, description="Research reactor")
        profile = get_nuclear_profile(conn, "BR")
        assert profile["on_watchlist"] is False

    def test_get_nonexistent(self, conn):
        item = get_nuclear_event(conn, "nonexistent")
        assert item is None


# ─── Migration / Refugee Tracking ──────────────────────────

from detection.migration_tracking import (
    record_flow, get_flow, list_flows, update_flow, get_crisis_summary,
)


class TestMigrationTracking:
    _fid = None

    def test_record_flow(self, conn):
        fid = record_flow(
            conn, "SY", "refugee", dest_country="TR",
            transit_countries=["LB", "JO"],
            estimated_count=150000, severity=80,
            route_description="Northern corridor via Aleppo",
            push_factors=["civil_war", "economic_collapse"],
            pull_factors=["proximity", "existing_diaspora"],
        )
        assert fid
        TestMigrationTracking._fid = fid

    def test_get_flow(self, conn):
        item = get_flow(conn, self._fid)
        assert item is not None
        assert item["origin_country"] == "SY"
        assert item["dest_country"] == "TR"
        assert item["estimated_count"] == 150000
        assert "civil_war" in item["push_factors"]

    def test_list_flows(self, conn):
        items = list_flows(conn, origin_country="SY")
        assert len(items) >= 1

    def test_list_flows_by_dest(self, conn):
        items = list_flows(conn, dest_country="TR")
        assert len(items) >= 1

    def test_update_flow(self, conn):
        ok = update_flow(conn, self._fid, status="seasonal", estimated_count=120000, severity=65)
        assert ok
        item = get_flow(conn, self._fid)
        assert item["status"] == "seasonal"
        assert item["estimated_count"] == 120000
        assert item["severity"] == 65

    def test_update_nonexistent(self, conn):
        ok = update_flow(conn, "nonexistent-flow", status="resolved")
        assert not ok

    def test_crisis_summary(self, conn):
        # Add a second flow
        record_flow(conn, "VE", "economic", dest_country="CO", estimated_count=80000, severity=70)
        summary = get_crisis_summary(conn)
        assert summary["active_flows"] >= 0 or summary["emerging_flows"] >= 0
        assert "by_origin_country" in summary

    def test_get_nonexistent(self, conn):
        item = get_flow(conn, "nonexistent")
        assert item is None


# ─── Cyber Incident Tracking ──────────────────────────────

from detection.cyber_incidents import (
    record_incident, get_incident, list_incidents, update_incident,
    get_threat_landscape,
)


class TestCyberIncidents:
    _cid = None

    def test_record_incident(self, conn):
        cid = record_incident(
            conn, "ransomware", 85,
            target_sector="healthcare", target_country="US",
            target_org="Regional Hospital Network",
            attributed_to="LockBit", attribution_confidence="moderate",
            attack_vector="phishing",
            iocs={"sha256": "abc123", "c2_domain": "evil.example.com"},
            impact="50k patient records encrypted",
        )
        assert cid
        TestCyberIncidents._cid = cid

    def test_get_incident(self, conn):
        item = get_incident(conn, self._cid)
        assert item is not None
        assert item["incident_type"] == "ransomware"
        assert item["severity"] == 85
        assert item["target_org"] == "Regional Hospital Network"
        assert item["iocs"]["sha256"] == "abc123"

    def test_list_incidents(self, conn):
        items = list_incidents(conn, target_country="US")
        assert len(items) >= 1

    def test_list_incidents_by_type(self, conn):
        items = list_incidents(conn, incident_type="ransomware")
        assert len(items) >= 1

    def test_update_incident(self, conn):
        ok = update_incident(
            conn, self._cid, status="contained",
            attributed_to="LockBit 3.0", attribution_confidence="high",
        )
        assert ok
        item = get_incident(conn, self._cid)
        assert item["status"] == "contained"
        assert item["attributed_to"] == "LockBit 3.0"
        assert item["attribution_confidence"] == "high"

    def test_update_nonexistent(self, conn):
        ok = update_incident(conn, "nonexistent-incident", status="resolved")
        assert not ok

    def test_threat_landscape(self, conn):
        # Add more incidents
        record_incident(conn, "apt", 90, target_country="US", attributed_to="APT29")
        record_incident(conn, "ddos", 45, target_country="GB")
        record_incident(conn, "data_breach", 70, target_country="US", target_sector="finance")
        landscape = get_threat_landscape(conn)
        assert landscape["total_incidents"] >= 4
        assert "by_incident_type" in landscape
        assert "by_threat_actor" in landscape

    def test_get_nonexistent(self, conn):
        item = get_incident(conn, "nonexistent")
        assert item is None


# ─── Custom Event Tagging ─────────────────────────────────

from intelligence.event_tagging import (
    add_tag, remove_tag, get_event_tags, find_events_by_tag,
    list_all_tags, bulk_tag,
)


class TestEventTagging:
    def test_add_tag(self, conn):
        tid = add_tag(conn, "evt-domain-0", "critical", "priority", created_by="analyst1")
        assert tid

    def test_add_tag_custom(self, conn):
        tid = add_tag(conn, "evt-domain-0", "iran-nuclear", "watchlist")
        assert tid

    def test_get_event_tags(self, conn):
        tags = get_event_tags(conn, "evt-domain-0")
        assert len(tags) >= 2
        tag_names = [t["tag_name"] for t in tags]
        assert "critical" in tag_names
        assert "iran-nuclear" in tag_names

    def test_tag_normalization(self, conn):
        """Tags should be lowercased and trimmed."""
        tid = add_tag(conn, "evt-domain-1", "  URGENT  ", "custom")
        assert tid
        tags = get_event_tags(conn, "evt-domain-1")
        tag_names = [t["tag_name"] for t in tags]
        assert "urgent" in tag_names

    def test_find_events_by_tag(self, conn):
        events = find_events_by_tag(conn, "critical")
        assert len(events) >= 1
        assert events[0]["event_id"] == "evt-domain-0"

    def test_list_all_tags(self, conn):
        tags = list_all_tags(conn)
        assert len(tags) >= 3
        tag_names = [t["tag_name"] for t in tags]
        assert "critical" in tag_names

    def test_bulk_tag(self, conn):
        event_ids = [f"evt-domain-{i}" for i in range(5)]
        count = bulk_tag(conn, event_ids, "batch-test", "auto", "system")
        assert count >= 5

    def test_remove_tag(self, conn):
        ok = remove_tag(conn, "evt-domain-0", "critical")
        assert ok
        tags = get_event_tags(conn, "evt-domain-0")
        tag_names = [t["tag_name"] for t in tags]
        assert "critical" not in tag_names

    def test_remove_nonexistent_tag(self, conn):
        ok = remove_tag(conn, "evt-domain-0", "nonexistent-tag")
        assert not ok

    def test_tag_color_defaults(self, conn):
        tid = add_tag(conn, "evt-domain-2", "priority-check", "priority")
        tags = get_event_tags(conn, "evt-domain-2")
        priority_tag = [t for t in tags if t["tag_name"] == "priority-check"]
        assert len(priority_tag) == 1
        assert priority_tag[0]["color"] == "#ef4444"  # red for priority


# ─── EXIF Extraction ──────────────────────────────────────

from geo.exif_extraction import parse_exif_from_dict, store_exif, get_exif, list_exif, find_exif_near


class TestExifExtraction:
    _eid = None

    def test_parse_exif_dms(self, conn):
        """Parse EXIF with DMS GPS coordinates."""
        exif = {
            "Make": "Canon",
            "Model": "EOS R5",
            "DateTimeOriginal": "2026:03:15 14:30:00",
            "GPSLatitude": [33, 20, 15.0],
            "GPSLatitudeRef": "N",
            "GPSLongitude": [44, 23, 45.0],
            "GPSLongitudeRef": "E",
            "GPSAltitude": 35.5,
            "ImageWidth": 8192,
            "ImageHeight": 5464,
        }
        parsed = parse_exif_from_dict(exif)
        assert parsed["camera_make"] == "Canon"
        assert parsed["camera_model"] == "EOS R5"
        assert parsed["latitude"] is not None
        assert 33.3 < parsed["latitude"] < 33.4
        assert 44.3 < parsed["longitude"] < 44.4
        assert parsed["altitude"] == 35.5
        assert parsed["image_width"] == 8192

    def test_parse_exif_decimal(self, conn):
        """Parse EXIF with decimal GPS coordinates."""
        exif = {
            "camera_make": "Sony",
            "gps_lat": 48.8566,
            "gps_lat_ref": "N",
            "gps_lng": 2.3522,
            "gps_lng_ref": "E",
        }
        parsed = parse_exif_from_dict(exif)
        assert parsed["camera_make"] == "Sony"
        assert parsed["latitude"] == 48.8566
        assert parsed["longitude"] == 2.3522

    def test_parse_exif_south_west(self, conn):
        """Southern and western coordinates should be negative."""
        exif = {
            "gps_lat": 23.5,
            "gps_lat_ref": "S",
            "gps_lng": 46.6,
            "gps_lng_ref": "W",
        }
        parsed = parse_exif_from_dict(exif)
        assert parsed["latitude"] == -23.5
        assert parsed["longitude"] == -46.6

    def test_store_and_get_exif(self, conn):
        parsed = parse_exif_from_dict({
            "Make": "Nikon", "Model": "D850",
            "GPSLatitude": [33, 20, 0], "GPSLatitudeRef": "N",
            "GPSLongitude": [44, 23, 0], "GPSLongitudeRef": "E",
        })
        eid = store_exif(conn, parsed, source_url="https://example.com/img.jpg",
                         filename="img.jpg", linked_event_id="evt-domain-0")
        assert eid
        TestExifExtraction._eid = eid

        item = get_exif(conn, eid)
        assert item is not None
        assert item["camera_make"] == "Nikon"
        assert item["camera_model"] == "D850"
        assert item["filename"] == "img.jpg"

    def test_list_exif(self, conn):
        items = list_exif(conn)
        assert len(items) >= 1

    def test_list_exif_by_event(self, conn):
        items = list_exif(conn, linked_event_id="evt-domain-0")
        assert len(items) >= 1

    def test_find_exif_near(self, conn):
        items = find_exif_near(conn, 33.33, 44.38, radius_deg=0.5)
        assert len(items) >= 1

    def test_find_exif_near_no_results(self, conn):
        items = find_exif_near(conn, -50.0, -70.0, radius_deg=0.1)
        assert len(items) == 0

    def test_get_nonexistent(self, conn):
        item = get_exif(conn, "nonexistent")
        assert item is None


# ─── Reverse Geocoding ────────────────────────────────────

from geo.reverse_geocoding import (
    reverse_geocode, reverse_geocode_offline, batch_reverse_geocode, get_geocode_stats,
)


class TestReverseGeocoding:
    def test_offline_iraq(self, conn):
        result = reverse_geocode_offline(33.0, 44.0)
        assert result["country_code"] == "IQ"
        assert result["country_name"] == "Iraq"
        assert result["resolution"] == "country_level"

    def test_offline_france(self, conn):
        result = reverse_geocode_offline(48.8, 2.3)
        assert result["country_code"] == "FR"
        assert result["country_name"] == "France"

    def test_offline_us(self, conn):
        result = reverse_geocode_offline(38.9, -77.0)
        assert result["country_code"] == "US"

    def test_offline_ocean(self, conn):
        """Middle of Pacific Ocean should return unknown."""
        result = reverse_geocode_offline(0.0, -170.0)
        assert result["country_code"] is None
        assert result["resolution"] == "unknown"

    def test_reverse_geocode_cached(self, conn):
        # Use unique coords unlikely to be cached by other tests
        result1 = reverse_geocode(conn, 52.52, 13.41)  # Berlin
        assert result1["country_code"] == "DE"

        # Second call near same point should hit cache
        result2 = reverse_geocode(conn, 52.53, 13.42)
        assert result2["country_code"] == "DE"
        assert result2["from_cache"] is True

    def test_reverse_geocode_no_cache(self, conn):
        result = reverse_geocode(conn, 48.8, 2.3, use_cache=False)
        assert result["country_code"] == "FR"
        assert result["from_cache"] is False

    def test_batch_reverse_geocode(self, conn):
        coords = [(33.0, 44.0), (48.8, 2.3), (38.9, -77.0)]
        results = batch_reverse_geocode(conn, coords)
        assert len(results) == 3
        codes = [r["country_code"] for r in results]
        assert "IQ" in codes
        assert "FR" in codes
        assert "US" in codes

    def test_geocode_stats(self, conn):
        stats = get_geocode_stats(conn)
        assert stats["total_cached"] >= 1
        assert isinstance(stats["by_country"], dict)


# ─── PDF Export ────────────────────────────────────────────

from intelligence.pdf_export import export_events_pdf, export_brief_pdf, SimplePDFWriter


class TestPDFExport:
    def test_simple_pdf_writer(self, conn):
        pdf = SimplePDFWriter()
        pdf.add_page(["Title", "Line 1", "Line 2"])
        pdf.add_page(["Page 2", "More content"])
        data = pdf.render()
        assert data.startswith(b"%PDF-1.4")
        assert b"%%EOF" in data

    def test_export_events_pdf(self, conn):
        pdf_bytes = export_events_pdf(conn, limit=5, title="Test Report")
        assert pdf_bytes
        assert pdf_bytes.startswith(b"%PDF-1.4")
        assert len(pdf_bytes) > 100

    def test_export_events_pdf_by_category(self, conn):
        pdf_bytes = export_events_pdf(conn, category="political")
        assert pdf_bytes
        assert pdf_bytes.startswith(b"%PDF-1.4")

    def test_export_events_pdf_by_country(self, conn):
        pdf_bytes = export_events_pdf(conn, country_code="IQ")
        assert pdf_bytes
        assert pdf_bytes.startswith(b"%PDF-1.4")

    def test_export_events_pdf_by_ids(self, conn):
        pdf_bytes = export_events_pdf(conn, event_ids=["evt-domain-0", "evt-domain-1"])
        assert pdf_bytes
        assert pdf_bytes.startswith(b"%PDF-1.4")

    def test_export_brief_pdf_not_found(self, conn):
        result = export_brief_pdf(conn, "nonexistent-brief")
        assert result is None

    def test_export_brief_pdf(self, conn):
        """Create a brief and export it."""
        # Seed a brief for this test
        conn.execute(
            """INSERT OR IGNORE INTO briefs
               (id, brief_type, title, summary, content, created_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            ("test-brief-001", "situation", "Test Brief",
             "Test brief summary",
             "This is a longer content body for the intelligence brief. "
             "It contains multiple sentences describing the situation."),
        )
        conn.commit()
        pdf_bytes = export_brief_pdf(conn, "test-brief-001")
        assert pdf_bytes
        assert pdf_bytes.startswith(b"%PDF-1.4")
        assert len(pdf_bytes) > 100

    def test_empty_pdf(self, conn):
        """Export with no matching events should still produce valid PDF."""
        pdf_bytes = export_events_pdf(conn, country_code="ZZ")  # no events for ZZ
        assert pdf_bytes
        assert pdf_bytes.startswith(b"%PDF-1.4")

"""
API Tests — Election monitoring, nuclear proliferation, migration tracking,
cyber incidents, event tagging, EXIF extraction, reverse geocoding, PDF export.
"""
import os
import sys
import tempfile
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
        now = datetime.now(timezone.utc)
        for i in range(10):
            ts = (now - timedelta(hours=i)).isoformat()
            db.execute(
                """INSERT OR IGNORE INTO events
                   (id, source, title, category, severity,
                    country_code, region, timestamp, summary)
                   VALUES (?, 'test', ?, 'political', ?, 'IQ', 'Middle East', ?, ?)""",
                (f"evt-dtapi-{i}", f"API domain event {i}", 55 + i * 2,
                 ts, f"Summary for API domain event {i}"),
            )
        # Seed a brief for PDF export
        db.execute(
            """INSERT OR IGNORE INTO briefs
               (id, brief_type, title, summary, content, created_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            ("api-brief-001", "situation", "API Test Brief",
             "API test brief",
             "Content of the API test brief for PDF export testing."),
        )
        db.commit()
        yield c
    os.unlink(_test_db_path)


# ─── Election Monitoring API ──────────────────────────────

class TestElectionAPI:
    _eid = None

    def test_create_election(self, client):
        resp = client.post("/api/elections", json={
            "country_code": "NG",
            "election_type": "presidential",
            "election_date": "2027-02-25",
            "candidates": ["Candidate X", "Candidate Y"],
            "risk_level": "elevated",
            "risk_factors": ["violence", "voter_suppression"],
            "region": "West Africa",
            "analyst": "api-test",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "election_id" in data
        TestElectionAPI._eid = data["election_id"]

    def test_get_election(self, client):
        resp = client.get(f"/api/elections/{self._eid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["country_code"] == "NG"
        assert data["election_type"] == "presidential"

    def test_list_elections(self, client):
        resp = client.get("/api/elections")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_list_elections_by_country(self, client):
        resp = client.get("/api/elections?country_code=NG")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_update_election(self, client):
        resp = client.put(f"/api/elections/{self._eid}", json={
            "status": "active",
            "irregularities": ["vote_buying"],
            "turnout_pct": 48.3,
            "risk_level": "high",
        })
        assert resp.status_code == 200
        assert resp.json()["updated"] is True

    def test_update_nonexistent(self, client):
        resp = client.put("/api/elections/nonexistent", json={"status": "completed"})
        assert resp.status_code == 404


# ─── Nuclear Proliferation API ─────────────────────────────

class TestNuclearAPI:
    _nid = None

    def test_create_nuclear_event(self, client):
        resp = client.post("/api/nuclear", json={
            "country_code": "KP",
            "event_type": "test",
            "severity": 95,
            "facility_name": "Punggye-ri",
            "lat": 41.28,
            "lng": 129.08,
            "description": "Possible underground nuclear test",
            "evidence": ["seismic_data", "satellite"],
            "source_type": "seismic",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "event_id" in data
        TestNuclearAPI._nid = data["event_id"]

    def test_get_nuclear_event(self, client):
        resp = client.get(f"/api/nuclear/{self._nid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["country_code"] == "KP"
        assert data["severity"] == 95

    def test_list_nuclear_events(self, client):
        resp = client.get("/api/nuclear")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_list_nuclear_by_country(self, client):
        resp = client.get("/api/nuclear?country_code=KP")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_update_nuclear_status(self, client):
        resp = client.put(f"/api/nuclear/{self._nid}/status?status=confirmed")
        assert resp.status_code == 200
        assert resp.json()["updated"] is True

    def test_nuclear_profile(self, client):
        resp = client.get("/api/nuclear/profile/KP")
        assert resp.status_code == 200
        data = resp.json()
        assert data["country_code"] == "KP"
        assert data["on_watchlist"] is True

    def test_get_nonexistent(self, client):
        resp = client.get("/api/nuclear/nonexistent")
        assert resp.status_code == 404


# ─── Migration API ─────────────────────────────────────────

class TestMigrationAPI:
    _fid = None

    def test_create_flow(self, client):
        resp = client.post("/api/migration", json={
            "origin_country": "AF",
            "flow_type": "refugee",
            "dest_country": "PK",
            "transit_countries": ["IR"],
            "estimated_count": 200000,
            "severity": 75,
            "route_description": "Eastern border crossing",
            "push_factors": ["conflict", "taliban_rule"],
            "pull_factors": ["pashtun_diaspora"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "flow_id" in data
        TestMigrationAPI._fid = data["flow_id"]

    def test_get_flow(self, client):
        resp = client.get(f"/api/migration/{self._fid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["origin_country"] == "AF"

    def test_list_flows(self, client):
        resp = client.get("/api/migration")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_list_flows_by_origin(self, client):
        resp = client.get("/api/migration?origin_country=AF")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_update_flow(self, client):
        resp = client.put(f"/api/migration/{self._fid}", json={
            "status": "seasonal",
            "estimated_count": 180000,
        })
        assert resp.status_code == 200
        assert resp.json()["updated"] is True

    def test_crisis_summary(self, client):
        resp = client.get("/api/migration/crisis")
        assert resp.status_code == 200
        data = resp.json()
        assert "active_flows" in data or "emerging_flows" in data

    def test_get_nonexistent(self, client):
        resp = client.get("/api/migration/nonexistent")
        assert resp.status_code == 404


# ─── Cyber Incident API ───────────────────────────────────

class TestCyberAPI:
    _cid = None

    def test_create_incident(self, client):
        resp = client.post("/api/cyber", json={
            "incident_type": "apt",
            "severity": 88,
            "target_sector": "government",
            "target_country": "DE",
            "target_org": "Bundestag",
            "attributed_to": "Fancy Bear",
            "attribution_confidence": "moderate",
            "attack_vector": "spear_phishing",
            "iocs": {"ip": "10.0.0.1", "domain": "malware.example.com"},
            "impact": "Data exfiltration from parliamentary network",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "incident_id" in data
        TestCyberAPI._cid = data["incident_id"]

    def test_get_incident(self, client):
        resp = client.get(f"/api/cyber/{self._cid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["incident_type"] == "apt"
        assert data["target_country"] == "DE"

    def test_list_incidents(self, client):
        resp = client.get("/api/cyber")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_list_incidents_by_country(self, client):
        resp = client.get("/api/cyber?target_country=DE")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_update_incident(self, client):
        resp = client.put(f"/api/cyber/{self._cid}", json={
            "status": "contained",
            "attribution_confidence": "high",
        })
        assert resp.status_code == 200
        assert resp.json()["updated"] is True

    def test_threat_landscape(self, client):
        # Add another incident
        client.post("/api/cyber", json={
            "incident_type": "ransomware",
            "severity": 70,
            "target_country": "US",
        })
        resp = client.get("/api/cyber/landscape")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_incidents"] >= 2

    def test_get_nonexistent(self, client):
        resp = client.get("/api/cyber/nonexistent")
        assert resp.status_code == 404


# ─── Event Tagging API ────────────────────────────────────

class TestTaggingAPI:
    def test_add_tag(self, client):
        resp = client.post("/api/tags", json={
            "event_id": "evt-dtapi-0",
            "tag_name": "escalation",
            "tag_category": "priority",
            "created_by": "api-test",
        })
        assert resp.status_code == 200
        assert "tag_id" in resp.json()

    def test_add_tag_custom(self, client):
        resp = client.post("/api/tags", json={
            "event_id": "evt-dtapi-0",
            "tag_name": "middle-east",
            "tag_category": "watchlist",
        })
        assert resp.status_code == 200

    def test_get_tags_for_event(self, client):
        resp = client.get("/api/tags/event/evt-dtapi-0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2

    def test_find_events_by_tag(self, client):
        resp = client.get("/api/tags/events/escalation")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert data["tag"] == "escalation"

    def test_list_all_tags(self, client):
        resp = client.get("/api/tags")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2

    def test_bulk_tag(self, client):
        resp = client.post("/api/tags/bulk", json={
            "event_ids": ["evt-dtapi-1", "evt-dtapi-2", "evt-dtapi-3"],
            "tag_name": "bulk-test",
            "tag_category": "auto",
            "created_by": "system",
        })
        assert resp.status_code == 200
        assert resp.json()["tagged"] >= 3

    def test_delete_tag(self, client):
        resp = client.delete("/api/tags/evt-dtapi-0/escalation")
        assert resp.status_code == 200
        assert resp.json()["removed"] is True

    def test_delete_nonexistent_tag(self, client):
        resp = client.delete("/api/tags/evt-dtapi-0/nonexistent")
        assert resp.status_code == 200
        assert resp.json()["removed"] is False


# ─── EXIF API ─────────────────────────────────────────────

class TestExifAPI:
    _eid = None

    def test_post_exif(self, client):
        resp = client.post("/api/exif", json={
            "exif_data": {
                "Make": "Apple",
                "Model": "iPhone 15 Pro",
                "GPSLatitude": [33, 20, 0],
                "GPSLatitudeRef": "N",
                "GPSLongitude": [44, 23, 0],
                "GPSLongitudeRef": "E",
                "ImageWidth": 4032,
                "ImageHeight": 3024,
            },
            "source_url": "https://example.com/photo.jpg",
            "filename": "photo.jpg",
            "linked_event_id": "evt-dtapi-0",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "exif_id" in data
        assert data["parsed"]["camera_make"] == "Apple"
        TestExifAPI._eid = data["exif_id"]

    def test_get_exif(self, client):
        resp = client.get(f"/api/exif/{self._eid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["camera_make"] == "Apple"

    def test_list_exif(self, client):
        resp = client.get("/api/exif")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_list_exif_by_event(self, client):
        resp = client.get("/api/exif?linked_event_id=evt-dtapi-0")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_exif_near(self, client):
        resp = client.get("/api/exif/near?lat=33.33&lng=44.38&radius=0.5")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_exif_near_no_results(self, client):
        resp = client.get("/api/exif/near?lat=-50.0&lng=-70.0&radius=0.1")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_get_nonexistent(self, client):
        resp = client.get("/api/exif/nonexistent")
        assert resp.status_code == 404


# ─── Reverse Geocoding API ────────────────────────────────

class TestGeocodeAPI:
    def test_reverse_geocode(self, client):
        resp = client.get("/api/geocode/reverse?lat=33.0&lng=44.0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["country_code"] == "IQ"

    def test_reverse_geocode_france(self, client):
        resp = client.get("/api/geocode/reverse?lat=48.8&lng=2.3")
        assert resp.status_code == 200
        data = resp.json()
        assert data["country_code"] == "FR"

    def test_batch_geocode(self, client):
        resp = client.post("/api/geocode/batch", json={
            "coordinates": [[33.0, 44.0], [48.8, 2.3], [38.9, -77.0]],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        codes = [r["country_code"] for r in data["results"]]
        assert "IQ" in codes
        assert "FR" in codes

    def test_geocode_stats(self, client):
        resp = client.get("/api/geocode/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cached"] >= 1


# ─── PDF Export API ────────────────────────────────────────

class TestPDFExportAPI:
    def test_export_events_pdf(self, client):
        resp = client.post("/api/export/pdf", json={
            "limit": 5,
            "title": "Test Intelligence Report",
        })
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF-1.4")

    def test_export_events_pdf_by_category(self, client):
        resp = client.post("/api/export/pdf", json={
            "category": "political",
        })
        assert resp.status_code == 200
        assert resp.content.startswith(b"%PDF-1.4")

    def test_export_events_pdf_by_country(self, client):
        resp = client.post("/api/export/pdf", json={
            "country_code": "IQ",
        })
        assert resp.status_code == 200
        assert resp.content.startswith(b"%PDF-1.4")

    def test_export_events_pdf_by_ids(self, client):
        resp = client.post("/api/export/pdf", json={
            "event_ids": ["evt-dtapi-0", "evt-dtapi-1"],
        })
        assert resp.status_code == 200
        assert resp.content.startswith(b"%PDF-1.4")

    def test_export_brief_pdf(self, client):
        resp = client.get("/api/export/pdf/brief/api-brief-001")
        assert resp.status_code == 200
        assert resp.content.startswith(b"%PDF-1.4")

    def test_export_brief_pdf_not_found(self, client):
        resp = client.get("/api/export/pdf/brief/nonexistent")
        assert resp.status_code == 404

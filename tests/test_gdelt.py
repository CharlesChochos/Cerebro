"""
Phase 1 Validation Tests — GDELT ingestion, parsing, API endpoints.
"""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection
from db.migrate import run_migrations
from ingestion.gdelt import _parse_row, fetch_latest_export, ingest


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = get_connection(path)
    run_migrations(conn)
    yield conn
    conn.close()
    os.unlink(path)


class TestGDELTParsing:
    """Test GDELT CSV row parsing."""

    def test_parse_valid_row(self):
        row = {
            "GlobalEventID": "12345",
            "Actor1Name": "UNITED STATES",
            "Actor2Name": "RUSSIA",
            "EventCode": "190",
            "EventRootCode": "19",
            "GoldsteinScale": "-10.0",
            "NumSources": "5",
            "NumMentions": "20",
            "NumArticles": "10",
            "AvgTone": "-3.5",
            "QuadClass": "4",
            "ActionGeo_Lat": "55.7558",
            "ActionGeo_Long": "37.6173",
            "ActionGeo_CountryCode": "RS",
            "ActionGeo_FullName": "Moscow, Russia",
            "DATEADDED": "20260409120000",
            "SOURCEURL": "https://example.com/article",
        }
        event = _parse_row(row)
        assert event is not None
        assert event["source"] == "gdelt"
        assert event["source_id"] == "gdelt-12345"
        assert event["category"] == "military"  # Root code 19 = Fight
        assert event["severity"] == 100.0  # -10 Goldstein = max severity
        assert event["latitude"] == 55.7558
        assert event["longitude"] == 37.6173
        assert event["country_code"] == "RS"
        assert "UNITED STATES" in event["title"]
        assert "RUSSIA" in event["title"]

    def test_parse_empty_row(self):
        event = _parse_row({})
        assert event is None

    def test_parse_political_event(self):
        row = {
            "GlobalEventID": "99999",
            "Actor1Name": "FRANCE",
            "Actor2Name": "GERMANY",
            "EventCode": "040",
            "EventRootCode": "04",
            "GoldsteinScale": "1.0",
            "NumSources": "3",
            "NumMentions": "5",
            "NumArticles": "3",
            "AvgTone": "1.5",
            "QuadClass": "1",
            "ActionGeo_Lat": "48.8566",
            "ActionGeo_Long": "2.3522",
            "ActionGeo_CountryCode": "FR",
            "ActionGeo_FullName": "Paris, France",
            "DATEADDED": "20260409150000",
            "SOURCEURL": "https://example.com/politics",
        }
        event = _parse_row(row)
        assert event is not None
        assert event["category"] == "political"
        assert event["severity"] < 50  # Positive Goldstein = low severity

    def test_severity_mapping(self):
        """Goldstein -10 = severity 100, +10 = severity 0."""
        row_base = {
            "GlobalEventID": "1",
            "Actor1Name": "A",
            "Actor2Name": "B",
            "EventCode": "190",
            "EventRootCode": "19",
            "NumSources": "1",
            "NumMentions": "1",
            "NumArticles": "1",
            "AvgTone": "0",
            "QuadClass": "4",
            "DATEADDED": "20260409120000",
            "SOURCEURL": "",
        }

        # Most severe
        row_base["GoldsteinScale"] = "-10.0"
        row_base["GlobalEventID"] = "1"
        event = _parse_row(row_base)
        assert event["severity"] == 100.0

        # Least severe
        row_base["GoldsteinScale"] = "10.0"
        row_base["GlobalEventID"] = "2"
        event = _parse_row(row_base)
        assert event["severity"] == 0.0

    def test_entities_extracted(self):
        row = {
            "GlobalEventID": "5555",
            "Actor1Name": "NATO",
            "Actor2Name": "UKRAINE",
            "EventCode": "050",
            "EventRootCode": "05",
            "GoldsteinScale": "3.0",
            "NumSources": "1",
            "NumMentions": "1",
            "NumArticles": "1",
            "AvgTone": "0",
            "QuadClass": "1",
            "DATEADDED": "20260409120000",
            "SOURCEURL": "",
        }
        event = _parse_row(row)
        entities = json.loads(event["entities_json"])
        assert len(entities) == 2
        assert entities[0]["name"] == "NATO"
        assert entities[1]["name"] == "UKRAINE"


class TestGDELTFetch:
    """Test GDELT API fetch (live network required)."""

    @pytest.mark.skipif(
        os.environ.get("SKIP_NETWORK") == "1",
        reason="Network tests disabled",
    )
    def test_fetch_returns_events(self):
        rows = fetch_latest_export()
        assert len(rows) > 0
        assert "GlobalEventID" in rows[0]


class TestGDELTIngestion:
    """Test full ingestion pipeline into database."""

    def test_ingest_with_mock_data(self, db, monkeypatch):
        """Mock fetch_latest_export to test ingestion without network."""
        mock_rows = [
            {
                "GlobalEventID": str(i),
                "Actor1Name": f"ACTOR_{i}",
                "Actor2Name": "TARGET",
                "EventCode": "190",
                "EventRootCode": "19",
                "GoldsteinScale": "-5.0",
                "NumSources": "3",
                "NumMentions": "10",
                "NumArticles": "5",
                "AvgTone": "-2.0",
                "QuadClass": "4",
                "ActionGeo_Lat": "40.0",
                "ActionGeo_Long": "-74.0",
                "ActionGeo_CountryCode": "US",
                "ActionGeo_FullName": "New York, United States",
                "DATEADDED": "20260409120000",
                "SOURCEURL": f"https://example.com/{i}",
            }
            for i in range(60)
        ]

        monkeypatch.setattr("ingestion.gdelt.fetch_latest_export", lambda: mock_rows)
        stats = ingest(db)

        assert stats["fetched"] == 60
        assert stats["inserted"] == 60
        assert stats["errors"] == 0

        # Verify in DB
        count = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert count == 60

        # Verify FTS
        fts_count = db.execute("SELECT COUNT(*) FROM events_fts").fetchone()[0]
        assert fts_count == 60

    def test_dedup_on_reingest(self, db, monkeypatch):
        """Same events should not be duplicated on second ingest."""
        mock_rows = [
            {
                "GlobalEventID": "100",
                "Actor1Name": "FRANCE",
                "Actor2Name": "UK",
                "EventCode": "040",
                "EventRootCode": "04",
                "GoldsteinScale": "1.0",
                "NumSources": "1",
                "NumMentions": "1",
                "NumArticles": "1",
                "AvgTone": "0",
                "QuadClass": "1",
                "DATEADDED": "20260409120000",
                "SOURCEURL": "https://example.com/100",
            }
        ]

        monkeypatch.setattr("ingestion.gdelt.fetch_latest_export", lambda: mock_rows)

        stats1 = ingest(db)
        assert stats1["inserted"] == 1

        stats2 = ingest(db)
        assert stats2["inserted"] == 0
        assert stats2["skipped"] == 1

        count = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert count == 1

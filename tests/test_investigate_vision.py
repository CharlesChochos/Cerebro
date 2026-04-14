"""
Tests — Autonomous deep-dive investigation agent + satellite change detection.
Covers: intelligence/investigate.py, detection/satellite_vision.py,
        API endpoints, surprise index API.
"""
import json
import os
import sys
import tempfile
import uuid
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ─── Module-level imports for unit tests ─────────────────────

from intelligence.investigate import (
    TOOLS,
    TOOL_DISPATCH,
    _exec_query_events_near,
    _exec_query_news,
    _exec_query_commodity_prices,
    _exec_query_vessel_history,
    _exec_query_entity_network,
    _exec_query_satellite_changes,
    _build_trigger_context,
)
from detection.satellite_vision import (
    _load_image_as_base64,
    _find_image_pair,
)


# ─── Fixtures ────────────────────────────────────────────────

_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["CEREBRO_DB_PATH"] = _test_db_path

from db.connection import get_connection
from db.migrate import run_migrations


@pytest.fixture(scope="module")
def conn():
    """Get a migrated test database connection."""
    c = get_connection(_test_db_path)
    run_migrations(c)
    yield c
    c.close()
    os.unlink(_test_db_path)


@pytest.fixture(scope="module")
def seeded_conn(conn):
    """Seed with test data."""
    # Events
    for i in range(5):
        conn.execute(
            """INSERT INTO events (id, source, title, summary, category, severity,
                   confidence, latitude, longitude, country_code, timestamp, ingested_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', ?), datetime('now'))""",
            (
                str(uuid.uuid4()), "test", f"Test event {i}",
                f"Summary for event {i}", "military" if i % 2 == 0 else "economic",
                50 + i * 10, 0.8, 33.5 + i * 0.1, 44.4 + i * 0.1,
                "IQ", f"-{i} hours",
            ),
        )

    # Entities
    eid1 = str(uuid.uuid4())
    eid2 = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO entities (id, name, entity_type, first_seen, last_seen) VALUES (?, ?, ?, datetime('now'), datetime('now'))",
        (eid1, "Test Corp", "organization"),
    )
    conn.execute(
        "INSERT INTO entities (id, name, entity_type, first_seen, last_seen) VALUES (?, ?, ?, datetime('now'), datetime('now'))",
        (eid2, "John Doe", "person"),
    )
    conn.execute(
        "INSERT INTO entity_relations (id, source_entity_id, target_entity_id, relation_type, confidence, source_event_id) VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), eid1, eid2, "employs", 0.9, None),
    )

    # Vessels + vessel tracks
    conn.execute(
        """INSERT INTO vessels (mmsi, name, vessel_type, flag, latitude, longitude,
               speed, course, destination)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("123456789", "Test Vessel", "cargo", "PA", 33.5, 44.4, 12.0, 180, "BASRA"),
    )
    conn.execute(
        """INSERT INTO vessel_tracks (mmsi, timestamp, latitude, longitude, speed, course)
           VALUES (?, datetime('now'), ?, ?, ?, ?)""",
        ("123456789", 33.5, 44.4, 12.0, 180),
    )

    # Satellite cache
    for i in range(2):
        conn.execute(
            """INSERT INTO satellite_cache (id, source, lat, lng, capture_date, image_url,
                   cloud_cover, resolution_m, bbox_json, annotations, thumbnail_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                f"sat-{i}", "sentinel2", 33.5, 44.5, f"2026-0{3 - i}-15", "",
                10 + i * 5, 10, json.dumps([44.0, 33.0, 45.0, 34.0]),
                None, "",
            ),
        )

    # Alerts
    conn.execute(
        """INSERT INTO alerts (id, event_id, alert_type, severity, confidence,
               title, description, region, country_code)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("alert-test", None, "anomaly", 85, 0.8,
         "High severity alert", "Military buildup detected", "Middle East", "IQ"),
    )

    conn.commit()
    return conn


# ─── Investigation Tool Dispatch Tests ───────────────────────

class TestToolDefinitions:

    def test_all_tools_defined(self):
        tool_names = {t["name"] for t in TOOLS}
        expected = {
            "query_events_near", "query_vessel_history",
            "query_entity_network", "query_news",
            "query_commodity_prices", "query_satellite_changes",
        }
        assert tool_names == expected

    def test_all_tools_have_dispatch(self):
        for tool in TOOLS:
            assert tool["name"] in TOOL_DISPATCH

    def test_tool_schemas_valid(self):
        for tool in TOOLS:
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"
            assert "properties" in tool["input_schema"]


class TestToolExecutors:

    def test_query_events_near(self, seeded_conn):
        result = json.loads(_exec_query_events_near(seeded_conn, {
            "lat": 33.5, "lng": 44.4, "radius_km": 200, "days": 7,
        }))
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_query_events_near_with_category(self, seeded_conn):
        result = json.loads(_exec_query_events_near(seeded_conn, {
            "lat": 33.5, "lng": 44.4, "radius_km": 200, "days": 7,
            "category": "military",
        }))
        assert isinstance(result, list)
        for ev in result:
            assert ev["category"] == "military"

    def test_query_vessel_history(self, seeded_conn):
        result = json.loads(_exec_query_vessel_history(seeded_conn, {
            "mmsi": "123456789",
        }))
        assert result["vessel"] is not None
        assert result["vessel"]["name"] == "Test Vessel"

    def test_query_vessel_history_unknown(self, seeded_conn):
        result = json.loads(_exec_query_vessel_history(seeded_conn, {
            "mmsi": "000000000",
        }))
        assert result["vessel"] is None

    def test_query_entity_network(self, seeded_conn):
        result = json.loads(_exec_query_entity_network(seeded_conn, {
            "entity_name": "Test Corp",
        }))
        assert result["entity"] is not None
        assert result["entity"]["name"] == "Test Corp"
        assert len(result["relationships"]) >= 1

    def test_query_entity_network_not_found(self, seeded_conn):
        result = json.loads(_exec_query_entity_network(seeded_conn, {
            "entity_name": "Nonexistent Entity XYZ",
        }))
        assert result["entity"] is None

    def test_query_news(self, seeded_conn):
        result = json.loads(_exec_query_news(seeded_conn, {
            "keyword": "Test event",
        }))
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_query_news_with_region(self, seeded_conn):
        result = json.loads(_exec_query_news(seeded_conn, {
            "keyword": "Test", "region": "IQ",
        }))
        assert isinstance(result, list)

    def test_query_commodity_prices(self, seeded_conn):
        result = json.loads(_exec_query_commodity_prices(seeded_conn, {
            "commodity": "oil", "days": 30,
        }))
        assert "commodity" in result
        assert result["commodity"] == "oil"

    def test_query_satellite_changes(self, seeded_conn):
        result = json.loads(_exec_query_satellite_changes(seeded_conn, {
            "lat": 33.5, "lng": 44.5, "radius_km": 100,
        }))
        assert "images_found" in result
        assert result["images_found"] >= 1


class TestBuildTriggerContext:

    def test_event_context(self, seeded_conn):
        # Get an event ID
        row = seeded_conn.execute("SELECT id FROM events LIMIT 1").fetchone()
        ctx = _build_trigger_context(seeded_conn, "event", row["id"])
        assert "ANOMALY TRIGGER: Event" in ctx
        assert "Test event" in ctx

    def test_alert_context(self, seeded_conn):
        ctx = _build_trigger_context(seeded_conn, "alert", "alert-test")
        assert "ANOMALY TRIGGER: Alert" in ctx
        assert "anomaly" in ctx

    def test_vessel_context(self, seeded_conn):
        ctx = _build_trigger_context(seeded_conn, "vessel", "123456789")
        assert "ANOMALY TRIGGER: Vessel" in ctx
        assert "Test Vessel" in ctx

    def test_unknown_trigger(self, seeded_conn):
        ctx = _build_trigger_context(seeded_conn, "unknown", "xyz")
        assert "details unavailable" in ctx


# ─── Satellite Vision Tests ──────────────────────────────────

class TestSatelliteVision:

    def test_find_image_pair(self, seeded_conn):
        after, before = _find_image_pair(seeded_conn, 33.5, 44.5, radius_km=100)
        assert after is not None
        assert before is not None
        # After should be more recent
        assert after["capture_date"] >= before["capture_date"]

    def test_find_image_pair_no_images(self, seeded_conn):
        after, before = _find_image_pair(seeded_conn, 0, 0, radius_km=1)
        assert after is None

    def test_load_image_nonexistent(self):
        result = _load_image_as_base64("/nonexistent/path.png")
        assert result is None

    def test_load_image_unsupported_ext(self, tmp_path):
        f = tmp_path / "test.xyz"
        f.write_bytes(b"data")
        result = _load_image_as_base64(str(f))
        assert result is None

    def test_load_image_png(self, tmp_path):
        f = tmp_path / "test.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n")
        result = _load_image_as_base64(str(f))
        assert result is not None
        data, media = result
        assert media == "image/png"
        assert len(data) > 0


# ─── Investigation Agent (mocked Claude) ─────────────────────

class TestInvestigateWithMock:

    @patch("intelligence.investigate.CLAUDE_API_KEY", "test-key")
    @patch("intelligence.investigate.anthropic.Anthropic")
    def test_investigate_single_round(self, MockClient, seeded_conn):
        """Mock a simple investigation where Claude returns a report immediately."""
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 200

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = json.dumps({
            "title": "Investigation: Military activity",
            "summary": "Analysis of military events near coordinates.",
            "key_findings": ["Finding 1", "Finding 2"],
            "risk_assessment": "high",
            "confidence": 0.85,
            "recommended_actions": ["Monitor region"],
            "entities_of_interest": ["Test Corp"],
            "sources_consulted": [],
        })
        mock_response.content = [text_block]

        client_instance = MockClient.return_value
        client_instance.messages.create.return_value = mock_response

        from intelligence.investigate import investigate
        event_id = seeded_conn.execute("SELECT id FROM events LIMIT 1").fetchone()["id"]
        result = investigate(seeded_conn, "event", event_id)

        assert "error" not in result
        assert result["investigation_id"]
        assert result["report"]["risk_assessment"] == "high"
        assert result["report"]["confidence"] == 0.85

    @patch("intelligence.investigate.CLAUDE_API_KEY", "test-key")
    @patch("intelligence.investigate.anthropic.Anthropic")
    def test_investigate_with_tool_calls(self, MockClient, seeded_conn):
        """Mock investigation with tool use round then final report."""
        # First response: Claude wants to use a tool
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "query_events_near"
        tool_block.input = {"lat": 33.5, "lng": 44.4, "radius_km": 100}
        tool_block.id = "tool-1"

        resp1 = MagicMock()
        resp1.stop_reason = "tool_use"
        resp1.usage.input_tokens = 50
        resp1.usage.output_tokens = 30
        resp1.content = [tool_block]

        # Second response: Claude returns final report
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = json.dumps({
            "title": "Investigation complete",
            "summary": "Found related events nearby.",
            "key_findings": ["3 military events within 100km"],
            "risk_assessment": "medium",
            "confidence": 0.7,
            "recommended_actions": [],
            "entities_of_interest": [],
            "sources_consulted": ["query_events_near"],
        })

        resp2 = MagicMock()
        resp2.stop_reason = "end_turn"
        resp2.usage.input_tokens = 100
        resp2.usage.output_tokens = 200
        resp2.content = [text_block]

        client_instance = MockClient.return_value
        client_instance.messages.create.side_effect = [resp1, resp2]

        from intelligence.investigate import investigate
        event_id = seeded_conn.execute("SELECT id FROM events LIMIT 1").fetchone()["id"]
        result = investigate(seeded_conn, "event", event_id)

        assert "error" not in result
        assert result["tool_calls_made"] == 1
        assert "query_events_near" in result["tools_used"]

    @patch("intelligence.investigate.CLAUDE_API_KEY", "")
    def test_investigate_no_api_key(self, seeded_conn):
        from intelligence.investigate import investigate
        result = investigate(seeded_conn, "event", "some-id")
        assert result["error"] == "no_api_key"


class TestInvestigationStorage:

    @patch("intelligence.investigate.CLAUDE_API_KEY", "test-key")
    @patch("intelligence.investigate.anthropic.Anthropic")
    def test_list_investigations(self, MockClient, seeded_conn):
        from intelligence.investigate import list_investigations
        items = list_investigations(seeded_conn)
        # Should have investigations from previous tests
        assert isinstance(items, list)

    @patch("intelligence.investigate.CLAUDE_API_KEY", "test-key")
    @patch("intelligence.investigate.anthropic.Anthropic")
    def test_get_investigation(self, MockClient, seeded_conn):
        from intelligence.investigate import get_investigation
        # Get first investigation
        row = seeded_conn.execute("SELECT id FROM investigations LIMIT 1").fetchone()
        if row:
            inv = get_investigation(seeded_conn, row["id"])
            assert inv is not None
            assert "title" in inv

    def test_get_investigation_not_found(self, seeded_conn):
        from intelligence.investigate import get_investigation
        result = get_investigation(seeded_conn, "nonexistent-id")
        assert result is None


# ─── Satellite Change Detection (mocked Claude) ─────────────

class TestSatelliteVisionMocked:

    @patch("detection.satellite_vision.CLAUDE_API_KEY", "test-key")
    @patch("detection.satellite_vision.anthropic.Anthropic")
    def test_compare_metadata_mode(self, MockClient, seeded_conn):
        """Compare two images in metadata-only mode (no actual files)."""
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 150
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = json.dumps({
            "changes_detected": True,
            "change_count": 2,
            "changes": [
                {"type": "military_deployment", "description": "New vehicles",
                 "severity": "high", "confidence": 0.7},
                {"type": "new_construction", "description": "Building expansion",
                 "severity": "medium", "confidence": 0.6},
            ],
            "overall_assessment": "Significant military activity detected.",
            "strategic_significance": "high",
        })
        mock_response.content = [text_block]

        client_instance = MockClient.return_value
        client_instance.messages.create.return_value = mock_response

        from detection.satellite_vision import compare_images_vision
        result = compare_images_vision(seeded_conn, "sat-1", "sat-0")

        assert "error" not in result
        assert result["mode"] == "metadata"
        assert result["result"]["changes_detected"] is True
        assert result["result"]["change_count"] == 2

    @patch("detection.satellite_vision.CLAUDE_API_KEY", "")
    def test_compare_no_api_key(self, seeded_conn):
        from detection.satellite_vision import compare_images_vision
        result = compare_images_vision(seeded_conn, "sat-0", "sat-1")
        assert result["error"] == "no_api_key"

    def test_compare_missing_images(self, seeded_conn):
        from detection.satellite_vision import compare_images_vision
        with patch("detection.satellite_vision.CLAUDE_API_KEY", "test-key"):
            result = compare_images_vision(seeded_conn, "nonexistent", "also-nonexistent")
        assert "error" in result

    @patch("detection.satellite_vision.CLAUDE_API_KEY", "test-key")
    @patch("detection.satellite_vision.anthropic.Anthropic")
    def test_detect_at_location(self, MockClient, seeded_conn):
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 80
        mock_response.usage.output_tokens = 120
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = json.dumps({
            "changes_detected": False, "change_count": 0,
            "changes": [], "overall_assessment": "No changes.",
            "strategic_significance": "low",
        })
        mock_response.content = [text_block]
        MockClient.return_value.messages.create.return_value = mock_response

        from detection.satellite_vision import detect_changes_at_location
        result = detect_changes_at_location(seeded_conn, 33.5, 44.5)
        assert "error" not in result

    def test_list_change_detections(self, seeded_conn):
        from detection.satellite_vision import list_change_detections
        items = list_change_detections(seeded_conn)
        assert isinstance(items, list)


# ─── API Tests ───────────────────────────────────────────────

from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


class TestInvestigateAPI:

    def test_list_investigations(self, client):
        resp = client.get("/api/investigations")
        assert resp.status_code == 200
        assert "investigations" in resp.json()

    def test_get_investigation_not_found(self, client):
        resp = client.get("/api/investigations/nonexistent")
        assert resp.status_code == 404

    def test_launch_invalid_trigger_type(self, client):
        resp = client.post("/api/investigate", json={
            "trigger_type": "invalid",
            "trigger_id": "test",
        })
        assert resp.status_code == 400


class TestSatelliteVisionAPI:

    def test_list_detections(self, client):
        resp = client.get("/api/vision/detections")
        assert resp.status_code == 200
        assert "detections" in resp.json()

    def test_get_detection_not_found(self, client):
        resp = client.get("/api/vision/detections/nonexistent")
        assert resp.status_code == 404


class TestSurpriseIndexAPI:

    def test_get_surprise_index(self, client):
        resp = client.get("/api/predictions/surprise")
        assert resp.status_code == 200
        data = resp.json()
        assert "surprise_score" in data
        assert "date" in data

    def test_get_surprise_index_with_date(self, client):
        resp = client.get("/api/predictions/surprise?date=2026-04-01")
        assert resp.status_code == 200
        data = resp.json()
        assert data["date"] == "2026-04-01"

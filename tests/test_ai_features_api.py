"""
API Tests — Multi-perspective, grounding firewall, leading indicators.
"""
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

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

        # Seed events across categories for indicator detection
        categories = ["military", "political", "economic", "health", "environmental"]
        for day_offset in range(60):
            for cat in categories:
                for i in range(2):
                    eid = f"evt-aiapi-{day_offset}-{cat}-{i}"
                    ts = (now - timedelta(days=day_offset)).isoformat()
                    db.execute(
                        """INSERT OR IGNORE INTO events
                           (id, source, title, category, severity, country_code, region, timestamp, summary)
                           VALUES (?, 'test', ?, ?, ?, 'US', 'Test Region', ?, ?)""",
                        (eid, f"AI API {cat} event {day_offset}#{i}", cat,
                         40 + day_offset % 40, ts, f"Summary of {cat}"),
                    )

        # Seed a brief
        db.execute(
            """INSERT OR IGNORE INTO briefs
               (id, brief_type, title, content, summary, event_ids, entity_ids, grounding_score)
               VALUES (?, 'daily', 'API Test Brief',
                       'Report [evt-aiapi-0-military-0] and [fake-ref-123] found.',
                       'Test', '[]', '[]', 0.0)""",
            ("brief-api-test-1",),
        )

        # Seed a fusion signal
        db.execute(
            """INSERT OR IGNORE INTO fusion_signals
               (id, signal_type, title, description, severity, confidence,
                event_ids, entity_ids, grounding_score)
               VALUES (?, 'economic_crisis', 'API Test Signal',
                       'Crisis detected [evt-aiapi-0-economic-0]',
                       70, 0.7, '[]', '[]', 0.0)""",
            ("fusion-api-test-1",),
        )

        db.commit()
        yield c
    os.unlink(_test_db_path)


# ─── Multi-Perspective API ────────────────────────────────────

class TestPerspectiveAPI:
    def test_create_simulation_by_region(self, client):
        with patch("intelligence.perspectives.CLAUDE_API_KEY", ""):
            resp = client.post("/api/perspectives", json={"region": "Test Region"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["simulation_id"] is not None
        assert len(data["actors"]) >= 2
        assert len(data["perspectives"]) >= 2

    def test_create_simulation_no_params(self, client):
        resp = client.post("/api/perspectives", json={})
        assert resp.status_code == 400

    def test_list_simulations(self, client):
        resp = client.get("/api/perspectives")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_get_simulation(self, client):
        sims = client.get("/api/perspectives").json()["simulations"]
        sid = sims[0]["id"]
        resp = client.get(f"/api/perspectives/{sid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == sid

    def test_get_simulation_not_found(self, client):
        resp = client.get("/api/perspectives/nonexistent")
        assert resp.status_code == 404

    def test_create_simulation_with_actors(self, client):
        with patch("intelligence.perspectives.CLAUDE_API_KEY", ""):
            resp = client.post("/api/perspectives", json={
                "region": "Test Region",
                "actors": ["United States", "China"],
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "United States" in data["actors"]
        assert "China" in data["actors"]


# ─── Grounding Firewall API ──────────────────────────────────

class TestGroundingAPI:
    def test_audit_text(self, client):
        with patch("intelligence.grounding.CLAUDE_API_KEY", ""):
            resp = client.post("/api/grounding/audit", json={
                "text": "Event [evt-aiapi-0-military-0] and [fake-ref-abc] found.",
                "target_type": "test",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["audit_id"] is not None
        assert data["grounding_score"] == 0.5
        assert len(data["flagged_claims"]) >= 1

    def test_sanitize_text(self, client):
        with patch("intelligence.grounding.CLAUDE_API_KEY", ""):
            resp = client.post("/api/grounding/sanitize", json={
                "text": "Event [evt-aiapi-0-military-0] and [fake-ref-xyz] detected.",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "UNVERIFIED" in data["sanitized_text"]
        assert data["flagged_count"] >= 1

    def test_audit_brief(self, client):
        with patch("intelligence.grounding.CLAUDE_API_KEY", ""):
            resp = client.post("/api/grounding/audit-brief/brief-api-test-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["target_type"] == "brief"

    def test_audit_brief_not_found(self, client):
        resp = client.post("/api/grounding/audit-brief/nonexistent")
        assert resp.status_code == 404

    def test_audit_fusion(self, client):
        with patch("intelligence.grounding.CLAUDE_API_KEY", ""):
            resp = client.post("/api/grounding/audit-fusion/fusion-api-test-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["target_type"] == "fusion_signal"

    def test_audit_fusion_not_found(self, client):
        resp = client.post("/api/grounding/audit-fusion/nonexistent")
        assert resp.status_code == 404

    def test_list_audits(self, client):
        resp = client.get("/api/grounding/audits")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_get_audit(self, client):
        audits = client.get("/api/grounding/audits").json()["audits"]
        aid = audits[0]["id"]
        resp = client.get(f"/api/grounding/audits/{aid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == aid

    def test_get_audit_not_found(self, client):
        resp = client.get("/api/grounding/audits/nonexistent")
        assert resp.status_code == 404


# ─── Leading Indicators API ──────────────────────────────────

class TestIndicatorsAPI:
    def test_get_known_patterns(self, client):
        resp = client.get("/api/indicators/patterns")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["patterns"]) >= 5

    def test_check_indicators(self, client):
        resp = client.get("/api/indicators/check")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_checked" in data
        assert "firing" in data
        assert "all_indicators" in data

    def test_check_indicators_with_country(self, client):
        resp = client.get("/api/indicators/check?country_code=US")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["all_indicators"], list)

    def test_scan_indicators(self, client):
        resp = client.post("/api/indicators/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_patterns_checked" in data
        assert "firing" in data
        assert "indicators" in data

    def test_list_indicators(self, client):
        resp = client.get("/api/indicators")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["indicators"], list)

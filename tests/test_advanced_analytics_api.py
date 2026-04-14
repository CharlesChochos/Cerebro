"""
API Tests — Historical analogs, cascade models, narrative divergence,
contrarian signals, narrative arcs.
"""
import json
import os
import sys
import tempfile
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

        categories = ["military", "political", "economic", "health", "environmental"]
        sources = ["gdelt", "acled", "reuters", "bbc", "xinhua"]
        countries = ["US", "CN", "RU", "IR", "UA"]

        for day_offset in range(60):
            for cat_idx, cat in enumerate(categories):
                for i in range(2):
                    eid = f"evt-advapi-{day_offset}-{cat}-{i}"
                    ts = (now - timedelta(days=day_offset)).isoformat()
                    cc = countries[day_offset % len(countries)]
                    src = sources[(day_offset + cat_idx) % len(sources)]
                    sev = 30 + day_offset % 50
                    db.execute(
                        """INSERT OR IGNORE INTO events
                           (id, source, title, category, severity,
                            country_code, region, timestamp, summary)
                           VALUES (?, ?, ?, ?, ?, ?, 'Test Region', ?, ?)""",
                        (eid, src,
                         f"API test {cat} event {day_offset}#{i} in {cc}",
                         cat, sev, cc, ts,
                         f"Summary of {cat} event in {cc}"),
                    )

        # Trigger event for cascade tests
        db.execute(
            """INSERT OR IGNORE INTO events
               (id, source, title, category, severity,
                country_code, region, timestamp, summary)
               VALUES (?, 'test', 'Earthquake in coastal city', 'environmental', 80,
                       'JP', 'East Asia', ?, 'Major earthquake detected')""",
            ("evt-advapi-trigger", now.isoformat()),
        )

        db.commit()
        yield c
    os.unlink(_test_db_path)


# ─── Historical Analogs API ───────────────────────────────────

class TestAnalogsAPI:
    def test_search_analogs(self, client):
        with patch("intelligence.historical_analogs.CLAUDE_API_KEY", ""):
            resp = client.post("/api/analogs/search", json={
                "region": "Test Region", "category": "military",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_analogs_checked"] >= 10
        assert data["matches_found"] >= 1

    def test_search_no_params(self, client):
        resp = client.post("/api/analogs/search", json={})
        assert resp.status_code == 400

    def test_get_catalog(self, client):
        resp = client.get("/api/analogs/catalog")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 10

    def test_list_analogs(self, client):
        resp = client.get("/api/analogs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_get_analog(self, client):
        analogs = client.get("/api/analogs").json()["analogs"]
        aid = analogs[0]["id"]
        resp = client.get(f"/api/analogs/{aid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == aid

    def test_get_analog_not_found(self, client):
        resp = client.get("/api/analogs/nonexistent")
        assert resp.status_code == 404


# ─── Cascade Models API ──────────────────────────────────────

class TestCascadesAPI:
    def test_create_cascade(self, client):
        with patch("intelligence.cascade_model.CLAUDE_API_KEY", ""):
            resp = client.post("/api/cascades/model", json={
                "trigger_description": "Economic sanctions imposed on country",
                "category": "economic",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "cascade_id" in data
        assert data["total_steps"] >= 1
        assert len(data["cascade_steps"]) >= 1

    def test_create_cascade_with_event(self, client):
        with patch("intelligence.cascade_model.CLAUDE_API_KEY", ""):
            resp = client.post("/api/cascades/model", json={
                "event_id": "evt-advapi-trigger",
            })
        assert resp.status_code == 200
        assert resp.json()["total_steps"] >= 1

    def test_create_cascade_no_input(self, client):
        resp = client.post("/api/cascades/model", json={})
        assert resp.status_code == 400

    def test_get_rules(self, client):
        resp = client.get("/api/cascades/rules")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 10

    def test_list_cascades(self, client):
        resp = client.get("/api/cascades")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_cascade(self, client):
        cascades = client.get("/api/cascades").json()["cascades"]
        cid = cascades[0]["id"]
        resp = client.get(f"/api/cascades/{cid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == cid

    def test_get_cascade_not_found(self, client):
        resp = client.get("/api/cascades/nonexistent")
        assert resp.status_code == 404


# ─── Narrative Divergence API ─────────────────────────────────

class TestDivergenceAPI:
    def test_analyze_divergence(self, client):
        with patch("intelligence.narrative_divergence.CLAUDE_API_KEY", ""):
            resp = client.post("/api/divergence/analyze", json={
                "topic": "military",
                "region": "Test Region",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "divergence_score" in data
        assert isinstance(data["divergence_score"], float)

    def test_list_divergences(self, client):
        resp = client.get("/api/divergence")
        assert resp.status_code == 200
        assert isinstance(resp.json()["analyses"], list)

    def test_get_divergence_not_found(self, client):
        resp = client.get("/api/divergence/nonexistent")
        assert resp.status_code == 404


# ─── Contrarian Signals API ──────────────────────────────────

class TestContrarianAPI:
    def test_scan_contrarian(self, client):
        resp = client.post("/api/contrarian/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_signals" in data
        assert "by_type" in data
        assert "signals" in data

    def test_scan_with_country(self, client):
        resp = client.post("/api/contrarian/scan?country_code=US")
        assert resp.status_code == 200

    def test_list_contrarian(self, client):
        resp = client.get("/api/contrarian")
        assert resp.status_code == 200
        assert isinstance(resp.json()["signals"], list)

    def test_get_contrarian_not_found(self, client):
        resp = client.get("/api/contrarian/nonexistent")
        assert resp.status_code == 404


# ─── Narrative Arcs API ──────────────────────────────────────

class TestArcsAPI:
    def test_track_arc(self, client):
        with patch("detection.narrative_arcs.CLAUDE_API_KEY", ""):
            resp = client.post("/api/arcs/track", json={
                "topic": "military",
                "region": "Test Region",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "arc_id" in data
        assert data["arc_phase"] in ("emerging", "escalating", "peak", "declining", "dormant")
        assert 0 <= data["intensity"] <= 1.0

    def test_list_arcs(self, client):
        resp = client.get("/api/arcs")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_arc(self, client):
        arcs = client.get("/api/arcs").json()["arcs"]
        aid = arcs[0]["id"]
        resp = client.get(f"/api/arcs/{aid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == aid

    def test_get_arc_not_found(self, client):
        resp = client.get("/api/arcs/nonexistent")
        assert resp.status_code == 404

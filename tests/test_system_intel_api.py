"""
API Tests — Ambient narration, proactive push, system self-awareness,
historical replay, commodity dependency, capital flight.
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
        # Seed some events for scans
        db = get_db()
        now = datetime.now(timezone.utc)
        for i in range(15):
            ts = (now - timedelta(hours=i)).isoformat()
            db.execute(
                """INSERT OR IGNORE INTO events
                   (id, source, title, category, severity,
                    country_code, region, timestamp, summary)
                   VALUES (?, 'test', ?, 'economic', ?, 'IQ', 'Middle East', ?, ?)""",
                (f"evt-sysapi-{i}", f"API econ event {i}", 65 + i,
                 ts, f"Summary {i}"),
            )
        db.commit()
        yield c
    os.unlink(_test_db_path)


# ─── Ambient Narration API ──────────────────────────────────

class TestNarrationAPI:
    def test_log_activity(self, client):
        resp = client.post("/api/narration/log", json={
            "component": "ingestion",
            "message": "Ingested 200 events from GDELT",
            "level": "info",
            "metadata": {"source": "gdelt", "count": 200},
        })
        assert resp.status_code == 200
        assert "log_id" in resp.json()

    def test_log_more(self, client):
        client.post("/api/narration/log", json={
            "component": "processing", "message": "Classified events", "level": "info",
        })
        client.post("/api/narration/log", json={
            "component": "detection", "message": "Anomaly detected", "level": "warning",
        })

    def test_activity_feed(self, client):
        resp = client.get("/api/narration/feed?minutes=120")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 3

    def test_feed_filter(self, client):
        resp = client.get("/api/narration/feed?component=ingestion&minutes=120")
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        assert all(e["component"] == "ingestion" for e in entries)

    def test_summary(self, client):
        resp = client.get("/api/narration/summary?minutes=120")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_entries"] >= 3

    def test_ticker(self, client):
        resp = client.get("/api/narration/ticker?limit=5")
        assert resp.status_code == 200
        assert len(resp.json()["ticker"]) >= 1


# ─── Proactive Push API ─────────────────────────────────────

class TestProactiveAPI:
    def test_create_alert(self, client):
        resp = client.post("/api/proactive/alerts", json={
            "alert_type": "threshold_breach",
            "title": "Severity spike in Iraq",
            "priority": "high",
            "country_code": "IQ",
        })
        assert resp.status_code == 200
        assert "alert_id" in resp.json()

    def test_create_more(self, client):
        client.post("/api/proactive/alerts", json={
            "alert_type": "anomaly", "title": "Unusual pattern", "priority": "medium",
        })

    def test_list_alerts(self, client):
        resp = client.get("/api/proactive/alerts?hours=24")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 2

    def test_get_alert(self, client):
        items = client.get("/api/proactive/alerts?hours=24").json()["alerts"]
        resp = client.get(f"/api/proactive/alerts/{items[0]['id']}")
        assert resp.status_code == 200

    def test_get_alert_not_found(self, client):
        resp = client.get("/api/proactive/alerts/nonexistent")
        assert resp.status_code == 404

    def test_update_status(self, client):
        items = client.get("/api/proactive/alerts?hours=24").json()["alerts"]
        resp = client.put(f"/api/proactive/alerts/{items[0]['id']}", json={
            "status": "acknowledged",
        })
        assert resp.status_code == 200

    def test_scan(self, client):
        resp = client.post("/api/proactive/scan?hours=24")
        assert resp.status_code == 200
        assert isinstance(resp.json()["alerts"], list)


# ─── System Self-Awareness API ──────────────────────────────

class TestSystemAPI:
    def test_register_component(self, client):
        resp = client.post("/api/system/components", json={
            "component_name": "api-test-ingester",
            "component_type": "ingestion",
        })
        assert resp.status_code == 200
        assert "component_id" in resp.json()

    def test_heartbeat(self, client):
        resp = client.post("/api/system/heartbeat", json={
            "component_name": "api-test-ingester",
            "status": "healthy",
            "metrics": {"events": 100},
        })
        assert resp.status_code == 200

    def test_heartbeat_not_registered(self, client):
        resp = client.post("/api/system/heartbeat", json={
            "component_name": "nonexistent",
            "status": "healthy",
        })
        assert resp.status_code == 404

    def test_list_components(self, client):
        resp = client.get("/api/system/components")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_component(self, client):
        resp = client.get("/api/system/components/api-test-ingester")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_get_component_not_found(self, client):
        resp = client.get("/api/system/components/nonexistent")
        assert resp.status_code == 404

    def test_error_report(self, client):
        resp = client.post("/api/system/error", json={
            "component_name": "api-test-ingester",
            "error_message": "Connection timeout",
        })
        assert resp.status_code == 200

    def test_database_metrics(self, client):
        resp = client.get("/api/system/database")
        assert resp.status_code == 200
        data = resp.json()
        assert "table_counts" in data
        assert data["total_rows"] >= 0

    def test_diagnostic(self, client):
        resp = client.get("/api/system/diagnostic")
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_status"] in ("healthy", "degraded", "critical")


# ─── Historical Replay API ──────────────────────────────────

class TestReplayAPI:
    def test_create_snapshot(self, client):
        resp = client.post("/api/replay/snapshots", json={
            "label": "API test snapshot",
        })
        assert resp.status_code == 200
        assert "snapshot_id" in resp.json()

    def test_list_snapshots(self, client):
        resp = client.get("/api/replay/snapshots")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_snapshot(self, client):
        snaps = client.get("/api/replay/snapshots").json()["snapshots"]
        resp = client.get(f"/api/replay/snapshots/{snaps[0]['id']}")
        assert resp.status_code == 200

    def test_get_snapshot_not_found(self, client):
        resp = client.get("/api/replay/snapshots/nonexistent")
        assert resp.status_code == 404

    def test_replay_events(self, client):
        now = datetime.now(timezone.utc).isoformat()
        resp = client.get(f"/api/replay/events?at_time={now}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_events"] >= 1

    def test_timeline(self, client):
        resp = client.get("/api/replay/timeline?days=3&interval_hours=24")
        assert resp.status_code == 200
        assert len(resp.json()["points"]) >= 1


# ─── Commodity Dependency API ───────────────────────────────

class TestCommoditiesAPI:
    def test_seed(self, client):
        resp = client.post("/api/commodities/seed")
        assert resp.status_code == 200
        assert resp.json()["seeded"] >= 0  # May already be seeded

    def test_add_dependency(self, client):
        resp = client.post("/api/commodities", json={
            "country_code": "GB",
            "commodity_name": "Natural Gas",
            "dependency_type": "import",
            "share_pct": 40.0,
            "top_partners": ["NO", "QA"],
        })
        assert resp.status_code == 200
        assert "dependency_id" in resp.json()

    def test_list_commodities(self, client):
        resp = client.get("/api/commodities")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_list_by_country(self, client):
        resp = client.get("/api/commodities?country_code=GB")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_dependency(self, client):
        items = client.get("/api/commodities").json()["dependencies"]
        resp = client.get(f"/api/commodities/{items[0]['id']}")
        assert resp.status_code == 200

    def test_get_not_found(self, client):
        resp = client.get("/api/commodities/nonexistent")
        assert resp.status_code == 404

    def test_country_risk(self, client):
        # Seed first to ensure data
        client.post("/api/commodities/seed")
        resp = client.get("/api/commodities/risk/CN")
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_risk" in data

    def test_disruption_impact(self, client):
        resp = client.get("/api/commodities/disruption/Crude Oil")
        assert resp.status_code == 200
        data = resp.json()
        assert "most_vulnerable" in data


# ─── Capital Flight API ─────────────────────────────────────

class TestCapitalFlightAPI:
    def test_record_signal(self, client):
        resp = client.post("/api/capital-flight/signals", json={
            "country_code": "TR",
            "signal_type": "currency_drop",
            "indicator_value": 30.0,
            "baseline_value": 20.0,
            "description": "Lira dropped 50%",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "signal_id" in data
        assert data["severity"] > 0

    def test_record_more(self, client):
        client.post("/api/capital-flight/signals", json={
            "country_code": "TR", "signal_type": "bond_spread",
            "indicator_value": 500, "baseline_value": 150,
        })

    def test_list_signals(self, client):
        resp = client.get("/api/capital-flight/signals?days=30")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 2

    def test_list_by_country(self, client):
        resp = client.get("/api/capital-flight/signals?country_code=TR&days=30")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 2

    def test_get_signal(self, client):
        items = client.get("/api/capital-flight/signals?days=30").json()["signals"]
        resp = client.get(f"/api/capital-flight/signals/{items[0]['id']}")
        assert resp.status_code == 200

    def test_get_not_found(self, client):
        resp = client.get("/api/capital-flight/signals/nonexistent")
        assert resp.status_code == 404

    def test_update_status(self, client):
        items = client.get("/api/capital-flight/signals?days=30").json()["signals"]
        resp = client.put(f"/api/capital-flight/signals/{items[0]['id']}", json={
            "status": "confirmed",
        })
        assert resp.status_code == 200

    def test_flight_risk(self, client):
        resp = client.get("/api/capital-flight/risk/TR?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_signals"] >= 1
        assert "risk_level" in data

    def test_scan(self, client):
        resp = client.post("/api/capital-flight/scan?days=24")
        assert resp.status_code == 200
        assert isinstance(resp.json()["signals"], list)

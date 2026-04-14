"""
Phase 11 API Tests — Reports, webhooks, widgets endpoints.
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

        # Seed events
        for i in range(8):
            db.execute(
                """INSERT OR IGNORE INTO events (id, source, title, category, severity, country_code, timestamp)
                   VALUES (?, 'test', ?, ?, ?, ?, ?)""",
                (
                    f"evt-api-out-{i}",
                    f"API output event {i}",
                    "military" if i % 3 == 0 else "economic",
                    40 + i * 7,
                    "US" if i < 5 else "GB",
                    (now - timedelta(days=i % 4)).isoformat(),
                ),
            )

        # Seed risk score
        db.execute(
            """INSERT OR IGNORE INTO risk_scores (id, scope_type, scope_value, score, trend, updated_at)
               VALUES (?, 'country', 'US', 72.0, 'rising', ?)""",
            (str(uuid.uuid4()), now.isoformat()),
        )

        # Seed prediction
        db.execute(
            """INSERT OR IGNORE INTO predictions (id, prediction, confidence, outcome, created_at)
               VALUES (?, 'API test prediction', 0.7, 'pending', ?)""",
            (str(uuid.uuid4()), now.isoformat()),
        )

        # Seed alerts
        db.execute(
            """INSERT OR IGNORE INTO alerts (id, title, severity, alert_type, acknowledged, country_code, created_at)
               VALUES (?, 'API Test Alert', 75, 'velocity_spike', 0, 'US', ?)""",
            (str(uuid.uuid4()), now.isoformat()),
        )

        db.commit()
        yield c
    os.unlink(_test_db_path)


# ─── Country Profile Endpoints ───────────────────────────────

class TestCountryProfileAPI:
    def test_generate_country_profile(self, client):
        with patch("intelligence.reports.CLAUDE_API_KEY", ""):
            resp = client.post("/api/reports/country-profile", json={
                "country_code": "US",
                "country_name": "United States",
                "days": 30,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["country_code"] == "US"
        assert data["profile_id"] is not None
        assert "executive_summary" in data

    def test_list_country_profiles(self, client):
        resp = client.get("/api/reports/country-profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_list_country_profiles_filter(self, client):
        resp = client.get("/api/reports/country-profiles?country_code=US")
        data = resp.json()
        assert all(p["country_code"] == "US" for p in data["profiles"])

    def test_get_country_profile(self, client):
        profiles = client.get("/api/reports/country-profiles").json()["profiles"]
        pid = profiles[0]["id"]
        resp = client.get(f"/api/reports/country-profiles/{pid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == pid

    def test_get_profile_not_found(self, client):
        resp = client.get("/api/reports/country-profiles/nonexistent")
        assert resp.status_code == 404


# ─── Weekly Report Endpoints ─────────────────────────────────

class TestWeeklyReportAPI:
    def test_generate_weekly_report(self, client):
        with patch("intelligence.reports.CLAUDE_API_KEY", ""):
            resp = client.post("/api/reports/weekly")
        assert resp.status_code == 200
        data = resp.json()
        assert data["report_id"] is not None
        assert "title" in data
        assert "executive_summary" in data

    def test_list_weekly_reports(self, client):
        resp = client.get("/api/reports/weekly")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_get_weekly_report(self, client):
        reports = client.get("/api/reports/weekly").json()["reports"]
        rid = reports[0]["id"]
        resp = client.get(f"/api/reports/weekly/{rid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == rid

    def test_get_report_not_found(self, client):
        resp = client.get("/api/reports/weekly/nonexistent")
        assert resp.status_code == 404


# ─── Webhook Endpoints ───────────────────────────────────────

class TestWebhookAPI:
    _webhook_id = None

    def test_create_webhook(self, client):
        resp = client.post("/api/webhooks", json={
            "name": "Test Webhook",
            "url": "https://httpbin.org/post",
            "event_types": ["alert", "new_report"],
            "secret": "test_secret_123",
            "filters": {"country_code": "US"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Webhook"
        assert data["event_types"] == ["alert", "new_report"]
        TestWebhookAPI._webhook_id = data["id"]

    def test_list_webhooks(self, client):
        resp = client.get("/api/webhooks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_get_webhook(self, client):
        resp = client.get(f"/api/webhooks/{TestWebhookAPI._webhook_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Webhook"

    def test_get_webhook_not_found(self, client):
        resp = client.get("/api/webhooks/nonexistent")
        assert resp.status_code == 404

    def test_update_webhook(self, client):
        resp = client.patch(f"/api/webhooks/{TestWebhookAPI._webhook_id}", json={
            "name": "Updated Webhook",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Webhook"

    def test_test_webhook(self, client):
        resp = client.post(f"/api/webhooks/{TestWebhookAPI._webhook_id}/test", json={
            "event_type": "test",
            "payload": {"hello": "world"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "log_id" in data
        # May or may not succeed depending on network, but endpoint works

    def test_webhook_logs(self, client):
        resp = client.get(f"/api/webhooks/{TestWebhookAPI._webhook_id}/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_delete_webhook(self, client):
        # Create one to delete
        create_resp = client.post("/api/webhooks", json={
            "name": "Delete Me",
            "url": "http://example.com/del",
            "event_types": ["test"],
        })
        del_id = create_resp.json()["id"]
        resp = client.delete(f"/api/webhooks/{del_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_delete_webhook_not_found(self, client):
        resp = client.delete("/api/webhooks/nonexistent")
        assert resp.status_code == 404


# ─── Widget Token Endpoints ──────────────────────────────────

class TestWidgetAPI:
    _token_id = None
    _token_value = None

    def test_create_widget_token(self, client):
        resp = client.post("/api/widgets/tokens", json={
            "widget_type": "risk_score",
            "scope": {"country_code": "US"},
            "hours_valid": 48,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["widget_type"] == "risk_score"
        assert data["active"] is True
        TestWidgetAPI._token_id = data["id"]
        TestWidgetAPI._token_value = data["token"]

    def test_create_invalid_widget_type(self, client):
        resp = client.post("/api/widgets/tokens", json={
            "widget_type": "invalid_type",
        })
        assert resp.status_code == 400

    def test_list_widget_tokens(self, client):
        resp = client.get("/api/widgets/tokens")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_get_widget_embed(self, client):
        resp = client.get(f"/api/widgets/embed?token={TestWidgetAPI._token_value}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["widget_type"] == "risk_score"
        assert "score" in data

    def test_get_widget_embed_invalid_token(self, client):
        resp = client.get("/api/widgets/embed?token=invalid_token_xyz")
        assert resp.status_code == 401

    def test_create_event_feed_token(self, client):
        resp = client.post("/api/widgets/tokens", json={
            "widget_type": "event_feed",
            "scope": {"country_code": "US"},
        })
        assert resp.status_code == 200
        token = resp.json()["token"]
        # Use it
        embed_resp = client.get(f"/api/widgets/embed?token={token}")
        assert embed_resp.status_code == 200
        data = embed_resp.json()
        assert data["widget_type"] == "event_feed"
        assert "events" in data

    def test_create_alert_ticker_token(self, client):
        resp = client.post("/api/widgets/tokens", json={
            "widget_type": "alert_ticker",
            "scope": {"country_code": "US"},
        })
        assert resp.status_code == 200
        token = resp.json()["token"]
        embed_resp = client.get(f"/api/widgets/embed?token={token}")
        assert embed_resp.status_code == 200
        assert embed_resp.json()["widget_type"] == "alert_ticker"

    def test_revoke_widget_token(self, client):
        resp = client.delete(f"/api/widgets/tokens/{TestWidgetAPI._token_id}")
        assert resp.status_code == 200
        assert resp.json()["revoked"] is True
        # Token should now be invalid
        embed_resp = client.get(f"/api/widgets/embed?token={TestWidgetAPI._token_value}")
        assert embed_resp.status_code == 401

    def test_revoke_token_not_found(self, client):
        resp = client.delete("/api/widgets/tokens/nonexistent")
        assert resp.status_code == 404

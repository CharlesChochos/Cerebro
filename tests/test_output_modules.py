"""
Phase 11 Tests — Output modules: reports, webhooks, widgets.
"""
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

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
    # Seed test data
    now = datetime.now(timezone.utc)
    for i in range(10):
        c.execute(
            """INSERT OR IGNORE INTO events (id, source, title, category, severity, country_code, timestamp)
               VALUES (?, 'test', ?, ?, ?, 'US', ?)""",
            (
                f"evt-output-{i}",
                f"Test event {i}",
                "military" if i % 2 == 0 else "political",
                50 + i * 5,
                (now - timedelta(days=i % 5)).isoformat(),
            ),
        )
    c.execute(
        """INSERT OR IGNORE INTO risk_scores (id, scope_type, scope_value, score, trend, updated_at)
           VALUES (?, 'country', 'US', 65.0, 'rising', ?)""",
        (str(uuid.uuid4()), now.isoformat()),
    )
    c.execute(
        """INSERT OR IGNORE INTO predictions (id, prediction, confidence, outcome, created_at)
           VALUES (?, 'Test prediction', 0.8, 'correct', ?)""",
        (str(uuid.uuid4()), now.isoformat()),
    )
    c.execute(
        """INSERT OR IGNORE INTO alerts (id, title, severity, alert_type, acknowledged, country_code, created_at)
           VALUES (?, 'Test Alert', 80, 'risk_threshold', 0, 'US', ?)""",
        (str(uuid.uuid4()), now.isoformat()),
    )
    c.commit()
    yield c
    c.close()
    os.unlink(path)


# ─── Reports ─────────────────────────────────────────────────

class TestCountryProfile:
    def test_gather_country_data(self, conn):
        from intelligence.reports import gather_country_data
        data = gather_country_data(conn, "US", days=30)
        assert data["event_count"] >= 1
        assert "events" in data
        assert "categories" in data
        assert "risk_score" in data

    def test_generate_country_profile_no_api_key(self, conn):
        from intelligence.reports import generate_country_profile
        with patch("intelligence.reports.CLAUDE_API_KEY", ""):
            profile = generate_country_profile(conn, "US", "United States", days=30)
        assert profile["country_code"] == "US"
        assert profile["country_name"] == "United States"
        assert profile["model_used"] is None
        assert "executive_summary" in profile
        assert "key_events" in profile
        assert "risk_score" in profile
        assert profile["profile_id"] is not None

    def test_profile_stored_in_db(self, conn):
        row = conn.execute(
            "SELECT * FROM country_profiles WHERE country_code = 'US' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert row["country_name"] == "United States"


class TestWeeklyReport:
    def test_generate_weekly_report_no_api_key(self, conn):
        from intelligence.reports import generate_weekly_report
        with patch("intelligence.reports.CLAUDE_API_KEY", ""):
            report = generate_weekly_report(conn)
        assert report["report_id"] is not None
        assert report["total_events"] >= 1
        assert "executive_summary" in report
        assert "trending_topics" in report
        assert "outlook" in report
        assert report["model_used"] is None

    def test_report_stored_in_db(self, conn):
        row = conn.execute(
            "SELECT * FROM weekly_reports ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert row["title"] is not None


# ─── Webhooks ────────────────────────────────────────────────

class TestWebhooks:
    def test_create_webhook(self, conn):
        from intelligence.webhooks import create_webhook
        wh = create_webhook(conn, "Test Hook", "https://example.com/hook", ["alert"], "mysecret")
        assert wh["id"] is not None
        assert wh["name"] == "Test Hook"
        assert wh["event_types"] == ["alert"]
        assert wh["active"] is True

    def test_list_webhooks(self, conn):
        from intelligence.webhooks import list_webhooks
        hooks = list_webhooks(conn)
        assert len(hooks) >= 1

    def test_get_webhook(self, conn):
        from intelligence.webhooks import list_webhooks, get_webhook
        hooks = list_webhooks(conn)
        wh = get_webhook(conn, hooks[0]["id"])
        assert wh is not None
        assert wh["name"] == hooks[0]["name"]

    def test_update_webhook(self, conn):
        from intelligence.webhooks import list_webhooks, update_webhook
        hooks = list_webhooks(conn)
        updated = update_webhook(conn, hooks[0]["id"], name="Updated Hook")
        assert updated["name"] == "Updated Hook"

    def test_sign_payload(self):
        from intelligence.webhooks import sign_payload, verify_signature
        sig = sign_payload("secret123", '{"test": true}')
        assert len(sig) == 64  # SHA256 hex
        assert verify_signature("secret123", '{"test": true}', sig)
        assert not verify_signature("wrong", '{"test": true}', sig)

    def test_matches_filters(self):
        from intelligence.webhooks import _matches_filters
        # No filters → matches all
        assert _matches_filters({}, {"country_code": "US"})
        # Country filter
        assert _matches_filters({"country_code": "US"}, {"country_code": "US"})
        assert not _matches_filters({"country_code": "GB"}, {"country_code": "US"})
        # Severity filter
        assert _matches_filters({"severity_min": 50}, {"severity": 80})
        assert not _matches_filters({"severity_min": 90}, {"severity": 80})

    def test_fire_webhook_connection_error(self, conn):
        from intelligence.webhooks import create_webhook, fire_webhook
        wh = create_webhook(conn, "Fail Hook", "http://localhost:1/invalid", ["test"])
        result = fire_webhook(conn, wh, "test", {"msg": "test"})
        assert result["success"] is False
        assert result["status_code"] is None

    def test_dispatch_event_filters(self, conn):
        from intelligence.webhooks import create_webhook, dispatch_event
        create_webhook(
            conn, "US Only", "http://localhost:1/us",
            ["alert"], filters={"country_code": "US"},
        )
        # Should match US events
        results = dispatch_event(conn, "alert", {"country_code": "US", "severity": 80})
        # At least one webhook was attempted (may fail on connection, that's fine)
        assert len(results) >= 1

    def test_get_webhook_logs(self, conn):
        from intelligence.webhooks import get_webhook_logs
        logs = get_webhook_logs(conn, limit=50)
        assert isinstance(logs, list)
        assert len(logs) >= 1  # from previous fire tests

    def test_delete_webhook(self, conn):
        from intelligence.webhooks import create_webhook, delete_webhook, get_webhook
        wh = create_webhook(conn, "To Delete", "http://example.com/del", ["test"])
        assert delete_webhook(conn, wh["id"]) is True
        assert get_webhook(conn, wh["id"]) is None


# ─── Widgets ─────────────────────────────────────────────────

class TestWidgets:
    def test_generate_token(self):
        from intelligence.widgets import generate_token
        t1 = generate_token()
        t2 = generate_token()
        assert len(t1) > 20
        assert t1 != t2

    def test_create_embed_token(self, conn):
        from intelligence.widgets import create_embed_token
        token = create_embed_token(conn, "risk_score", {"country_code": "US"}, 24)
        assert token["id"] is not None
        assert token["widget_type"] == "risk_score"
        assert token["scope"]["country_code"] == "US"
        assert token["active"] is True

    def test_validate_token(self, conn):
        from intelligence.widgets import create_embed_token, validate_token
        created = create_embed_token(conn, "event_feed", {}, 24)
        validated = validate_token(conn, created["token"])
        assert validated is not None
        assert validated["widget_type"] == "event_feed"

    def test_validate_expired_token(self, conn):
        from intelligence.widgets import validate_token
        # Insert an already-expired token
        expired_id = str(uuid.uuid4())
        expired_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        conn.execute(
            """INSERT INTO embed_tokens (id, token, widget_type, scope, expires_at, active)
               VALUES (?, 'expired_tok_123', 'risk_score', '{}', ?, 1)""",
            (expired_id, expired_at),
        )
        conn.commit()
        assert validate_token(conn, "expired_tok_123") is None

    def test_validate_inactive_token(self, conn):
        from intelligence.widgets import create_embed_token, revoke_token, validate_token
        created = create_embed_token(conn, "alert_ticker", {}, 24)
        revoke_token(conn, created["id"])
        assert validate_token(conn, created["token"]) is None

    def test_list_tokens(self, conn):
        from intelligence.widgets import list_tokens
        tokens = list_tokens(conn)
        assert len(tokens) >= 1

    def test_revoke_token(self, conn):
        from intelligence.widgets import create_embed_token, revoke_token
        created = create_embed_token(conn, "risk_score", {}, 1)
        assert revoke_token(conn, created["id"]) is True
        assert revoke_token(conn, "nonexistent") is False

    def test_widget_data_risk_score(self, conn):
        from intelligence.widgets import get_widget_data
        data = get_widget_data(conn, {"widget_type": "risk_score", "scope": {"country_code": "US"}})
        assert data["widget_type"] == "risk_score"
        assert "score" in data

    def test_widget_data_event_feed(self, conn):
        from intelligence.widgets import get_widget_data
        data = get_widget_data(conn, {"widget_type": "event_feed", "scope": {"country_code": "US"}})
        assert data["widget_type"] == "event_feed"
        assert "events" in data
        assert data["count"] >= 1

    def test_widget_data_alert_ticker(self, conn):
        from intelligence.widgets import get_widget_data
        data = get_widget_data(conn, {"widget_type": "alert_ticker", "scope": {"country_code": "US"}})
        assert data["widget_type"] == "alert_ticker"
        assert "alerts" in data

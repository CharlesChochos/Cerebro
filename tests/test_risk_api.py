"""
Tests for risk scores, alerts, velocity, and prediction scorecard API endpoints.
"""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from api.main import app, get_db


@pytest.fixture(scope="module")
def client():
    """Create test client and seed risk/alert data."""
    with TestClient(app) as c:
        conn = get_db()

        # Seed events for risk scoring context
        for i in range(5):
            conn.execute(
                """INSERT INTO events (id, source, title, category, severity, confidence,
                    country_code, region, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', ?))""",
                (str(uuid.uuid4()), ["gdelt", "rss", "who"][i % 3],
                 f"Risk Test Event {i}", ["military", "economic", "health"][i % 3],
                 60 + i * 8, 0.7 + i * 0.05, "US", "North America",
                 f"-{i} hours"),
            )

        # Seed risk scores
        risk_ids = []
        for i, (stype, sval) in enumerate([
            ("region", "Middle East"), ("region", "North America"),
            ("country", "US"), ("topic", "military"),
        ]):
            rid = str(uuid.uuid4())
            risk_ids.append(rid)
            conn.execute(
                """INSERT OR REPLACE INTO risk_scores
                   (id, scope_type, scope_value, score, components,
                    event_count, source_count, trend)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (rid, stype, sval, 75 - i * 10,
                 json.dumps({"severity_avg": 70, "corroboration": 50}),
                 10 + i, 3, ["spike", "rising", "stable", "falling"][i]),
            )

        # Seed alert history
        alert_ids = []
        for i in range(4):
            aid = str(uuid.uuid4())
            alert_ids.append(aid)
            conn.execute(
                """INSERT INTO alert_history
                   (id, config_id, alert_type, title, description, severity,
                    scope_type, scope_value, event_ids, acknowledged)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (aid, "default-critical",
                 ["threshold", "velocity_spike", "threshold", "anomaly"][i],
                 f"Test Alert {i}", f"Description {i}", 80 - i * 10,
                 "region", "Middle East", json.dumps([]),
                 1 if i == 3 else 0),
            )

        # Seed velocity data
        for i, (stype, sval) in enumerate([("region", "Middle East"), ("topic", "military")]):
            for period in ["1h", "6h", "24h"]:
                conn.execute(
                    """INSERT OR REPLACE INTO event_velocity
                       (id, scope_type, scope_value, period, event_count,
                        avg_severity, baseline_rate, velocity_ratio)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (str(uuid.uuid4()), stype, sval, period,
                     10 + i * 5, 65.0, 3.0, [4.0, 1.5, 2.0][["1h", "6h", "24h"].index(period)]),
                )

        # Seed predictions
        for i in range(5):
            conn.execute(
                """INSERT INTO predictions
                   (id, brief_id, prediction, confidence, timeframe, category, outcome)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), None,
                 f"Prediction {i}", [0.9, 0.7, 0.5, 0.8, 0.6][i],
                 "24h", "military",
                 ["correct", "correct", "incorrect", None, None][i]),
            )

        conn.commit()
        c.risk_ids = risk_ids
        c.alert_ids = alert_ids
        yield c


# ── Risk Score Tests ────────────────────────────────────────────────────────


def test_list_risk_scores(client):
    r = client.get("/api/risk")
    assert r.status_code == 200
    data = r.json()
    assert len(data["scores"]) >= 4


def test_risk_filter_by_type(client):
    r = client.get("/api/risk?scope_type=region")
    assert r.status_code == 200
    data = r.json()
    assert all(s["scope_type"] == "region" for s in data["scores"])


def test_risk_min_score(client):
    r = client.get("/api/risk?min_score=60")
    assert r.status_code == 200
    data = r.json()
    assert all(s["score"] >= 60 for s in data["scores"])


def test_risk_components_parsed(client):
    r = client.get("/api/risk")
    data = r.json()
    for s in data["scores"]:
        assert isinstance(s["components"], dict)


def test_get_specific_risk(client):
    r = client.get("/api/risk/region/Middle East")
    assert r.status_code == 200
    data = r.json()
    assert data["scope_value"] == "Middle East"


def test_risk_not_found(client):
    r = client.get("/api/risk/region/Nonexistent")
    assert r.status_code == 404


# ── Alert Tests ─────────────────────────────────────────────────────────────


def test_list_alerts(client):
    r = client.get("/api/alerts")
    assert r.status_code == 200
    data = r.json()
    assert len(data["alerts"]) >= 4
    assert "unacknowledged_count" in data


def test_alerts_filter_type(client):
    r = client.get("/api/alerts?alert_type=threshold")
    assert r.status_code == 200
    data = r.json()
    assert all(a["alert_type"] == "threshold" for a in data["alerts"])


def test_alerts_filter_unacknowledged(client):
    r = client.get("/api/alerts?acknowledged=false")
    assert r.status_code == 200
    data = r.json()
    assert all(a["acknowledged"] == 0 for a in data["alerts"])


def test_acknowledge_alert(client):
    r = client.post(f"/api/alerts/{client.alert_ids[0]}/acknowledge")
    assert r.status_code == 200
    assert r.json()["acknowledged"] == client.alert_ids[0]


def test_acknowledge_not_found(client):
    r = client.post("/api/alerts/nonexistent/acknowledge")
    assert r.status_code == 404


def test_configure_alert(client):
    r = client.post("/api/alerts/configure", json={
        "name": "Test Config",
        "scope_type": "region",
        "scope_value": "Europe",
        "min_severity": 80,
        "min_risk_score": 70,
        "cooldown_minutes": 30,
    })
    assert r.status_code == 200
    assert "config_id" in r.json()


def test_list_alert_configs(client):
    r = client.get("/api/alerts/configs")
    assert r.status_code == 200
    data = r.json()
    assert len(data["configs"]) >= 3  # 3 defaults + our new one


# ── Velocity Tests ──────────────────────────────────────────────────────────


def test_list_velocities(client):
    r = client.get("/api/velocity")
    assert r.status_code == 200
    data = r.json()
    assert len(data["velocities"]) >= 1


def test_velocity_spikes_only(client):
    r = client.get("/api/velocity?spikes_only=true")
    assert r.status_code == 200
    data = r.json()
    assert all(v["velocity_ratio"] >= 3.0 for v in data["velocities"])


def test_velocity_filter_period(client):
    r = client.get("/api/velocity?period=1h")
    assert r.status_code == 200
    data = r.json()
    assert all(v["period"] == "1h" for v in data["velocities"])


# ── Prediction Scorecard Tests ──────────────────────────────────────────────


def test_prediction_scorecard(client):
    r = client.get("/api/predictions/scorecard")
    assert r.status_code == 200
    data = r.json()
    assert "total_predictions" in data
    assert data["total_predictions"] >= 5
    assert "calibration" in data
    assert "accuracy" in data


def test_surprise_index(client):
    r = client.get("/api/predictions/surprise")
    assert r.status_code == 200
    data = r.json()
    assert "surprise_score" in data
    assert "date" in data

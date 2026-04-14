"""
Tests for intelligence layer API endpoints:
briefs, world state, fusion signals, predictions, red team.
"""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from api.main import app, get_db


@pytest.fixture(scope="module")
def client():
    """Create test client and seed intelligence data."""
    with TestClient(app) as c:
        conn = get_db()

        # Seed some events first (needed for FK references)
        event_ids = [str(uuid.uuid4()) for _ in range(3)]
        for i, eid in enumerate(event_ids):
            conn.execute(
                """INSERT INTO events (id, source, title, category, severity, confidence, country_code, region, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (eid, "gdelt", f"Test Event {i}", "military", 70 + i * 10, 0.8, "US", "North America"),
            )

        entity_ids = [str(uuid.uuid4()) for _ in range(2)]
        for i, entid in enumerate(entity_ids):
            conn.execute(
                "INSERT INTO entities (id, name, entity_type, event_count) VALUES (?, ?, ?, ?)",
                (entid, f"Entity {i}", "organization", 5),
            )

        # Seed briefs
        brief_ids = []
        for i, btype in enumerate(["daily", "flash", "weekly"]):
            bid = str(uuid.uuid4())
            brief_ids.append(bid)
            conn.execute(
                """INSERT INTO briefs
                   (id, brief_type, title, content, summary, event_ids, entity_ids,
                    grounding_score, model_used, token_count, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', ?))""",
                (
                    bid, btype, f"Test {btype.title()} Brief",
                    f"# {btype.title()} Brief\n\nContent here.",
                    f"Summary of {btype} brief",
                    json.dumps(event_ids[:2]),
                    json.dumps(entity_ids[:1]),
                    0.85, "claude-sonnet-4-20250514", 1500,
                    f"-{i} hours",
                ),
            )

        # Seed predictions
        pred_ids = []
        for i in range(3):
            pid = str(uuid.uuid4())
            pred_ids.append(pid)
            outcome = None if i < 2 else "correct"
            conn.execute(
                """INSERT INTO predictions
                   (id, brief_id, prediction, confidence, timeframe, category, outcome)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (pid, brief_ids[0], f"Prediction {i}", 0.7 - i * 0.1, "24h", "military", outcome),
            )

        # Seed world state
        ws_ids = []
        for i in range(3):
            wsid = str(uuid.uuid4())
            ws_ids.append(wsid)
            conn.execute(
                """INSERT INTO world_state
                   (id, date, content, token_count, events_summarized, model_used)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (wsid, f"2025-01-0{i+1}", f"## World State {i+1}\n\nContent.", 2000, 50 + i * 10, "claude-sonnet-4-20250514"),
            )

        # Seed fusion signals
        fusion_ids = []
        for i, stype in enumerate(["sanctions_evasion", "military_escalation"]):
            fid = str(uuid.uuid4())
            fusion_ids.append(fid)
            conn.execute(
                """INSERT INTO fusion_signals
                   (id, signal_type, title, description, severity, confidence,
                    event_ids, entity_ids, grounding_score, model_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fid, stype, f"Test {stype} signal",
                    f"Description of {stype} pattern",
                    80 + i * 5, 0.75 + i * 0.1,
                    json.dumps(event_ids[:2]),
                    json.dumps(entity_ids[:1]),
                    0.9, "claude-sonnet-4-20250514",
                ),
            )

        # Seed red team analysis
        rt_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO red_team_analyses
               (id, target_type, target_id, counterarguments, alternative_hypotheses,
                confidence_adjustment, model_used)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                rt_id, "brief", brief_ids[0],
                json.dumps([{"claim": "X", "counter": "Y", "severity": "medium"}]),
                json.dumps([{"hypothesis": "Alt H1", "plausibility": 0.4}]),
                -0.1, "claude-sonnet-4-20250514",
            ),
        )

        conn.commit()

        # Store IDs for tests
        c.brief_ids = brief_ids
        c.event_ids = event_ids
        c.ws_ids = ws_ids
        c.fusion_ids = fusion_ids
        c.pred_ids = pred_ids

        yield c


# ── Briefs Tests ────────────────────────────────────────────────────────────


def test_list_briefs(client):
    r = client.get("/api/briefs")
    assert r.status_code == 200
    data = r.json()
    assert "briefs" in data
    assert data["total"] >= 3
    assert len(data["briefs"]) >= 3


def test_list_briefs_filter_type(client):
    r = client.get("/api/briefs?brief_type=daily")
    assert r.status_code == 200
    data = r.json()
    assert all(b["brief_type"] == "daily" for b in data["briefs"])


def test_list_briefs_pagination(client):
    r = client.get("/api/briefs?limit=1&offset=0")
    assert r.status_code == 200
    data = r.json()
    assert len(data["briefs"]) == 1
    assert data["total"] >= 3


def test_get_brief_detail(client):
    r = client.get(f"/api/briefs/{client.brief_ids[0]}")
    assert r.status_code == 200
    data = r.json()
    assert data["brief_type"] == "daily"
    assert "content" in data
    assert "predictions" in data
    assert len(data["predictions"]) == 3
    assert "red_team" in data
    assert len(data["red_team"]) >= 1


def test_get_brief_not_found(client):
    r = client.get("/api/briefs/nonexistent-id")
    assert r.status_code == 404


def test_brief_json_fields_parsed(client):
    r = client.get(f"/api/briefs/{client.brief_ids[0]}")
    data = r.json()
    assert isinstance(data["event_ids"], list)
    assert isinstance(data["entity_ids"], list)


# ── World State Tests ───────────────────────────────────────────────────────


def test_get_world_state(client):
    r = client.get("/api/worldstate")
    assert r.status_code == 200
    data = r.json()
    assert data["world_state"] is not None
    assert "content" in data["world_state"]


def test_world_state_history(client):
    r = client.get("/api/worldstate/history")
    assert r.status_code == 200
    data = r.json()
    assert len(data["history"]) >= 3


def test_world_state_history_limit(client):
    r = client.get("/api/worldstate/history?limit=1")
    assert r.status_code == 200
    assert len(r.json()["history"]) == 1


def test_get_world_state_by_id(client):
    r = client.get(f"/api/worldstate/{client.ws_ids[0]}")
    assert r.status_code == 200
    data = r.json()
    assert "content" in data


def test_world_state_not_found(client):
    r = client.get("/api/worldstate/nonexistent")
    assert r.status_code == 404


# ── Fusion Signals Tests ────────────────────────────────────────────────────


def test_list_fusion_signals(client):
    r = client.get("/api/fusion")
    assert r.status_code == 200
    data = r.json()
    assert len(data["signals"]) >= 2


def test_fusion_filter_by_type(client):
    r = client.get("/api/fusion?signal_type=sanctions_evasion")
    assert r.status_code == 200
    data = r.json()
    assert all(s["signal_type"] == "sanctions_evasion" for s in data["signals"])


def test_fusion_min_severity(client):
    r = client.get("/api/fusion?min_severity=85")
    assert r.status_code == 200
    data = r.json()
    assert all(s["severity"] >= 85 for s in data["signals"])


def test_fusion_json_fields_parsed(client):
    r = client.get("/api/fusion")
    data = r.json()
    for sig in data["signals"]:
        assert isinstance(sig["event_ids"], list)


# ── Predictions Tests ───────────────────────────────────────────────────────


def test_list_predictions(client):
    r = client.get("/api/predictions")
    assert r.status_code == 200
    data = r.json()
    assert len(data["predictions"]) >= 3


def test_predictions_filter_pending(client):
    r = client.get("/api/predictions?outcome=pending")
    assert r.status_code == 200
    data = r.json()
    assert all(p["outcome"] is None for p in data["predictions"])


def test_predictions_filter_correct(client):
    r = client.get("/api/predictions?outcome=correct")
    assert r.status_code == 200
    data = r.json()
    assert all(p["outcome"] == "correct" for p in data["predictions"])


# ── Red Team Tests ──────────────────────────────────────────────────────────


def test_red_team_for_brief(client):
    r = client.get(f"/api/redteam/brief/{client.brief_ids[0]}")
    assert r.status_code == 200
    data = r.json()
    assert len(data["analyses"]) >= 1
    analysis = data["analyses"][0]
    assert isinstance(analysis["counterarguments"], list)
    assert isinstance(analysis["alternative_hypotheses"], list)


def test_red_team_no_results(client):
    r = client.get(f"/api/redteam/event/{client.event_ids[0]}")
    assert r.status_code == 200
    data = r.json()
    assert data["analyses"] == []


def test_red_team_invalid_type(client):
    r = client.get("/api/redteam/invalid_type/some-id")
    assert r.status_code == 400

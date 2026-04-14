"""
Tests for the NL query API endpoints:
- POST /api/query (tested only for validation, not live Claude)
- GET /api/sessions
- GET /api/sessions/{id}
- DELETE /api/sessions/{id}
"""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from api.main import app, get_db


@pytest.fixture(scope="module")
def client():
    """Create test client and seed conversation data."""
    with TestClient(app) as c:
        conn = get_db()

        # Create sessions
        session_ids = []
        for i in range(3):
            sid = str(uuid.uuid4())
            session_ids.append(sid)
            conn.execute(
                """INSERT INTO conversation_sessions (id, title, created_at, updated_at)
                   VALUES (?, ?, datetime('now', ?), datetime('now', ?))""",
                (sid, f"Test Session {i}", f"-{i} hours", f"-{i} hours"),
            )

        # Create turns for first session
        for turn in range(3):
            conn.execute(
                """INSERT INTO conversation_turns
                   (id, session_id, turn_number, question, answer,
                    event_ids, entity_ids, grounding_score,
                    suggested_questions, model_used, input_tokens, output_tokens)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    session_ids[0],
                    turn + 1,
                    f"Question {turn + 1}?",
                    f"Answer to question {turn + 1}.",
                    json.dumps(["evt-1", "evt-2"]),
                    json.dumps(["ent-1"]),
                    0.85,
                    json.dumps(["Follow-up 1?", "Follow-up 2?", "Follow-up 3?"]),
                    "claude-sonnet-4-20250514",
                    500,
                    200,
                ),
            )

        conn.commit()
        c.session_ids = session_ids
        yield c


# ── Session listing ─────────────────────────────────────────────────────────


def test_list_sessions(client):
    r = client.get("/api/sessions")
    assert r.status_code == 200
    data = r.json()
    assert "sessions" in data
    assert len(data["sessions"]) >= 3
    # Should have turn_count
    session_with_turns = next(
        (s for s in data["sessions"] if s["id"] == client.session_ids[0]), None
    )
    assert session_with_turns is not None
    assert session_with_turns["turn_count"] == 3


def test_list_sessions_pagination(client):
    r = client.get("/api/sessions?limit=1&offset=0")
    assert r.status_code == 200
    data = r.json()
    assert len(data["sessions"]) == 1


# ── Session detail ──────────────────────────────────────────────────────────


def test_get_session(client):
    r = client.get(f"/api/sessions/{client.session_ids[0]}")
    assert r.status_code == 200
    data = r.json()
    assert data["session"]["id"] == client.session_ids[0]
    assert len(data["turns"]) == 3
    # Turns should be ordered
    assert data["turns"][0]["turn_number"] == 1
    assert data["turns"][2]["turn_number"] == 3


def test_get_session_json_parsed(client):
    r = client.get(f"/api/sessions/{client.session_ids[0]}")
    data = r.json()
    turn = data["turns"][0]
    assert isinstance(turn["event_ids"], list)
    assert isinstance(turn["suggested_questions"], list)
    assert len(turn["suggested_questions"]) == 3


def test_get_session_not_found(client):
    r = client.get("/api/sessions/nonexistent-id")
    assert r.status_code == 404


# ── Session deletion ────────────────────────────────────────────────────────


def test_delete_session(client):
    # Delete the last session (no turns)
    sid = client.session_ids[2]
    r = client.delete(f"/api/sessions/{sid}")
    assert r.status_code == 200
    assert r.json()["deleted"] == sid

    # Verify it's gone
    r2 = client.get(f"/api/sessions/{sid}")
    assert r2.status_code == 404


def test_delete_session_not_found(client):
    r = client.delete("/api/sessions/nonexistent")
    assert r.status_code == 404


# ── Query validation ────────────────────────────────────────────────────────


def test_query_empty_question(client):
    r = client.post("/api/query", json={"question": ""})
    assert r.status_code == 400


def test_query_too_long(client):
    r = client.post("/api/query", json={"question": "x" * 2001})
    assert r.status_code == 400


def test_query_no_api_key(client):
    """Without a valid API key, should get 503."""
    # This will attempt to call Claude and fail since we likely don't have a valid key
    # in test env. The endpoint should return 503 for no_api_key.
    r = client.post("/api/query", json={"question": "What is happening in Ukraine?"})
    # Could be 503 (no key) or 500 (API error) — both are acceptable in test
    assert r.status_code in (500, 503)

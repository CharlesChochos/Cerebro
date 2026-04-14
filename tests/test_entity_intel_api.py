"""
API tests for entity intelligence endpoints — dossiers, ACH, workspaces, sanctions.
"""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from api.main import app, get_db


@pytest.fixture(scope="module")
def client():
    """Create test client and seed entity intelligence data."""
    with TestClient(app) as c:
        conn = get_db()

        # Seed entities
        entity_ids = []
        for i, (name, etype) in enumerate([
            ("NATO", "organization"), ("Russia", "location"),
            ("Dark Fleet Shipping", "organization"), ("Test Person", "person"),
            ("Shell Corp Alpha", "organization"),
        ]):
            eid = f"ent-{i}"
            entity_ids.append(eid)
            conn.execute(
                """INSERT OR IGNORE INTO entities (id, name, entity_type, event_count, aliases)
                   VALUES (?, ?, ?, ?, ?)""",
                (eid, name, etype, 10 - i,
                 json.dumps([f"{name} Alt"]) if i < 3 else None),
            )

        # Seed entity relations
        for src, tgt, rel in [
            ("ent-0", "ent-1", "co_occurs"),
            ("ent-1", "ent-2", "associated_with"),
            ("ent-2", "ent-4", "co_occurs"),
            ("ent-0", "ent-3", "co_occurs"),
        ]:
            conn.execute(
                """INSERT OR IGNORE INTO entity_relations
                   (id, source_entity_id, target_entity_id, relation_type, confidence)
                   VALUES (?, ?, ?, ?, 0.7)""",
                (str(uuid.uuid4()), src, tgt, rel),
            )

        # Seed events referencing entities
        for i in range(5):
            conn.execute(
                """INSERT OR IGNORE INTO events (id, source, title, category, severity, confidence,
                    country_code, region, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', ?))""",
                (f"ev-ei-{i}", ["gdelt", "rss"][i % 2],
                 f"NATO military exercise {i}" if i < 3 else f"Russia diplomatic event {i}",
                 "military", 60 + i * 5, 0.8, "US", "Europe",
                 f"-{i} hours"),
            )

        # Seed a tracked entity
        conn.execute(
            """INSERT OR IGNORE INTO tracked_entities
               (id, entity_id, priority, notes, tags)
               VALUES (?, ?, ?, ?, ?)""",
            ("trk-1", "ent-0", "critical", "High priority NATO tracking",
             json.dumps(["military", "alliance"])),
        )

        # Seed an ACH framework
        ach_id = str(uuid.uuid4())
        matrix = [["C", "I", "N"], ["I", "C", "N"], ["N", "N", "C"]]
        conn.execute(
            """INSERT INTO ach_frameworks
               (id, workspace_id, title, description, hypotheses, evidence, matrix, conclusion)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (ach_id, None, "Test ACH", "Who is escalating?",
             json.dumps(["H1: Country A", "H2: Country B", "H3: Neither"]),
             json.dumps(["E1: Troop movements", "E2: Diplomatic cables", "E3: Economic sanctions"]),
             json.dumps(matrix), "H2 has fewest inconsistencies."),
        )

        # Seed a workspace
        ws_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO analysis_workspaces
               (id, title, description, workspace_type, content, pinned_events, pinned_entities)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ws_id, "Test Workspace", "Analysis notebook", "notebook",
             json.dumps({"notes": [{"id": "n1", "text": "Initial note"}]}),
             json.dumps(["ev-ei-0"]), json.dumps(["ent-0"])),
        )

        conn.commit()

        c.entity_ids = entity_ids
        c.ach_id = ach_id
        c.ws_id = ws_id
        yield c


# ── Omnisearch Tests ───────────────────────────────────────────────────────


def test_omnisearch(client):
    r = client.get("/api/entity-search?q=NATO")
    assert r.status_code == 200
    data = r.json()
    assert data["total_hits"] >= 1
    assert data["query"] == "NATO"


def test_omnisearch_events(client):
    r = client.get("/api/entity-search?q=military")
    assert r.status_code == 200
    data = r.json()
    assert len(data.get("events", [])) >= 1


def test_omnisearch_too_short(client):
    r = client.get("/api/entity-search?q=x")
    assert r.status_code == 422  # validation error


# ── Dossier Tests ──────────────────────────────────────────────────────────


def test_get_dossier(client):
    r = client.get(f"/api/entities/{client.entity_ids[0]}/dossier")
    assert r.status_code == 200
    data = r.json()
    assert data["entity_name"] == "NATO"
    assert "event_count" in data


def test_dossier_not_found(client):
    r = client.get("/api/entities/nonexistent/dossier")
    assert r.status_code == 404


def test_refresh_dossier(client):
    r = client.post(f"/api/entities/{client.entity_ids[0]}/dossier/refresh")
    assert r.status_code == 200


def test_refresh_dossier_not_found(client):
    r = client.post("/api/entities/nonexistent/dossier/refresh")
    assert r.status_code == 404


# ── Link Analysis Tests ────────────────────────────────────────────────────


def test_entity_graph(client):
    r = client.get(f"/api/entities/{client.entity_ids[0]}/graph")
    assert r.status_code == 200
    data = r.json()
    assert data["center_entity"] == client.entity_ids[0]
    assert data["node_count"] >= 1
    assert "nodes" in data
    assert "edges" in data


def test_entity_graph_not_found(client):
    r = client.get("/api/entities/nonexistent/graph")
    assert r.status_code == 404


def test_entity_path(client):
    r = client.get(f"/api/entities/path/{client.entity_ids[0]}/{client.entity_ids[1]}")
    assert r.status_code == 200
    data = r.json()
    assert data["hops"] >= 1
    assert len(data["path"]) >= 2


def test_entity_path_not_found(client):
    r = client.get("/api/entities/path/nonexistent/also-nonexistent")
    assert r.status_code == 404


# ── Tracked Entities Tests ─────────────────────────────────────────────────


def test_list_tracked(client):
    r = client.get("/api/tracked-entities")
    assert r.status_code == 200
    data = r.json()
    assert len(data["tracked_entities"]) >= 1


def test_list_tracked_by_priority(client):
    r = client.get("/api/tracked-entities?priority=critical")
    assert r.status_code == 200
    data = r.json()
    assert all(t["priority"] == "critical" for t in data["tracked_entities"])


def test_track_entity(client):
    r = client.post("/api/tracked-entities", json={
        "entity_id": client.entity_ids[1],
        "priority": "high",
        "notes": "Monitor closely",
        "tags": ["geopolitical"],
    })
    assert r.status_code == 200
    assert "tracked_id" in r.json()


def test_track_entity_not_found(client):
    r = client.post("/api/tracked-entities", json={
        "entity_id": "nonexistent",
        "priority": "normal",
    })
    assert r.status_code == 404


def test_untrack_entity(client):
    # First track it
    client.post("/api/tracked-entities", json={
        "entity_id": client.entity_ids[3],
        "priority": "low",
    })
    r = client.delete(f"/api/tracked-entities/{client.entity_ids[3]}")
    assert r.status_code == 200


def test_untrack_not_found(client):
    r = client.delete("/api/tracked-entities/nonexistent")
    assert r.status_code == 404


# ── ACH Tests ──────────────────────────────────────────────────────────────


def test_list_ach(client):
    r = client.get("/api/ach")
    assert r.status_code == 200
    data = r.json()
    assert len(data["frameworks"]) >= 1


def test_get_ach(client):
    r = client.get(f"/api/ach/{client.ach_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Test ACH"
    assert isinstance(data["hypotheses"], list)
    assert isinstance(data["evidence"], list)
    assert isinstance(data["matrix"], list)
    assert "scores" in data


def test_ach_not_found(client):
    r = client.get("/api/ach/nonexistent")
    assert r.status_code == 404


def test_create_ach(client):
    r = client.post("/api/ach", json={
        "title": "New ACH",
        "question": "Who is responsible?",
        "hypotheses": ["State A", "State B", "Non-state actor"],
        "evidence": ["Satellite imagery shows movement", "Diplomatic cables indicate tension"],
    })
    assert r.status_code == 200
    data = r.json()
    assert "framework_id" in data
    assert len(data["matrix"]) == 2  # 2 evidence items
    assert len(data["matrix"][0]) == 3  # 3 hypotheses


def test_create_ach_too_few_hypotheses(client):
    r = client.post("/api/ach", json={
        "title": "Bad ACH",
        "question": "Test",
        "hypotheses": ["Only one"],
        "evidence": ["Some evidence"],
    })
    assert r.status_code == 400


def test_update_ach_cell(client):
    r = client.patch(f"/api/ach/{client.ach_id}/cell", json={
        "evidence_idx": 0,
        "hypothesis_idx": 1,
        "value": "C",
    })
    assert r.status_code == 200
    assert r.json()["updated"] is True


def test_update_ach_cell_invalid_value(client):
    r = client.patch(f"/api/ach/{client.ach_id}/cell", json={
        "evidence_idx": 0,
        "hypothesis_idx": 0,
        "value": "X",
    })
    assert r.status_code == 400


# ── Workspace Tests ────────────────────────────────────────────────────────


def test_list_workspaces(client):
    r = client.get("/api/workspaces")
    assert r.status_code == 200
    data = r.json()
    assert len(data["workspaces"]) >= 1


def test_get_workspace(client):
    r = client.get(f"/api/workspaces/{client.ws_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Test Workspace"
    assert isinstance(data["content"], dict)
    assert isinstance(data["pinned_events"], list)


def test_workspace_not_found(client):
    r = client.get("/api/workspaces/nonexistent")
    assert r.status_code == 404


def test_create_workspace(client):
    r = client.post("/api/workspaces", json={
        "title": "New Analysis",
        "description": "Investigation into X",
        "workspace_type": "notebook",
        "pinned_events": ["ev-ei-0"],
    })
    assert r.status_code == 200
    assert "workspace_id" in r.json()


def test_add_workspace_note(client):
    r = client.post(f"/api/workspaces/{client.ws_id}/notes", json={
        "text": "This is a new observation.",
    })
    assert r.status_code == 200
    assert r.json()["note_count"] >= 2  # 1 seeded + 1 new


# ── Sanctions Tests ────────────────────────────────────────────────────────


def test_list_watchlist(client):
    r = client.get("/api/sanctions/watchlist")
    assert r.status_code == 200
    data = r.json()
    assert len(data["watchlist"]) >= 3  # 3 seeded entries


def test_watchlist_filter_type(client):
    r = client.get("/api/sanctions/watchlist?entity_type=person")
    assert r.status_code == 200
    data = r.json()
    assert all(e["entity_type"] == "person" for e in data["watchlist"])


def test_run_sanctions_scan(client):
    r = client.post("/api/sanctions/scan")
    assert r.status_code == 200
    data = r.json()
    assert "direct_matches" in data
    assert "multi_hop_matches" in data


def test_list_sanctions_hits(client):
    r = client.get("/api/sanctions/hits")
    assert r.status_code == 200
    data = r.json()
    assert "hits" in data
    assert "total" in data

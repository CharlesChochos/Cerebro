"""
API Tests — Key assumptions, I&W framework, association matrix,
threat assessment matrix, IC source ratings.
"""
import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["CEREBRO_DB_PATH"] = _test_db_path

from api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
    os.unlink(_test_db_path)


# ─── Key Assumptions Check API ──────────────────────────────

class TestAssumptionsAPI:
    def test_create_assumption(self, client):
        resp = client.post("/api/assumptions", json={
            "assumption_text": "Regime will not escalate",
            "assessment_id": "api-assess-1",
            "confidence": "high",
            "evidence_for": ["Historical pattern"],
            "impact_if_wrong": "critical",
        })
        assert resp.status_code == 200
        assert "assumption_id" in resp.json()

    def test_create_more(self, client):
        client.post("/api/assumptions", json={
            "assumption_text": "Sanctions will hold",
            "assessment_id": "api-assess-1",
            "confidence": "moderate",
            "impact_if_wrong": "high",
        })
        client.post("/api/assumptions", json={
            "assumption_text": "Allies are united",
            "assessment_id": "api-assess-1",
            "confidence": "low",
            "impact_if_wrong": "moderate",
        })

    def test_list_assumptions(self, client):
        resp = client.get("/api/assumptions?assessment_id=api-assess-1")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 3

    def test_get_assumption(self, client):
        items = client.get("/api/assumptions").json()["assumptions"]
        resp = client.get(f"/api/assumptions/{items[0]['id']}")
        assert resp.status_code == 200
        assert "assumption_text" in resp.json()

    def test_get_assumption_not_found(self, client):
        resp = client.get("/api/assumptions/nonexistent")
        assert resp.status_code == 404

    def test_update_status(self, client):
        items = client.get("/api/assumptions").json()["assumptions"]
        resp = client.put(f"/api/assumptions/{items[0]['id']}", json={
            "status": "challenged",
            "evidence_against": ["New intelligence report"],
            "confidence": "low",
        })
        assert resp.status_code == 200
        assert resp.json()["updated"] is True

    def test_evaluate(self, client):
        resp = client.get("/api/assumptions/evaluate/api-assess-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_assumptions"] >= 3
        assert "overall_confidence" in data


# ─── I&W Framework API ──────────────────────────────────────

class TestIWFrameworkAPI:
    def test_create_framework(self, client):
        resp = client.post("/api/iw/frameworks", json={
            "name": "API Test I&W Framework",
            "threat_type": "military",
            "region": "Middle East",
            "threshold_pct": 50.0,
        })
        assert resp.status_code == 200
        assert "framework_id" in resp.json()

    def test_add_indicators(self, client):
        fws = client.get("/api/iw/frameworks").json()["frameworks"]
        fid = fws[0]["id"]
        for text in ["Troop mobilization", "Diplomatic withdrawal", "Comms spike"]:
            resp = client.post(f"/api/iw/frameworks/{fid}/indicators", json={
                "indicator_text": text,
                "category": "military",
                "weight": 1.0,
            })
            assert resp.status_code == 200

    def test_add_indicator_framework_not_found(self, client):
        resp = client.post("/api/iw/frameworks/nonexistent/indicators", json={
            "indicator_text": "test",
        })
        assert resp.status_code == 404

    def test_list_frameworks(self, client):
        resp = client.get("/api/iw/frameworks")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_framework(self, client):
        fws = client.get("/api/iw/frameworks").json()["frameworks"]
        resp = client.get(f"/api/iw/frameworks/{fws[0]['id']}")
        assert resp.status_code == 200
        assert len(resp.json()["indicators"]) >= 3

    def test_get_framework_not_found(self, client):
        resp = client.get("/api/iw/frameworks/nonexistent")
        assert resp.status_code == 404

    def test_update_indicator(self, client):
        fws = client.get("/api/iw/frameworks").json()["frameworks"]
        fw = client.get(f"/api/iw/frameworks/{fws[0]['id']}").json()
        ind_id = fw["indicators"][0]["id"]
        resp = client.put(f"/api/iw/indicators/{ind_id}", json={
            "status": "confirmed",
            "evidence": {"source": "satellite"},
        })
        assert resp.status_code == 200

    def test_evaluate_framework(self, client):
        fws = client.get("/api/iw/frameworks").json()["frameworks"]
        resp = client.get(f"/api/iw/frameworks/{fws[0]['id']}/evaluate")
        assert resp.status_code == 200
        data = resp.json()
        assert "warning_level" in data
        assert data["total_indicators"] >= 3


# ─── Association Matrix API ─────────────────────────────────

class TestAssociationsAPI:
    def test_create_association(self, client):
        resp = client.post("/api/associations", json={
            "entity_a_type": "entity",
            "entity_a_id": "api-ent-1",
            "entity_b_type": "entity",
            "entity_b_id": "api-ent-2",
            "relationship_type": "linked",
            "strength": 0.8,
            "entity_a_label": "Org Alpha",
            "entity_b_label": "Person Beta",
            "evidence": ["Joint operation"],
        })
        assert resp.status_code == 200
        assert "association_id" in resp.json()

    def test_create_more(self, client):
        client.post("/api/associations", json={
            "entity_a_type": "entity", "entity_a_id": "api-ent-2",
            "entity_b_type": "event", "entity_b_id": "api-evt-1",
            "relationship_type": "co-temporal", "strength": 0.6,
        })

    def test_list_associations(self, client):
        resp = client.get("/api/associations")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 2

    def test_find_by_entity(self, client):
        resp = client.get("/api/associations?entity_type=entity&entity_id=api-ent-2")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_association(self, client):
        items = client.get("/api/associations").json()["associations"]
        resp = client.get(f"/api/associations/{items[0]['id']}")
        assert resp.status_code == 200

    def test_get_association_not_found(self, client):
        resp = client.get("/api/associations/nonexistent")
        assert resp.status_code == 404

    def test_network_graph(self, client):
        resp = client.get("/api/associations/network/entity/api-ent-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_nodes"] >= 1

    def test_stats(self, client):
        resp = client.get("/api/associations/stats")
        assert resp.status_code == 200
        assert resp.json()["total_associations"] >= 2


# ─── Threat Assessment API ──────────────────────────────────

class TestThreatsAPI:
    def test_create_threat(self, client):
        resp = client.post("/api/threats", json={
            "threat_name": "API Test Threat",
            "capability_score": 80,
            "intent_score": 70,
            "opportunity_score": 60,
            "vulnerability_score": 50,
            "threat_type": "state",
            "region": "Middle East",
            "evidence": ["Intel report"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "assessment_id" in data
        assert data["overall_score"] > 40
        assert "threat_level" in data

    def test_create_low_threat(self, client):
        resp = client.post("/api/threats", json={
            "threat_name": "Minor Protest",
            "capability_score": 10,
            "intent_score": 15,
            "opportunity_score": 20,
            "threat_type": "non-state",
        })
        assert resp.status_code == 200
        assert resp.json()["overall_score"] < 25

    def test_list_threats(self, client):
        resp = client.get("/api/threats")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 2

    def test_get_threat(self, client):
        items = client.get("/api/threats").json()["assessments"]
        resp = client.get(f"/api/threats/{items[0]['id']}")
        assert resp.status_code == 200
        assert "threat_level" in resp.json()

    def test_get_threat_not_found(self, client):
        resp = client.get("/api/threats/nonexistent")
        assert resp.status_code == 404

    def test_update_threat(self, client):
        items = client.get("/api/threats").json()["assessments"]
        resp = client.put(f"/api/threats/{items[0]['id']}", json={
            "intent_score": 95,
        })
        assert resp.status_code == 200
        assert resp.json()["overall_score"] > 0

    def test_update_not_found(self, client):
        resp = client.put("/api/threats/nonexistent", json={"intent_score": 50})
        assert resp.status_code == 404

    def test_summary(self, client):
        resp = client.get("/api/threats/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_active"] >= 2
        assert "by_threat_level" in data


# ─── IC Source Ratings API ──────────────────────────────────

class TestSourceRatingsAPI:
    def test_rate_source(self, client):
        resp = client.post("/api/source-ratings", json={
            "source_name": "Agent HAWK",
            "reliability": "B",
            "information_quality": 2,
            "source_type": "humint",
            "rating_basis": ["Consistent reporting"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["rating"] == "B2"
        assert data["composite_score"] == 80.0

    def test_rate_multiple(self, client):
        client.post("/api/source-ratings", json={
            "source_name": "SIGINT Node X",
            "reliability": "A", "information_quality": 1,
            "source_type": "sigint",
        })
        client.post("/api/source-ratings", json={
            "source_name": "Social Media Feed",
            "reliability": "D", "information_quality": 4,
            "source_type": "osint",
        })

    def test_list_ratings(self, client):
        resp = client.get("/api/source-ratings")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 3

    def test_list_by_source_type(self, client):
        resp = client.get("/api/source-ratings?source_type=humint")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_rating(self, client):
        items = client.get("/api/source-ratings").json()["ratings"]
        resp = client.get(f"/api/source-ratings/{items[0]['id']}")
        assert resp.status_code == 200
        assert "rating" in resp.json()

    def test_get_rating_not_found(self, client):
        resp = client.get("/api/source-ratings/nonexistent")
        assert resp.status_code == 404

    def test_source_history(self, client):
        # Rate the same source again
        client.post("/api/source-ratings", json={
            "source_name": "Agent HAWK",
            "reliability": "A", "information_quality": 1,
            "source_type": "humint",
        })
        resp = client.get("/api/source-ratings/source/Agent HAWK")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 2

    def test_stats(self, client):
        resp = client.get("/api/source-ratings/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_ratings"] >= 3
        assert data["avg_composite_score"] > 0

"""
Module-level tests — Key assumptions, I&W framework, association matrix,
threat assessment, IC source ratings.
"""
import os
import sys
import tempfile

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
    yield c
    c.close()
    os.unlink(path)


# ─── Key Assumptions Check ──────────────────────────────────

class TestKeyAssumptions:
    def test_create_assumption(self, conn):
        from intelligence.key_assumptions import create_assumption
        aid = create_assumption(
            conn, "The regime will not use military force",
            assessment_id="assess-1",
            confidence="high",
            evidence_for=["Historical restraint", "International pressure"],
            evidence_against=["Recent troop movements"],
            impact_if_wrong="critical",
            analyst="analyst-1",
        )
        assert aid is not None

    def test_create_multiple_assumptions(self, conn):
        from intelligence.key_assumptions import create_assumption
        create_assumption(conn, "Economic sanctions will hold", assessment_id="assess-1",
                         confidence="moderate", impact_if_wrong="high")
        create_assumption(conn, "Allies will support intervention", assessment_id="assess-1",
                         confidence="low", impact_if_wrong="moderate")
        create_assumption(conn, "Intel sources are accurate", assessment_id="assess-1",
                         confidence="moderate", impact_if_wrong="critical")

    def test_get_assumption(self, conn):
        from intelligence.key_assumptions import list_assumptions, get_assumption
        items = list_assumptions(conn, assessment_id="assess-1")
        assert len(items) >= 4
        item = get_assumption(conn, items[0]["id"])
        assert item is not None
        assert isinstance(item["evidence_for"], list)

    def test_get_assumption_not_found(self, conn):
        from intelligence.key_assumptions import get_assumption
        assert get_assumption(conn, "nonexistent") is None

    def test_update_status(self, conn):
        from intelligence.key_assumptions import list_assumptions, update_assumption_status, get_assumption
        items = list_assumptions(conn, assessment_id="assess-1")
        aid = items[0]["id"]
        ok = update_assumption_status(
            conn, aid, "challenged",
            evidence_against=["New satellite imagery shows buildup"],
            confidence="low",
        )
        assert ok is True
        updated = get_assumption(conn, aid)
        assert updated["status"] == "challenged"
        assert updated["confidence"] == "low"

    def test_update_invalid_status(self, conn):
        from intelligence.key_assumptions import list_assumptions, update_assumption_status
        items = list_assumptions(conn, assessment_id="assess-1")
        ok = update_assumption_status(conn, items[0]["id"], "invalid_status")
        assert ok is False

    def test_list_by_status(self, conn):
        from intelligence.key_assumptions import list_assumptions
        challenged = list_assumptions(conn, status="challenged")
        assert len(challenged) >= 1
        assert all(a["status"] == "challenged" for a in challenged)

    def test_evaluate_assumptions(self, conn):
        from intelligence.key_assumptions import evaluate_assumptions
        result = evaluate_assumptions(conn, "assess-1")
        assert result["total_assumptions"] >= 4
        assert result["challenged"] >= 1
        assert result["overall_confidence"] in ("low", "moderate", "high")
        # Assumptions should be sorted by vulnerability
        scores = [a["vulnerability_score"] for a in result["assumptions"]]
        assert scores == sorted(scores, reverse=True)


# ─── Indications & Warning ──────────────────────────────────

class TestIWFramework:
    _framework_id: str | None = None

    def test_create_framework(self, conn):
        from intelligence.iw_framework import create_framework
        fid = create_framework(
            conn, "Iran Military Escalation",
            threat_type="military",
            description="Indicators of potential military action by Iran",
            region="Middle East",
            country_code="IR",
            threshold_pct=50.0,
        )
        assert fid is not None
        TestIWFramework._framework_id = fid

    def test_add_indicators(self, conn):
        from intelligence.iw_framework import add_indicator
        fid = TestIWFramework._framework_id
        add_indicator(conn, fid, "Troop mobilization near border", category="military", weight=2.0)
        add_indicator(conn, fid, "Diplomatic recall of ambassadors", category="diplomatic", weight=1.5)
        add_indicator(conn, fid, "Increased military communications", category="military", weight=1.0)
        add_indicator(conn, fid, "Civil defense drills announced", category="social", weight=0.5)
        add_indicator(conn, fid, "Economic sanctions evasion increase", category="economic", weight=1.0)

    def test_get_framework_with_indicators(self, conn):
        from intelligence.iw_framework import get_framework
        fw = get_framework(conn, TestIWFramework._framework_id)
        assert fw is not None
        assert len(fw["indicators"]) >= 5
        assert fw["name"] == "Iran Military Escalation"

    def test_get_framework_not_found(self, conn):
        from intelligence.iw_framework import get_framework
        assert get_framework(conn, "nonexistent") is None

    def test_update_indicator_status(self, conn):
        from intelligence.iw_framework import get_framework, update_indicator_status
        fw = get_framework(conn, TestIWFramework._framework_id)
        # Mark two indicators as observed
        update_indicator_status(conn, fw["indicators"][0]["id"], "confirmed",
                               evidence={"source": "satellite imagery"})
        update_indicator_status(conn, fw["indicators"][1]["id"], "observed",
                               evidence={"source": "diplomatic channels"})
        update_indicator_status(conn, fw["indicators"][2]["id"], "possible")

    def test_update_invalid_indicator(self, conn):
        from intelligence.iw_framework import update_indicator_status
        assert update_indicator_status(conn, "nonexistent", "observed") is False
        fw_list = list(conn.execute("SELECT id FROM iw_indicators LIMIT 1"))
        if fw_list:
            assert update_indicator_status(conn, fw_list[0]["id"], "bogus") is False

    def test_evaluate_framework(self, conn):
        from intelligence.iw_framework import evaluate_framework
        fid = TestIWFramework._framework_id
        result = evaluate_framework(conn, fid)
        assert result["total_indicators"] >= 5
        assert result["observed"] >= 1
        assert result["warning_level"] > 0
        assert isinstance(result["triggered"], bool)

    def test_evaluate_triggers_warning(self, conn):
        from intelligence.iw_framework import evaluate_framework
        fid = TestIWFramework._framework_id
        result = evaluate_framework(conn, fid)
        # With 2 confirmed/observed + 1 possible out of 5 indicators (weight ~6),
        # warning level should be significant
        assert result["warning_level"] > 20

    def test_list_by_status(self, conn):
        from intelligence.iw_framework import list_frameworks
        active = list_frameworks(conn, status="active")
        assert isinstance(active, list)

    def test_list_by_threat_type(self, conn):
        from intelligence.iw_framework import list_frameworks
        mil = list_frameworks(conn, threat_type="military")
        assert len(mil) >= 1


# ─── Association Matrix ─────────────────────────────────────

class TestAssociationMatrix:
    def test_create_association(self, conn):
        from intelligence.association_matrix import create_association
        aid = create_association(
            conn,
            entity_a_type="entity", entity_a_id="ent-001",
            entity_b_type="entity", entity_b_id="ent-002",
            relationship_type="linked", strength=0.8,
            entity_a_label="Organization Alpha",
            entity_b_label="Person Beta",
            evidence=["Joint press statement", "Shared funding"],
        )
        assert aid is not None

    def test_create_chain(self, conn):
        from intelligence.association_matrix import create_association
        create_association(conn, "entity", "ent-002", "entity", "ent-003",
                         "financial", strength=0.6, entity_a_label="Person Beta",
                         entity_b_label="Company Gamma")
        create_association(conn, "entity", "ent-003", "event", "evt-001",
                         "co-temporal", strength=0.7, entity_a_label="Company Gamma",
                         entity_b_label="Weapons Shipment")
        create_association(conn, "country", "IR", "entity", "ent-001",
                         "command", strength=0.9, entity_a_label="Iran",
                         entity_b_label="Organization Alpha", bidirectional=False)

    def test_get_association(self, conn):
        from intelligence.association_matrix import list_associations, get_association
        items = list_associations(conn)
        assert len(items) >= 4
        item = get_association(conn, items[0]["id"])
        assert item is not None
        assert isinstance(item["evidence"], list)

    def test_get_association_not_found(self, conn):
        from intelligence.association_matrix import get_association
        assert get_association(conn, "nonexistent") is None

    def test_find_by_entity(self, conn):
        from intelligence.association_matrix import find_associations
        assocs = find_associations(conn, entity_type="entity", entity_id="ent-002")
        assert len(assocs) >= 2  # linked to ent-001 and financial to ent-003

    def test_find_by_relationship(self, conn):
        from intelligence.association_matrix import find_associations
        financial = find_associations(conn, relationship_type="financial")
        assert len(financial) >= 1
        assert all(a["relationship_type"] == "financial" for a in financial)

    def test_find_by_min_strength(self, conn):
        from intelligence.association_matrix import find_associations
        strong = find_associations(conn, min_strength=0.8)
        assert all(a["strength"] >= 0.8 for a in strong)

    def test_build_network_graph(self, conn):
        from intelligence.association_matrix import build_network_graph
        graph = build_network_graph(conn, "entity", "ent-001", depth=2)
        assert graph["total_nodes"] >= 2
        assert graph["total_edges"] >= 1
        assert graph["root"]["id"] == "ent-001"

    def test_network_depth_limit(self, conn):
        from intelligence.association_matrix import build_network_graph
        shallow = build_network_graph(conn, "entity", "ent-001", depth=1)
        deep = build_network_graph(conn, "entity", "ent-001", depth=3)
        assert deep["total_nodes"] >= shallow["total_nodes"]

    def test_matrix_stats(self, conn):
        from intelligence.association_matrix import get_matrix_stats
        stats = get_matrix_stats(conn)
        assert stats["total_associations"] >= 4
        assert "linked" in stats["by_relationship_type"]


# ─── Threat Assessment Matrix ───────────────────────────────

class TestThreatAssessment:
    def test_compute_overall_score(self):
        from intelligence.threat_assessment import compute_overall_score
        # High threat = high everything
        high = compute_overall_score(90, 90, 90, 90)
        # Low threat = low everything
        low = compute_overall_score(10, 10, 10, 10)
        assert high > low
        assert high > 70
        assert low < 20

    def test_zero_intent_reduces_score(self):
        from intelligence.threat_assessment import compute_overall_score
        # High capability but no intent should still be low-ish
        # (geometric mean punishes zeros via clamping to 1)
        no_intent = compute_overall_score(90, 1, 90, 90)
        full = compute_overall_score(90, 90, 90, 90)
        assert no_intent < full * 0.5

    def test_classify_threat_level(self):
        from intelligence.threat_assessment import classify_threat_level
        assert classify_threat_level(85) == "critical"
        assert classify_threat_level(65) == "high"
        assert classify_threat_level(45) == "moderate"
        assert classify_threat_level(25) == "low"
        assert classify_threat_level(10) == "minimal"

    def test_create_assessment(self, conn):
        from intelligence.threat_assessment import create_assessment
        result = create_assessment(
            conn, "Iranian Missile Strike",
            capability_score=85, intent_score=60, opportunity_score=70,
            vulnerability_score=55,
            threat_type="state", region="Middle East", country_code="IR",
            timeframe="near-term", analyst="analyst-1",
            evidence=["HUMINT report #44", "Satellite imagery"],
        )
        assert "assessment_id" in result
        assert result["overall_score"] > 40
        assert result["threat_level"] in ("moderate", "high", "critical")

    def test_create_low_threat(self, conn):
        from intelligence.threat_assessment import create_assessment
        result = create_assessment(
            conn, "Minor Protest Activity",
            capability_score=15, intent_score=20, opportunity_score=30,
            threat_type="non-state", region="Western Europe",
        )
        assert result["overall_score"] < 30

    def test_get_assessment(self, conn):
        from intelligence.threat_assessment import list_assessments, get_assessment
        items = list_assessments(conn)
        assert len(items) >= 2
        item = get_assessment(conn, items[0]["id"])
        assert item is not None
        assert "threat_level" in item
        assert isinstance(item["evidence"], list)

    def test_get_assessment_not_found(self, conn):
        from intelligence.threat_assessment import get_assessment
        assert get_assessment(conn, "nonexistent") is None

    def test_update_assessment(self, conn):
        from intelligence.threat_assessment import list_assessments, update_assessment, get_assessment
        items = list_assessments(conn)
        tid = items[0]["id"]
        old_score = items[0]["overall_score"]
        result = update_assessment(conn, tid, intent_score=95)
        assert result is not None
        # Increasing intent should increase overall score
        assert result["overall_score"] >= old_score

    def test_update_not_found(self, conn):
        from intelligence.threat_assessment import update_assessment
        assert update_assessment(conn, "nonexistent") is None

    def test_list_by_threat_type(self, conn):
        from intelligence.threat_assessment import list_assessments
        state = list_assessments(conn, threat_type="state")
        assert len(state) >= 1

    def test_list_by_region(self, conn):
        from intelligence.threat_assessment import list_assessments
        me = list_assessments(conn, region="Middle East")
        assert len(me) >= 1

    def test_threat_summary(self, conn):
        from intelligence.threat_assessment import get_threat_summary
        summary = get_threat_summary(conn)
        assert summary["total_active"] >= 2
        assert isinstance(summary["by_threat_level"], dict)
        assert summary["highest_threat"] is not None


# ─── IC Source Ratings ──────────────────────────────────────

class TestSourceRating:
    def test_compute_composite(self):
        from intelligence.source_rating import compute_composite_score
        # A1 = best possible = (5+5)/10 * 100 = 100
        assert compute_composite_score("A", 1) == 100.0
        # F6 = worst = (0+0)/10 * 100 = 0
        assert compute_composite_score("F", 6) == 0.0
        # B2 = good = (4+4)/10 * 100 = 80
        assert compute_composite_score("B", 2) == 80.0
        # C3 = moderate = (3+3)/10 * 100 = 60
        assert compute_composite_score("C", 3) == 60.0

    def test_format_rating(self):
        from intelligence.source_rating import format_rating
        assert format_rating("B", 2) == "B2"
        assert format_rating("a", 1) == "A1"

    def test_classify_rating(self):
        from intelligence.source_rating import classify_rating
        assert classify_rating(90) == "excellent"
        assert classify_rating(65) == "good"
        assert classify_rating(45) == "adequate"
        assert classify_rating(25) == "poor"
        assert classify_rating(10) == "unreliable"

    def test_rate_source(self, conn):
        from intelligence.source_rating import rate_source
        result = rate_source(
            conn, "Agent COYOTE", "B", 2,
            source_type="humint",
            rating_basis=["5 years of reliable reporting", "Confirmed by SIGINT"],
            analyst="analyst-1",
        )
        assert result["rating"] == "B2"
        assert result["composite_score"] == 80.0
        assert result["quality_tier"] == "excellent"
        assert "rating_id" in result

    def test_rate_multiple_sources(self, conn):
        from intelligence.source_rating import rate_source
        rate_source(conn, "SIGINT Station Alpha", "A", 1, source_type="sigint")
        rate_source(conn, "Twitter OSINT Feed", "D", 4, source_type="osint")
        rate_source(conn, "Satellite Constellation Bravo", "B", 1, source_type="geoint")

    def test_get_rating(self, conn):
        from intelligence.source_rating import list_ratings, get_rating
        items = list_ratings(conn)
        assert len(items) >= 4
        item = get_rating(conn, items[0]["id"])
        assert item is not None
        assert "rating" in item
        assert "quality_tier" in item
        assert "reliability_label" in item

    def test_get_rating_not_found(self, conn):
        from intelligence.source_rating import get_rating
        assert get_rating(conn, "nonexistent") is None

    def test_list_by_source_type(self, conn):
        from intelligence.source_rating import list_ratings
        humint = list_ratings(conn, source_type="humint")
        assert len(humint) >= 1

    def test_list_by_min_composite(self, conn):
        from intelligence.source_rating import list_ratings
        good = list_ratings(conn, min_composite=70.0)
        assert all(r["composite_score"] >= 70.0 for r in good)

    def test_list_by_reliability(self, conn):
        from intelligence.source_rating import list_ratings
        a_rated = list_ratings(conn, reliability="A")
        assert len(a_rated) >= 1

    def test_get_source_history(self, conn):
        from intelligence.source_rating import rate_source, get_ratings_for_source
        # Rate the same source again (updated assessment)
        rate_source(conn, "Agent COYOTE", "A", 1, source_type="humint",
                   rating_basis=["Confirmed key intelligence leading to arrest"])
        history = get_ratings_for_source(conn, "Agent COYOTE")
        assert len(history) >= 2

    def test_rating_stats(self, conn):
        from intelligence.source_rating import get_rating_stats
        stats = get_rating_stats(conn)
        assert stats["total_ratings"] >= 4
        assert stats["avg_composite_score"] > 0
        assert "humint" in stats["by_source_type"]
        assert "rating_scale" in stats

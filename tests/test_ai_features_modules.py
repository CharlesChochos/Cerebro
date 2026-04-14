"""
Tests — Multi-perspective, grounding firewall, leading indicators modules.
"""
import json
import math
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

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

    now = datetime.now(timezone.utc)

    # Seed events across categories and countries for indicator detection
    categories = ["military", "political", "economic", "health", "environmental"]
    countries = ["US", "CN", "RU", "IR", "UA"]
    for day_offset in range(90):
        for cat_idx, cat in enumerate(categories):
            # Create varying event counts to produce correlations
            count = 1 + (day_offset % (cat_idx + 3))
            for i in range(min(count, 3)):
                eid = f"evt-ai-{day_offset}-{cat}-{i}"
                ts = (now - timedelta(days=day_offset)).isoformat()
                cc = countries[day_offset % len(countries)]
                c.execute(
                    """INSERT OR IGNORE INTO events
                       (id, source, title, category, severity, country_code, region, timestamp,
                        summary, entities_json)
                       VALUES (?, 'test', ?, ?, ?, ?, 'Test Region', ?, ?, '[]')""",
                    (eid, f"Test {cat} event day-{day_offset} #{i}", cat,
                     30 + day_offset % 50, cc, ts,
                     f"Summary of {cat} event in {cc}"),
                )

    # Seed entities
    c.execute(
        """INSERT OR IGNORE INTO entities (id, name, entity_type, event_count, first_seen, last_seen)
           VALUES ('ent-1', 'Test Person', 'person', 10, ?, ?)""",
        (now.isoformat(), now.isoformat()),
    )

    # Seed a brief for grounding audit testing
    brief_content = (
        "## Executive Summary\n"
        "Major military events detected [evt-ai-0-military-0] in the region.\n"
        "Economic indicators [evt-ai-1-economic-0] suggest rising instability.\n"
        "Unverified reports [fake-id-999] claim further escalation.\n"
    )
    c.execute(
        """INSERT OR IGNORE INTO briefs
           (id, brief_type, title, content, summary, event_ids, entity_ids,
            grounding_score, model_used)
           VALUES (?, 'daily', 'Test Brief', ?, 'Test summary', '[]', '[]', 0.0, NULL)""",
        ("brief-test-1", brief_content),
    )

    # Seed a fusion signal
    c.execute(
        """INSERT OR IGNORE INTO fusion_signals
           (id, signal_type, title, description, severity, confidence,
            event_ids, entity_ids, grounding_score, model_used)
           VALUES (?, 'military_escalation', 'Test Signal',
                   'Escalation detected [evt-ai-0-military-0] and [fake-signal-ref]',
                   75, 0.8, '[]', '[]', 0.0, NULL)""",
        ("fusion-test-1",),
    )

    c.commit()
    yield c
    c.close()
    os.unlink(path)


# ─── Multi-Perspective ────────────────────────────────────────

class TestMultiPerspective:
    def test_identify_actors(self, conn):
        from intelligence.perspectives import identify_actors
        actors = identify_actors(conn)
        assert len(actors) >= 2
        # Should include some of our seeded countries
        assert all(isinstance(a, str) for a in actors)

    def test_gather_scenario_context_by_region(self, conn):
        from intelligence.perspectives import gather_scenario_context
        scenario, events_text = gather_scenario_context(conn, region="Test Region")
        assert "Test Region" in scenario
        assert len(events_text) > 0

    def test_gather_scenario_context_no_input(self, conn):
        from intelligence.perspectives import gather_scenario_context
        scenario, events_text = gather_scenario_context(conn)
        assert scenario == ""
        assert events_text == ""

    def test_compute_divergence_simple(self):
        from intelligence.perspectives import compute_divergence_simple
        # All agree → low divergence
        perspectives_agree = [
            {"escalation_risk": 0.7},
            {"escalation_risk": 0.8},
            {"escalation_risk": 0.75},
        ]
        div = compute_divergence_simple(perspectives_agree)
        assert div < 0.1

        # Disagreement → high divergence
        perspectives_disagree = [
            {"escalation_risk": 0.1},
            {"escalation_risk": 0.9},
        ]
        div2 = compute_divergence_simple(perspectives_disagree)
        assert div2 > 0.3

    def test_compute_divergence_single_actor(self):
        from intelligence.perspectives import compute_divergence_simple
        assert compute_divergence_simple([{"escalation_risk": 0.5}]) == 0.0

    def test_run_simulation_no_api_key(self, conn):
        from intelligence.perspectives import run_multi_perspective
        with patch("intelligence.perspectives.CLAUDE_API_KEY", ""):
            result = run_multi_perspective(conn, region="Test Region")
        assert result["simulation_id"] is not None
        assert len(result["actors"]) >= 2
        assert len(result["perspectives"]) >= 2
        assert result["model_used"] is None
        # Perspectives should be stubs
        assert "not available" in result["perspectives"][0]["interpretation"]

    def test_simulation_stored_in_db(self, conn):
        from intelligence.perspectives import list_simulations
        sims = list_simulations(conn)
        assert len(sims) >= 1
        assert sims[0]["scenario_title"] is not None

    def test_get_simulation(self, conn):
        from intelligence.perspectives import list_simulations, get_simulation
        sims = list_simulations(conn)
        sim = get_simulation(conn, sims[0]["id"])
        assert sim is not None
        assert isinstance(sim["actors"], list)
        assert isinstance(sim["perspectives"], list)

    def test_get_simulation_not_found(self, conn):
        from intelligence.perspectives import get_simulation
        assert get_simulation(conn, "nonexistent") is None


# ─── Grounding Firewall ──────────────────────────────────────

class TestGrounding:
    def test_extract_referenced_ids(self):
        from intelligence.grounding import extract_referenced_ids
        text = "Event [evt-ai-0-military-0] caused escalation. Related: [evt-ai-1-economic-0]."
        ids = extract_referenced_ids(text)
        assert "evt-ai-0-military-0" in ids
        assert "evt-ai-1-economic-0" in ids

    def test_extract_no_ids(self):
        from intelligence.grounding import extract_referenced_ids
        ids = extract_referenced_ids("No references here.")
        assert len(ids) == 0

    def test_get_valid_event_ids(self, conn):
        from intelligence.grounding import get_valid_event_ids
        ids = get_valid_event_ids(conn, {"evt-ai-0-military-0", "fake-id-999"})
        assert "evt-ai-0-military-0" in ids
        assert "fake-id-999" not in ids

    def test_simple_grounding_score_all_valid(self, conn):
        from intelligence.grounding import compute_grounding_score_simple, get_valid_event_ids
        valid = get_valid_event_ids(conn)
        text = f"Event [{list(valid)[0]}] happened."
        result = compute_grounding_score_simple(text, valid)
        assert result["grounding_score"] == 1.0
        assert result["invalid_references"] == 0

    def test_simple_grounding_score_mixed(self, conn):
        from intelligence.grounding import compute_grounding_score_simple, get_valid_event_ids
        valid = get_valid_event_ids(conn)
        real_id = list(valid)[0]
        text = f"Event [{real_id}] and [fake-id-999] detected."
        result = compute_grounding_score_simple(text, valid)
        assert result["grounding_score"] == 0.5
        assert result["invalid_references"] == 1

    def test_simple_grounding_no_refs(self, conn):
        from intelligence.grounding import compute_grounding_score_simple
        result = compute_grounding_score_simple("No references.", set())
        assert result["grounding_score"] == 0.0
        assert result["total_references"] == 0

    def test_audit_text_no_api_key(self, conn):
        from intelligence.grounding import audit_text
        with patch("intelligence.grounding.CLAUDE_API_KEY", ""):
            result = audit_text(
                conn,
                "Event [evt-ai-0-military-0] and [fake-id-999] detected.",
                "test", "test-1",
            )
        assert result["audit_id"] is not None
        assert result["grounding_score"] == 0.5
        assert result["model_used"] is None
        assert len(result["flagged_claims"]) >= 1

    def test_audit_stored_in_db(self, conn):
        from intelligence.grounding import list_audits
        audits = list_audits(conn)
        assert len(audits) >= 1

    def test_get_audit(self, conn):
        from intelligence.grounding import list_audits, get_audit
        audits = list_audits(conn)
        audit = get_audit(conn, audits[0]["id"])
        assert audit is not None
        assert "flagged_claims" in audit

    def test_sanitize_text_no_api_key(self, conn):
        from intelligence.grounding import sanitize_text
        with patch("intelligence.grounding.CLAUDE_API_KEY", ""):
            result = sanitize_text(
                conn,
                "Event [evt-ai-0-military-0] and [fake-id-999] detected.",
            )
        assert "UNVERIFIED" in result["sanitized_text"]
        assert result["flagged_count"] >= 1

    def test_audit_brief(self, conn):
        from intelligence.grounding import audit_brief
        with patch("intelligence.grounding.CLAUDE_API_KEY", ""):
            result = audit_brief(conn, "brief-test-1")
        assert result["target_type"] == "brief"
        assert result["grounding_score"] >= 0
        # Should flag fake-id-999
        assert any("fake-id-999" in str(f) for f in result.get("flagged_claims", []))

    def test_audit_brief_not_found(self, conn):
        from intelligence.grounding import audit_brief
        result = audit_brief(conn, "nonexistent")
        assert "error" in result

    def test_audit_fusion_signal(self, conn):
        from intelligence.grounding import audit_fusion_signal
        with patch("intelligence.grounding.CLAUDE_API_KEY", ""):
            result = audit_fusion_signal(conn, "fusion-test-1")
        assert result["target_type"] == "fusion_signal"


# ─── Leading Indicators ──────────────────────────────────────

class TestLeadingIndicators:
    def test_pearson_correlation_perfect(self):
        from detection.leading_indicators import pearson_correlation
        x = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        y = [2, 4, 6, 8, 10, 12, 14, 16, 18, 20]
        assert abs(pearson_correlation(x, y) - 1.0) < 0.001

    def test_pearson_correlation_negative(self):
        from detection.leading_indicators import pearson_correlation
        x = [1, 2, 3, 4, 5]
        y = [10, 8, 6, 4, 2]
        assert abs(pearson_correlation(x, y) - (-1.0)) < 0.001

    def test_pearson_correlation_zero(self):
        from detection.leading_indicators import pearson_correlation
        # Constant series → no correlation
        assert pearson_correlation([5, 5, 5, 5, 5], [1, 2, 3, 4, 5]) == 0.0

    def test_pearson_too_few(self):
        from detection.leading_indicators import pearson_correlation
        assert pearson_correlation([1, 2], [3, 4]) == 0.0

    def test_fill_daily_series(self):
        from detection.leading_indicators import fill_daily_series
        series = fill_daily_series([], days=30)
        assert len(series) == 30
        assert all(v == 0 for v in series)

    def test_compute_lagged_correlation(self):
        from detection.leading_indicators import compute_lagged_correlation
        # Leading by 5 days
        leading = list(range(50))
        lagging = [0] * 5 + list(range(45))
        corr = compute_lagged_correlation(leading, lagging, 5)
        assert corr > 0.9  # Should be highly correlated with 5-day lag

    def test_compute_lagged_correlation_zero_lag(self):
        from detection.leading_indicators import compute_lagged_correlation
        assert compute_lagged_correlation([1, 2, 3], [4, 5, 6], 0) == 0.0

    def test_find_best_lag(self):
        from detection.leading_indicators import find_best_lag
        # Create series where leading perfectly predicts lagging at lag=10
        leading = [0] * 50
        lagging = [0] * 50
        for i in range(10, 40):
            leading[i] = 5
            lagging[i + 10] = 5 if i + 10 < 50 else 0
        best_lag, best_corr = find_best_lag(leading, lagging, max_lag=20)
        # Should find a lag near 10 with positive correlation
        assert 7 <= best_lag <= 15
        assert best_corr > 0

    def test_get_daily_event_counts(self, conn):
        from detection.leading_indicators import get_daily_event_counts
        counts = get_daily_event_counts(conn, "military", days=90)
        assert len(counts) >= 1
        # Each entry is (date_str, count)
        assert all(isinstance(c[1], int) for c in counts)

    def test_scan_indicators(self, conn):
        from detection.leading_indicators import scan_indicators
        results = scan_indicators(conn, days=90)
        assert len(results) >= 1
        for r in results:
            assert "pattern" in r
            assert "status" in r
            assert r["status"] in ("firing", "dormant", "weak")
            assert "correlation_at_typical_lag" in r

    def test_scan_indicators_with_country(self, conn):
        from detection.leading_indicators import scan_indicators
        results = scan_indicators(conn, country_code="US", days=90)
        assert isinstance(results, list)

    def test_run_indicator_scan(self, conn):
        from detection.leading_indicators import run_indicator_scan
        result = run_indicator_scan(conn)
        assert "total_patterns_checked" in result
        assert "firing" in result
        assert "dormant" in result
        assert "indicators" in result

    def test_list_indicators(self, conn):
        from detection.leading_indicators import list_indicators
        indicators = list_indicators(conn)
        assert isinstance(indicators, list)

    def test_known_patterns_exist(self):
        from detection.leading_indicators import KNOWN_PATTERNS
        assert len(KNOWN_PATTERNS) >= 5
        for p in KNOWN_PATTERNS:
            assert "name" in p
            assert "leading" in p
            assert "lagging" in p
            assert "typical_lag_days" in p

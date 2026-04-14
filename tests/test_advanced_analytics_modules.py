"""
Tests — Historical analogs, cascade models, narrative divergence,
contrarian signals, narrative arcs (module-level).
"""
import json
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

    # Seed events across categories, sources, and countries
    categories = ["military", "political", "economic", "health", "environmental"]
    sources = ["gdelt", "acled", "reuters", "bbc", "xinhua"]
    countries = ["US", "CN", "RU", "IR", "UA"]

    for day_offset in range(60):
        for cat_idx, cat in enumerate(categories):
            count = 1 + (day_offset % (cat_idx + 2))
            for i in range(min(count, 3)):
                eid = f"evt-adv-{day_offset}-{cat}-{i}"
                ts = (now - timedelta(days=day_offset)).isoformat()
                cc = countries[day_offset % len(countries)]
                src = sources[(day_offset + cat_idx) % len(sources)]
                sev = 30 + day_offset % 50
                c.execute(
                    """INSERT OR IGNORE INTO events
                       (id, source, source_id, title, category, severity,
                        country_code, region, timestamp, summary, entities_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]')""",
                    (eid, src, eid,
                     f"Test {cat} event day-{day_offset} #{i} in {cc}",
                     cat, sev, cc, "Test Region", ts,
                     f"Summary of {cat} event in {cc} from {src}"),
                )

    # Seed a high-severity military event for analog matching
    c.execute(
        """INSERT OR IGNORE INTO events
           (id, source, source_id, title, category, severity,
            country_code, region, timestamp, summary)
           VALUES (?, 'test', ?, ?, 'military', 85, 'UA', 'Eastern Europe', ?, ?)""",
        ("evt-adv-trigger", "evt-adv-trigger",
         "Military buildup near border", now.isoformat(),
         "Significant military buildup detected near eastern border"),
    )

    c.commit()
    yield c
    c.close()
    os.unlink(path)


# ─── Historical Analogs ────────────────────────────────────────

class TestHistoricalAnalogs:
    def test_catalog_has_entries(self):
        from intelligence.historical_analogs import HISTORICAL_ANALOGS
        assert len(HISTORICAL_ANALOGS) >= 10
        for a in HISTORICAL_ANALOGS:
            assert "title" in a
            assert "signature" in a
            assert "outcome" in a

    def test_compute_signature_match(self):
        from intelligence.historical_analogs import compute_signature_match, HISTORICAL_ANALOGS
        profile = {
            "categories": ["military", "political"],
            "avg_severity": 80,
            "titles": ["Military buildup near border", "Troop movements detected"],
        }
        # Crimea analog should score well for military+political
        crimea = next(a for a in HISTORICAL_ANALOGS if "Crimea" in a["title"])
        score = compute_signature_match(profile, crimea)
        assert score > 0.3

    def test_signature_match_low_for_mismatch(self):
        from intelligence.historical_analogs import compute_signature_match, HISTORICAL_ANALOGS
        profile = {
            "categories": ["health"],
            "avg_severity": 30,
            "titles": ["Flu cases reported"],
        }
        crimea = next(a for a in HISTORICAL_ANALOGS if "Crimea" in a["title"])
        score = compute_signature_match(profile, crimea)
        assert score < 0.5

    def test_build_event_profile(self, conn):
        from intelligence.historical_analogs import build_event_profile
        profile = build_event_profile(conn, region="Test Region", category="military")
        assert profile["event_count"] >= 1
        assert "military" in profile["categories"]

    def test_find_analogs(self, conn):
        from intelligence.historical_analogs import find_analogs
        with patch("intelligence.historical_analogs.CLAUDE_API_KEY", ""):
            analogs = find_analogs(conn, region="Test Region", category="military", top_n=3)
        assert len(analogs) >= 1
        assert all(a["similarity_score"] >= 0 for a in analogs)
        # Should be sorted by score
        scores = [a["similarity_score"] for a in analogs]
        assert scores == sorted(scores, reverse=True)

    def test_run_analog_search(self, conn):
        from intelligence.historical_analogs import run_analog_search
        with patch("intelligence.historical_analogs.CLAUDE_API_KEY", ""):
            result = run_analog_search(conn, region="Test Region", category="military")
        assert result["total_analogs_checked"] >= 10
        assert result["matches_found"] >= 1

    def test_list_analog_matches(self, conn):
        from intelligence.historical_analogs import list_analog_matches
        matches = list_analog_matches(conn)
        assert len(matches) >= 1
        assert "analog_title" in matches[0]

    def test_get_analog_match(self, conn):
        from intelligence.historical_analogs import list_analog_matches, get_analog_match
        matches = list_analog_matches(conn)
        match = get_analog_match(conn, matches[0]["id"])
        assert match is not None
        assert isinstance(match["key_similarities"], list)

    def test_get_analog_not_found(self, conn):
        from intelligence.historical_analogs import get_analog_match
        assert get_analog_match(conn, "nonexistent") is None


# ─── Cascade Models ────────────────────────────────────────────

class TestCascadeModels:
    def test_cascade_rules_exist(self):
        from intelligence.cascade_model import CASCADE_RULES
        assert len(CASCADE_RULES) >= 10
        for r in CASCADE_RULES:
            assert "trigger" in r
            assert "effect" in r
            assert "probability" in r
            assert 0 < r["probability"] <= 1

    def test_get_cascade_rules_for(self):
        from intelligence.cascade_model import get_cascade_rules_for
        mil_rules = get_cascade_rules_for("military")
        assert len(mil_rules) >= 1
        assert all(r["trigger"] == "military" for r in mil_rules)

    def test_build_cascade_chain(self):
        from intelligence.cascade_model import build_cascade_chain
        steps = build_cascade_chain("environmental", 70)
        assert len(steps) >= 2
        # First step should be triggered by environmental
        assert steps[0]["source_category"] == "environmental"
        # All steps should have positive delay and valid categories
        for s in steps:
            assert s["delay_days"] > 0
            assert s["category"] in ("military", "political", "economic", "health", "environmental")

    def test_build_cascade_chain_no_loops(self):
        from intelligence.cascade_model import build_cascade_chain
        steps = build_cascade_chain("political", 50, max_depth=10)
        edges = [(s["source_category"], s["category"]) for s in steps]
        # No duplicate edges
        assert len(edges) == len(set(edges))

    def test_model_cascade_with_event(self, conn):
        from intelligence.cascade_model import model_cascade
        with patch("intelligence.cascade_model.CLAUDE_API_KEY", ""):
            result = model_cascade(conn, event_id="evt-adv-trigger")
        assert result["trigger_description"] is not None
        assert len(result["cascade_steps"]) >= 1
        assert result["total_steps"] >= 1
        assert 0 < result["probability_chain"] <= 1

    def test_model_cascade_with_description(self, conn):
        from intelligence.cascade_model import model_cascade
        with patch("intelligence.cascade_model.CLAUDE_API_KEY", ""):
            result = model_cascade(
                conn,
                trigger_description="Major earthquake in coastal city",
                region="Southeast Asia",
                category="environmental",
            )
        assert len(result["cascade_steps"]) >= 1
        assert result["max_severity"] > 0

    def test_model_cascade_no_input(self, conn):
        from intelligence.cascade_model import model_cascade
        result = model_cascade(conn)
        assert "error" in result

    def test_run_cascade_model(self, conn):
        from intelligence.cascade_model import run_cascade_model
        with patch("intelligence.cascade_model.CLAUDE_API_KEY", ""):
            result = run_cascade_model(
                conn,
                trigger_description="Economic sanctions imposed",
                category="economic",
            )
        assert "cascade_id" in result
        assert result["total_steps"] >= 1

    def test_list_cascades(self, conn):
        from intelligence.cascade_model import list_cascades
        cascades = list_cascades(conn)
        assert len(cascades) >= 1

    def test_get_cascade(self, conn):
        from intelligence.cascade_model import list_cascades, get_cascade
        cascades = list_cascades(conn)
        cascade = get_cascade(conn, cascades[0]["id"])
        assert cascade is not None
        assert isinstance(cascade["cascade_steps"], list)

    def test_get_cascade_not_found(self, conn):
        from intelligence.cascade_model import get_cascade
        assert get_cascade(conn, "nonexistent") is None


# ─── Narrative Divergence ──────────────────────────────────────

class TestNarrativeDivergence:
    def test_tokenize(self):
        from intelligence.narrative_divergence import tokenize
        tokens = tokenize("The military buildup continues in the region")
        assert "military" in tokens
        assert "buildup" in tokens
        assert "the" not in tokens  # stopword removed

    def test_jaccard_similarity_identical(self):
        from intelligence.narrative_divergence import jaccard_similarity
        a = {"military", "buildup", "region"}
        assert jaccard_similarity(a, a) == 1.0

    def test_jaccard_similarity_disjoint(self):
        from intelligence.narrative_divergence import jaccard_similarity
        a = {"military", "buildup"}
        b = {"economic", "crisis"}
        assert jaccard_similarity(a, b) == 0.0

    def test_jaccard_similarity_partial(self):
        from intelligence.narrative_divergence import jaccard_similarity
        a = {"military", "buildup", "region"}
        b = {"military", "crisis", "region"}
        sim = jaccard_similarity(a, b)
        assert 0.3 < sim < 0.8

    def test_cluster_events_by_source(self):
        from intelligence.narrative_divergence import cluster_events_by_source
        events = [
            {"source": "reuters", "title": "Event 1"},
            {"source": "bbc", "title": "Event 2"},
            {"source": "reuters", "title": "Event 3"},
        ]
        clusters = cluster_events_by_source(events)
        assert len(clusters) == 2
        assert len(clusters["reuters"]) == 2

    def test_compute_pairwise_divergence(self):
        from intelligence.narrative_divergence import compute_pairwise_divergence
        # Very different narratives
        clusters = {
            "reuters": [{"title": "Military escalation continues", "summary": "Troops deployed"}],
            "xinhua": [{"title": "Peace talks productive", "summary": "Diplomatic progress"}],
        }
        div = compute_pairwise_divergence(clusters)
        assert div > 0.5  # should be high divergence

    def test_compute_divergence_single_source(self):
        from intelligence.narrative_divergence import compute_pairwise_divergence
        clusters = {"reuters": [{"title": "Test", "summary": "Test"}]}
        assert compute_pairwise_divergence(clusters) == 0.0

    def test_analyze_divergence(self, conn):
        from intelligence.narrative_divergence import analyze_divergence
        with patch("intelligence.narrative_divergence.CLAUDE_API_KEY", ""):
            result = analyze_divergence(conn, topic="military", region="Test Region")
        assert result["topic"] == "military"
        assert isinstance(result["divergence_score"], float)
        assert result["event_count"] >= 0

    def test_run_divergence_analysis(self, conn):
        from intelligence.narrative_divergence import run_divergence_analysis
        with patch("intelligence.narrative_divergence.CLAUDE_API_KEY", ""):
            result = run_divergence_analysis(conn, topic="military", region="Test Region")
        assert "divergence_score" in result

    def test_list_divergence_analyses(self, conn):
        from intelligence.narrative_divergence import list_divergence_analyses
        analyses = list_divergence_analyses(conn)
        assert isinstance(analyses, list)

    def test_get_divergence_not_found(self, conn):
        from intelligence.narrative_divergence import get_divergence_analysis
        assert get_divergence_analysis(conn, "nonexistent") is None


# ─── Contrarian Signals ───────────────────────────────────────

class TestContrarianSignals:
    def test_get_severity_trend(self, conn):
        from detection.contrarian_signals import get_severity_trend
        trend = get_severity_trend(conn, "military")
        assert trend["category"] == "military"
        assert trend["direction"] in ("escalating", "de-escalating", "stable", "flat")
        assert trend["total_events"] >= 0

    def test_detect_severity_outliers(self, conn):
        from detection.contrarian_signals import detect_severity_outliers
        outliers = detect_severity_outliers(conn)
        assert isinstance(outliers, list)
        for o in outliers:
            assert o["signal_type"] == "outlier"
            assert o["strength"] >= 0

    def test_detect_category_anomalies(self, conn):
        from detection.contrarian_signals import detect_category_anomalies
        anomalies = detect_category_anomalies(conn)
        assert isinstance(anomalies, list)

    def test_scan_contrarian_signals(self, conn):
        from detection.contrarian_signals import scan_contrarian_signals
        signals = scan_contrarian_signals(conn)
        assert isinstance(signals, list)
        # Should be sorted by strength
        if len(signals) >= 2:
            assert signals[0]["strength"] >= signals[-1]["strength"]

    def test_run_contrarian_scan(self, conn):
        from detection.contrarian_signals import run_contrarian_scan
        result = run_contrarian_scan(conn)
        assert "total_signals" in result
        assert "by_type" in result
        assert "signals" in result

    def test_scan_with_country_filter(self, conn):
        from detection.contrarian_signals import scan_contrarian_signals
        signals = scan_contrarian_signals(conn, country_code="US")
        assert isinstance(signals, list)

    def test_list_contrarian_signals(self, conn):
        from detection.contrarian_signals import list_contrarian_signals
        signals = list_contrarian_signals(conn)
        assert isinstance(signals, list)

    def test_get_contrarian_not_found(self, conn):
        from detection.contrarian_signals import get_contrarian_signal
        assert get_contrarian_signal(conn, "nonexistent") is None


# ─── Narrative Arcs ───────────────────────────────────────────

class TestNarrativeArcs:
    def test_compute_arc_metrics_no_events(self):
        from detection.narrative_arcs import compute_arc_metrics
        metrics = compute_arc_metrics([])
        assert metrics["phase"] == "dormant"
        assert metrics["intensity"] == 0.0

    def test_compute_arc_metrics_with_events(self):
        from detection.narrative_arcs import compute_arc_metrics
        now = datetime.now(timezone.utc)
        events = [
            {"severity": 70, "timestamp": (now - timedelta(days=i)).isoformat(),
             "source": "test"} for i in range(10)
        ]
        metrics = compute_arc_metrics(events)
        assert metrics["phase"] in ("emerging", "escalating", "peak", "declining", "dormant")
        assert 0 <= metrics["intensity"] <= 1.0
        assert metrics["event_count"] == 10

    def test_compute_arc_metrics_emerging(self):
        from detection.narrative_arcs import compute_arc_metrics
        now = datetime.now(timezone.utc)
        # Only 2 very recent events → emerging
        events = [
            {"severity": 50, "timestamp": (now - timedelta(days=1)).isoformat(), "source": "a"},
            {"severity": 55, "timestamp": (now - timedelta(days=2)).isoformat(), "source": "b"},
        ]
        metrics = compute_arc_metrics(events)
        assert metrics["phase"] in ("emerging", "dormant")

    def test_get_topic_events(self, conn):
        from detection.narrative_arcs import get_topic_events
        events = get_topic_events(conn, "military", region="Test Region")
        assert isinstance(events, list)

    def test_track_narrative_arc(self, conn):
        from detection.narrative_arcs import track_narrative_arc
        with patch("detection.narrative_arcs.CLAUDE_API_KEY", ""):
            arc = track_narrative_arc(conn, "military", region="Test Region")
        assert arc["topic"] == "military"
        assert arc["arc_phase"] in ("emerging", "escalating", "peak", "declining", "dormant")
        assert 0 <= arc["intensity"] <= 1.0

    def test_run_arc_tracker(self, conn):
        from detection.narrative_arcs import run_arc_tracker
        with patch("detection.narrative_arcs.CLAUDE_API_KEY", ""):
            arc = run_arc_tracker(conn, "military", region="Test Region")
        assert "arc_id" in arc
        assert arc["arc_id"] is not None

    def test_run_arc_tracker_updates_existing(self, conn):
        from detection.narrative_arcs import run_arc_tracker
        with patch("detection.narrative_arcs.CLAUDE_API_KEY", ""):
            arc1 = run_arc_tracker(conn, "military", region="Test Region")
            arc2 = run_arc_tracker(conn, "military", region="Test Region")
        # Should update the same arc
        assert arc2["arc_id"] == arc1["arc_id"]

    def test_list_narrative_arcs(self, conn):
        from detection.narrative_arcs import list_narrative_arcs
        arcs = list_narrative_arcs(conn)
        assert len(arcs) >= 1

    def test_get_narrative_arc(self, conn):
        from detection.narrative_arcs import list_narrative_arcs, get_narrative_arc
        arcs = list_narrative_arcs(conn)
        arc = get_narrative_arc(conn, arcs[0]["id"])
        assert arc is not None
        assert isinstance(arc["phase_history"], list)

    def test_get_arc_not_found(self, conn):
        from detection.narrative_arcs import get_narrative_arc
        assert get_narrative_arc(conn, "nonexistent") is None

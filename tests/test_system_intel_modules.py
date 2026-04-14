"""
Module-level tests — Ambient narration, proactive push, system self-awareness,
historical replay, commodity dependency, capital flight.
"""
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta

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

    # Seed events for proactive scan and replay
    now = datetime.now(timezone.utc)
    for i in range(20):
        ts = (now - timedelta(hours=i)).isoformat()
        sev = 50 + (i * 3) % 40
        c.execute(
            """INSERT OR IGNORE INTO events
               (id, source, title, category, severity,
                latitude, longitude, country_code, region, timestamp, summary)
               VALUES (?, 'test', ?, 'economic', ?, 33.0, 44.0, 'IQ', 'Middle East', ?, ?)""",
            (f"evt-sysintel-{i}", f"Econ event {i}", min(sev, 100),
             ts, f"Summary {i}"),
        )
    # Add some military events too
    for i in range(10):
        ts = (now - timedelta(hours=i)).isoformat()
        c.execute(
            """INSERT OR IGNORE INTO events
               (id, source, title, category, severity,
                latitude, longitude, country_code, region, timestamp, summary)
               VALUES (?, 'acled', ?, 'military', ?, 48.8, 2.3, 'FR', 'Western Europe', ?, ?)""",
            (f"evt-sysintel-mil-{i}", f"Military event {i}", 60 + i * 2,
             ts, f"Military summary {i}"),
        )
    c.commit()
    yield c
    c.close()
    os.unlink(path)


# ─── Ambient Narration ──────────────────────────────────────

class TestAmbientNarration:
    def test_log_activity(self, conn):
        from intelligence.ambient_narration import log_activity
        log_id = log_activity(conn, "ingestion", "Ingested 150 events from GDELT",
                             metadata={"source": "gdelt", "count": 150})
        assert log_id > 0

    def test_log_multiple(self, conn):
        from intelligence.ambient_narration import log_activity
        log_activity(conn, "processing", "Classified 50 events", level="info")
        log_activity(conn, "intelligence", "Generated 3 briefs", level="info")
        log_activity(conn, "detection", "Anomaly detected in IQ", level="warning")
        log_activity(conn, "system", "Database backup completed", level="info")

    def test_get_activity_feed(self, conn):
        from intelligence.ambient_narration import get_activity_feed
        feed = get_activity_feed(conn, minutes=120)
        assert len(feed) >= 5

    def test_feed_filter_by_component(self, conn):
        from intelligence.ambient_narration import get_activity_feed
        feed = get_activity_feed(conn, component="ingestion", minutes=120)
        assert all(e["component"] == "ingestion" for e in feed)

    def test_feed_filter_by_level(self, conn):
        from intelligence.ambient_narration import get_activity_feed
        feed = get_activity_feed(conn, level="warning", minutes=120)
        assert all(e["level"] == "warning" for e in feed)

    def test_activity_summary(self, conn):
        from intelligence.ambient_narration import get_activity_summary
        summary = get_activity_summary(conn, minutes=120)
        assert summary["total_entries"] >= 5
        assert "ingestion" in summary["by_component"]
        assert "info" in summary["by_level"]

    def test_generate_narration(self, conn):
        from intelligence.ambient_narration import generate_narration
        ticker = generate_narration(conn, limit=5)
        assert len(ticker) >= 1
        assert "text" in ticker[0]
        assert "icon" in ticker[0]


# ─── Proactive Intelligence Push ────────────────────────────

class TestProactivePush:
    def test_create_alert(self, conn):
        from intelligence.proactive_push import create_alert
        aid = create_alert(
            conn, "threshold_breach",
            "Severity spike in Iraq",
            summary="Average severity 78 across 12 events",
            priority="high",
            trigger_rule={"rule": "severity_spike", "threshold": 70},
            country_code="IQ",
        )
        assert aid is not None

    def test_create_more_alerts(self, conn):
        from intelligence.proactive_push import create_alert
        create_alert(conn, "pattern_match", "Multi-source convergence: FR",
                    priority="medium", country_code="FR")
        create_alert(conn, "anomaly", "Unusual event burst detected",
                    priority="low")

    def test_get_alert(self, conn):
        from intelligence.proactive_push import list_alerts, get_alert
        items = list_alerts(conn, hours=24)
        assert len(items) >= 3
        item = get_alert(conn, items[0]["id"])
        assert item is not None
        assert "title" in item

    def test_get_alert_not_found(self, conn):
        from intelligence.proactive_push import get_alert
        assert get_alert(conn, "nonexistent") is None

    def test_list_by_status(self, conn):
        from intelligence.proactive_push import list_alerts
        pending = list_alerts(conn, status="pending", hours=24)
        assert all(a["status"] == "pending" for a in pending)

    def test_list_by_priority(self, conn):
        from intelligence.proactive_push import list_alerts
        high = list_alerts(conn, priority="high", hours=24)
        assert all(a["priority"] == "high" for a in high)

    def test_update_status(self, conn):
        from intelligence.proactive_push import list_alerts, update_alert_status, get_alert
        items = list_alerts(conn, hours=24)
        aid = items[0]["id"]
        ok = update_alert_status(conn, aid, "delivered")
        assert ok is True
        alert = get_alert(conn, aid)
        assert alert["status"] == "delivered"
        assert alert["delivered_at"] is not None

    def test_update_invalid_status(self, conn):
        from intelligence.proactive_push import list_alerts, update_alert_status
        items = list_alerts(conn, hours=24)
        ok = update_alert_status(conn, items[0]["id"], "bogus")
        assert ok is False

    def test_scan_for_alerts(self, conn):
        from intelligence.proactive_push import scan_for_alerts
        # Our seeded data should trigger at least the event burst or severity spike
        results = scan_for_alerts(conn, hours=24)
        assert isinstance(results, list)


# ─── System Self-Awareness ──────────────────────────────────

class TestSystemAwareness:
    def test_register_component(self, conn):
        from intelligence.system_awareness import register_component
        cid = register_component(conn, "gdelt-ingester", "ingestion",
                                config={"interval_minutes": 15})
        assert cid is not None

    def test_register_more(self, conn):
        from intelligence.system_awareness import register_component
        register_component(conn, "event-classifier", "processing")
        register_component(conn, "brief-generator", "intelligence")
        register_component(conn, "api-server", "api")

    def test_heartbeat(self, conn):
        from intelligence.system_awareness import heartbeat
        ok = heartbeat(conn, "gdelt-ingester", "healthy",
                      metrics={"events_processed": 1500, "avg_latency_ms": 45})
        assert ok is True

    def test_heartbeat_not_found(self, conn):
        from intelligence.system_awareness import heartbeat
        ok = heartbeat(conn, "nonexistent-component", "healthy")
        assert ok is False

    def test_report_error(self, conn):
        from intelligence.system_awareness import report_error, get_component
        report_error(conn, "event-classifier", "Model loading failed: OOM")
        comp = get_component(conn, "event-classifier")
        assert comp["status"] == "degraded"
        assert "OOM" in comp["last_error"]

    def test_get_component(self, conn):
        from intelligence.system_awareness import get_component
        comp = get_component(conn, "gdelt-ingester")
        assert comp is not None
        assert comp["component_type"] == "ingestion"

    def test_get_component_not_found(self, conn):
        from intelligence.system_awareness import get_component
        assert get_component(conn, "nonexistent") is None

    def test_list_components(self, conn):
        from intelligence.system_awareness import list_components
        comps = list_components(conn)
        assert len(comps) >= 4

    def test_list_by_status(self, conn):
        from intelligence.system_awareness import list_components
        degraded = list_components(conn, status="degraded")
        assert len(degraded) >= 1

    def test_database_metrics(self, conn):
        from intelligence.system_awareness import get_database_metrics
        metrics = get_database_metrics(conn)
        assert metrics["total_rows"] > 0
        assert "events" in metrics["table_counts"]
        assert metrics["table_counts"]["events"] >= 30

    def test_diagnostic_report(self, conn):
        from intelligence.system_awareness import generate_diagnostic_report
        report = generate_diagnostic_report(conn)
        assert report["overall_status"] in ("healthy", "degraded", "critical")
        assert report["total_components"] >= 4
        assert "database" in report


# ─── Historical Replay ──────────────────────────────────────

class TestHistoricalReplay:
    def test_create_snapshot(self, conn):
        from intelligence.historical_replay import create_snapshot
        result = create_snapshot(conn, label="Test snapshot")
        assert "snapshot_id" in result
        assert result["event_count"] >= 30

    def test_create_past_snapshot(self, conn):
        from intelligence.historical_replay import create_snapshot
        past = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
        result = create_snapshot(conn, snapshot_time=past, label="12h ago")
        assert result["event_count"] >= 0

    def test_get_snapshot(self, conn):
        from intelligence.historical_replay import list_snapshots, get_snapshot
        snaps = list_snapshots(conn)
        assert len(snaps) >= 2
        snap = get_snapshot(conn, snaps[0]["id"])
        assert snap is not None
        assert "summary_stats" in snap

    def test_get_snapshot_not_found(self, conn):
        from intelligence.historical_replay import get_snapshot
        assert get_snapshot(conn, "nonexistent") is None

    def test_list_snapshots(self, conn):
        from intelligence.historical_replay import list_snapshots
        snaps = list_snapshots(conn)
        assert len(snaps) >= 2

    def test_replay_events(self, conn):
        from intelligence.historical_replay import replay_events
        now = datetime.now(timezone.utc).isoformat()
        result = replay_events(conn, now)
        assert result["total_events"] >= 30
        assert len(result["events"]) > 0

    def test_replay_filtered(self, conn):
        from intelligence.historical_replay import replay_events
        now = datetime.now(timezone.utc).isoformat()
        result = replay_events(conn, now, category="military")
        assert all(e["category"] == "military" for e in result["events"])

    def test_replay_past_time(self, conn):
        from intelligence.historical_replay import replay_events
        past = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
        result = replay_events(conn, past)
        # Should have fewer events than "now" since some were after this time
        now_result = replay_events(conn, datetime.now(timezone.utc).isoformat())
        assert result["total_events"] <= now_result["total_events"]

    def test_timeline(self, conn):
        from intelligence.historical_replay import get_timeline
        timeline = get_timeline(conn, days=3, interval_hours=12)
        assert len(timeline) >= 1
        # Timeline should be non-decreasing (cumulative)
        counts = [p["cumulative_events"] for p in timeline]
        assert counts == sorted(counts)


# ─── Commodity Dependency ───────────────────────────────────

class TestCommodityDependency:
    def test_seed_dependencies(self, conn):
        from detection.commodity_dependency import seed_dependencies, list_dependencies
        seed_dependencies(conn)
        # Verify data exists (may have been seeded by another test file)
        deps = list_dependencies(conn)
        assert len(deps) >= 8

    def test_seed_idempotent(self, conn):
        from detection.commodity_dependency import seed_dependencies
        count = seed_dependencies(conn)
        assert count == 0  # Already seeded

    def test_add_dependency(self, conn):
        from detection.commodity_dependency import add_dependency
        did = add_dependency(
            conn, "GB", "Natural Gas", "import",
            share_pct=45.0, top_partners=["NO", "QA", "US"],
            risk_factors=["North Sea depletion"],
        )
        assert did is not None

    def test_get_dependency(self, conn):
        from detection.commodity_dependency import list_dependencies, get_dependency
        items = list_dependencies(conn)
        assert len(items) >= 9
        item = get_dependency(conn, items[0]["id"])
        assert item is not None
        assert isinstance(item["top_partners"], list)

    def test_get_dependency_not_found(self, conn):
        from detection.commodity_dependency import get_dependency
        assert get_dependency(conn, "nonexistent") is None

    def test_list_by_country(self, conn):
        from detection.commodity_dependency import list_dependencies
        cn = list_dependencies(conn, country_code="CN")
        assert len(cn) >= 1

    def test_list_by_commodity(self, conn):
        from detection.commodity_dependency import list_dependencies
        oil = list_dependencies(conn, commodity_name="Crude Oil")
        assert len(oil) >= 2  # CN and IN both import crude

    def test_assess_country_risk(self, conn):
        from detection.commodity_dependency import assess_country_risk
        risk = assess_country_risk(conn, "CN")
        assert risk["total_dependencies"] >= 1
        assert risk["overall_risk"] in ("low", "elevated", "high", "critical")
        assert risk["risk_score"] > 0

    def test_assess_unknown_country(self, conn):
        from detection.commodity_dependency import assess_country_risk
        risk = assess_country_risk(conn, "XX")
        assert risk["overall_risk"] == "unknown"

    def test_disruption_impact(self, conn):
        from detection.commodity_dependency import find_disruption_impact
        impact = find_disruption_impact(conn, "Crude Oil")
        assert impact["import_dependent_countries"] >= 2
        assert len(impact["most_vulnerable"]) >= 1


# ─── Capital Flight Detection ───────────────────────────────

class TestCapitalFlight:
    def test_compute_severity(self):
        from detection.capital_flight import compute_severity
        # Large currency drop = high severity
        high = compute_severity("currency_drop", -15)
        low = compute_severity("currency_drop", -2)
        assert high > low
        assert high > 50

    def test_fx_control_always_high(self):
        from detection.capital_flight import compute_severity
        sev = compute_severity("fx_control", 0)
        assert sev >= 70

    def test_record_signal(self, conn):
        from detection.capital_flight import record_signal
        result = record_signal(
            conn, "TR", "currency_drop",
            indicator_value=28.5, baseline_value=20.0,
            description="Turkish Lira dropped 42.5%",
            evidence=["Central bank data", "Reuters report"],
        )
        assert "signal_id" in result
        assert result["severity"] > 0
        assert result["change_pct"] > 0

    def test_record_multiple_signals(self, conn):
        from detection.capital_flight import record_signal
        record_signal(conn, "TR", "bond_spread",
                     indicator_value=450, baseline_value=150,
                     description="Sovereign bond spread widened to 450bp")
        record_signal(conn, "AR", "reserve_decline",
                     indicator_value=25000, baseline_value=40000,
                     description="Foreign reserves dropped 37.5%")
        record_signal(conn, "AR", "fx_control",
                     indicator_value=1, baseline_value=0,
                     description="Capital controls imposed on forex transactions")

    def test_get_signal(self, conn):
        from detection.capital_flight import list_signals, get_signal
        items = list_signals(conn, days=30)
        assert len(items) >= 4
        item = get_signal(conn, items[0]["id"])
        assert item is not None
        assert isinstance(item["evidence"], list)

    def test_get_signal_not_found(self, conn):
        from detection.capital_flight import get_signal
        assert get_signal(conn, "nonexistent") is None

    def test_list_by_country(self, conn):
        from detection.capital_flight import list_signals
        tr = list_signals(conn, country_code="TR", days=30)
        assert len(tr) >= 2

    def test_list_by_signal_type(self, conn):
        from detection.capital_flight import list_signals
        fx = list_signals(conn, signal_type="fx_control", days=30)
        assert len(fx) >= 1

    def test_update_status(self, conn):
        from detection.capital_flight import list_signals, update_signal_status, get_signal
        items = list_signals(conn, days=30)
        sid = items[0]["id"]
        ok = update_signal_status(conn, sid, "confirmed")
        assert ok is True
        sig = get_signal(conn, sid)
        assert sig["status"] == "confirmed"

    def test_update_invalid(self, conn):
        from detection.capital_flight import update_signal_status
        ok = update_signal_status(conn, "nonexistent", "confirmed")
        assert ok is False

    def test_assess_flight_risk(self, conn):
        from detection.capital_flight import assess_country_flight_risk
        risk = assess_country_flight_risk(conn, "TR", days=30)
        assert risk["active_signals"] >= 1
        assert risk["risk_level"] in ("low", "moderate", "elevated", "high", "critical")
        assert risk["composite_score"] > 0

    def test_assess_no_signals(self, conn):
        from detection.capital_flight import assess_country_flight_risk
        risk = assess_country_flight_risk(conn, "XX", days=30)
        assert risk["risk_level"] == "low"
        assert risk["active_signals"] == 0

    def test_scan_economic_events(self, conn):
        from detection.capital_flight import scan_economic_events
        results = scan_economic_events(conn, days=24)
        assert isinstance(results, list)

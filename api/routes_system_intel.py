"""
System & intelligence features API — ambient narration, proactive push,
system self-awareness, historical replay, commodity mapping, capital flight.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.main import get_db
from intelligence.ambient_narration import (
    log_activity, get_activity_feed, get_activity_summary, generate_narration,
)
from intelligence.proactive_push import (
    create_alert as create_proactive_alert, get_alert, list_alerts,
    update_alert_status, scan_for_alerts,
)
from intelligence.system_awareness import (
    register_component, heartbeat, report_error, get_component,
    list_components, get_database_metrics, generate_diagnostic_report,
)
from intelligence.historical_replay import (
    create_snapshot, get_snapshot, list_snapshots, replay_events, get_timeline,
)
from detection.commodity_dependency import (
    seed_dependencies, add_dependency, get_dependency, list_dependencies,
    assess_country_risk as assess_commodity_risk, find_disruption_impact,
)
from detection.capital_flight import (
    record_signal, get_signal, list_signals, update_signal_status,
    assess_country_flight_risk, scan_economic_events,
)

router = APIRouter(prefix="/api", tags=["system-intel"])


# ─── Ambient Narration (System Activity Ticker) ────────────

class LogActivityRequest(BaseModel):
    component: str
    message: str
    level: str = "info"
    metadata: dict | None = None


@router.post("/narration/log")
def post_log_activity(req: LogActivityRequest):
    """Log a system activity entry."""
    conn = get_db()
    log_id = log_activity(conn, req.component, req.message, req.level, req.metadata)
    return {"log_id": log_id}


@router.get("/narration/feed")
def get_narration_feed(
    component: str | None = None,
    level: str | None = None,
    minutes: int = Query(default=60, le=1440),
    limit: int = Query(default=50, le=200),
):
    """Get the activity feed for the ambient narration ticker."""
    conn = get_db()
    entries = get_activity_feed(conn, component, level, minutes, limit)
    return {"total": len(entries), "entries": entries}


@router.get("/narration/summary")
def get_narration_summary(minutes: int = Query(default=60, le=1440)):
    """Get activity summary by component and level."""
    conn = get_db()
    return get_activity_summary(conn, minutes)


@router.get("/narration/ticker")
def get_ticker(limit: int = Query(default=10, le=50)):
    """Get human-readable narration ticker entries."""
    conn = get_db()
    narrations = generate_narration(conn, limit)
    return {"total": len(narrations), "ticker": narrations}


# ─── Proactive Intelligence Push ────────────────────────────

class ProactiveAlertRequest(BaseModel):
    alert_type: str
    title: str
    summary: str | None = None
    priority: str = "medium"
    trigger_rule: dict | None = None
    target_entities: list[str] | None = None
    region: str | None = None
    country_code: str | None = None


class AlertStatusUpdate(BaseModel):
    status: str


@router.post("/proactive/alerts")
def post_proactive_alert(req: ProactiveAlertRequest):
    """Create a proactive intelligence alert."""
    conn = get_db()
    aid = create_proactive_alert(
        conn, req.alert_type, req.title, req.summary, req.priority,
        req.trigger_rule, req.target_entities, req.region, req.country_code,
    )
    return {"alert_id": aid}


@router.get("/proactive/alerts")
def get_proactive_alerts(
    status: str | None = None,
    priority: str | None = None,
    alert_type: str | None = None,
    hours: int = Query(default=24, le=720),
    limit: int = Query(default=50, le=200),
):
    """List proactive alerts."""
    conn = get_db()
    items = list_alerts(conn, status, priority, alert_type, hours, limit)
    return {"total": len(items), "alerts": items}


@router.post("/proactive/scan")
def post_proactive_scan(hours: int = Query(default=6, le=72)):
    """Scan for conditions that should trigger proactive alerts."""
    conn = get_db()
    results = scan_for_alerts(conn, hours)
    return {"total_generated": len(results), "alerts": results}


@router.get("/proactive/alerts/{alert_id}")
def get_proactive_alert(alert_id: str):
    """Get a single proactive alert."""
    conn = get_db()
    item = get_alert(conn, alert_id)
    if not item:
        raise HTTPException(status_code=404, detail="Alert not found")
    return item


@router.put("/proactive/alerts/{alert_id}")
def put_proactive_alert_status(alert_id: str, req: AlertStatusUpdate):
    """Update an alert's status (delivered, acknowledged, dismissed)."""
    conn = get_db()
    ok = update_alert_status(conn, alert_id, req.status)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid status or alert not found")
    return {"updated": True}


# ─── System Self-Awareness ──────────────────────────────────

class ComponentRegisterRequest(BaseModel):
    component_name: str
    component_type: str | None = None
    config: dict | None = None


class HeartbeatRequest(BaseModel):
    component_name: str
    status: str = "healthy"
    metrics: dict | None = None


class ErrorReportRequest(BaseModel):
    component_name: str
    error_message: str


@router.post("/system/components")
def post_system_component(req: ComponentRegisterRequest):
    """Register a system component."""
    conn = get_db()
    cid = register_component(conn, req.component_name, req.component_type, req.config)
    return {"component_id": cid}


@router.get("/system/components")
def get_system_components(status: str | None = None):
    """List all system components."""
    conn = get_db()
    items = list_components(conn, status)
    return {"total": len(items), "components": items}


@router.get("/system/components/{component_name}")
def get_system_component(component_name: str):
    """Get a specific component's status."""
    conn = get_db()
    item = get_component(conn, component_name)
    if not item:
        raise HTTPException(status_code=404, detail="Component not found")
    return item


@router.post("/system/heartbeat")
def post_heartbeat(req: HeartbeatRequest):
    """Record a heartbeat from a system component."""
    conn = get_db()
    ok = heartbeat(conn, req.component_name, req.status, req.metrics)
    if not ok:
        raise HTTPException(status_code=404, detail="Component not registered")
    return {"recorded": True}


@router.post("/system/error")
def post_error_report(req: ErrorReportRequest):
    """Report an error for a component."""
    conn = get_db()
    ok = report_error(conn, req.component_name, req.error_message)
    return {"recorded": ok}


@router.get("/system/database")
def get_db_metrics():
    """Get comprehensive database metrics."""
    conn = get_db()
    return get_database_metrics(conn)


@router.get("/system/diagnostic")
def get_diagnostic():
    """Generate a full system diagnostic report."""
    conn = get_db()
    return generate_diagnostic_report(conn)


# ─── Historical Replay / Time Machine ───────────────────────

class SnapshotRequest(BaseModel):
    snapshot_time: str | None = None
    snapshot_type: str = "manual"
    label: str | None = None


@router.post("/replay/snapshots")
def post_snapshot(req: SnapshotRequest):
    """Create a snapshot of the current system state."""
    conn = get_db()
    return create_snapshot(conn, req.snapshot_time, req.snapshot_type, req.label)


@router.get("/replay/snapshots")
def get_snapshots(
    start_date: str | None = None,
    end_date: str | None = None,
    snapshot_type: str | None = None,
    limit: int = Query(default=50, le=200),
):
    """List snapshots."""
    conn = get_db()
    items = list_snapshots(conn, start_date, end_date, snapshot_type, limit)
    return {"total": len(items), "snapshots": items}


@router.get("/replay/snapshots/{snapshot_id}")
def get_single_snapshot(snapshot_id: str):
    """Get a specific snapshot."""
    conn = get_db()
    item = get_snapshot(conn, snapshot_id)
    if not item:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return item


@router.get("/replay/events")
def get_replay_events(
    at_time: str = Query(..., description="ISO timestamp to replay at"),
    category: str | None = None,
    region: str | None = None,
    country_code: str | None = None,
    limit: int = Query(default=100, le=1000),
):
    """Replay events as they existed at a specific point in time."""
    conn = get_db()
    return replay_events(conn, at_time, category, region, country_code, limit)


@router.get("/replay/timeline")
def get_replay_timeline(
    days: int = Query(default=30, le=365),
    interval_hours: int = Query(default=24, le=168),
):
    """Get a timeline of cumulative event counts for time-series visualization."""
    conn = get_db()
    timeline = get_timeline(conn, days, interval_hours)
    return {"days": days, "interval_hours": interval_hours, "points": timeline}


# ─── Commodity Dependency Mapping ───────────────────────────

class CommodityDependencyRequest(BaseModel):
    country_code: str
    commodity_name: str
    dependency_type: str = "import"
    share_pct: float | None = None
    volume_usd: float | None = None
    top_partners: list[str] | None = None
    risk_level: str = "normal"
    risk_factors: list[str] | None = None
    commodity_code: str | None = None


@router.post("/commodities/seed")
def seed_commodity_data():
    """Seed critical commodity dependency data."""
    conn = get_db()
    count = seed_dependencies(conn)
    return {"seeded": count}


@router.post("/commodities")
def post_commodity_dependency(req: CommodityDependencyRequest):
    """Add a commodity dependency record."""
    conn = get_db()
    did = add_dependency(
        conn, req.country_code, req.commodity_name, req.dependency_type,
        req.share_pct, req.volume_usd, req.top_partners,
        req.risk_level, req.risk_factors, req.commodity_code,
    )
    return {"dependency_id": did}


@router.get("/commodities")
def get_commodities(
    country_code: str | None = None,
    commodity_name: str | None = None,
    dependency_type: str | None = None,
    risk_level: str | None = None,
    limit: int = Query(default=100, le=500),
):
    """List commodity dependencies."""
    conn = get_db()
    items = list_dependencies(conn, country_code, commodity_name, dependency_type, risk_level, limit)
    return {"total": len(items), "dependencies": items}


@router.get("/commodities/risk/{country_code}")
def get_commodity_risk(country_code: str):
    """Assess commodity supply chain risk for a country."""
    conn = get_db()
    return assess_commodity_risk(conn, country_code)


@router.get("/commodities/disruption/{commodity_name}")
def get_disruption_impact(commodity_name: str):
    """Assess which countries would be impacted by a commodity disruption."""
    conn = get_db()
    return find_disruption_impact(conn, commodity_name)


@router.get("/commodities/{dep_id}")
def get_single_commodity(dep_id: str):
    """Get a single commodity dependency record."""
    conn = get_db()
    item = get_dependency(conn, dep_id)
    if not item:
        raise HTTPException(status_code=404, detail="Dependency not found")
    return item


# ─── Capital Flight Detection ───────────────────────────────

class CapitalFlightSignalRequest(BaseModel):
    country_code: str
    signal_type: str
    indicator_value: float
    baseline_value: float
    description: str | None = None
    evidence: list[str] | None = None


class SignalStatusUpdate(BaseModel):
    status: str


@router.post("/capital-flight/signals")
def post_capital_flight_signal(req: CapitalFlightSignalRequest):
    """Record a capital flight signal."""
    conn = get_db()
    return record_signal(
        conn, req.country_code, req.signal_type,
        req.indicator_value, req.baseline_value,
        req.description, req.evidence,
    )


@router.get("/capital-flight/signals")
def get_capital_flight_signals(
    country_code: str | None = None,
    signal_type: str | None = None,
    status: str | None = None,
    min_severity: float = 0,
    days: int = Query(default=30, le=365),
    limit: int = Query(default=50, le=200),
):
    """List capital flight signals."""
    conn = get_db()
    items = list_signals(conn, country_code, signal_type, status, min_severity, days, limit)
    return {"total": len(items), "signals": items}


@router.get("/capital-flight/risk/{country_code}")
def get_capital_flight_risk(country_code: str, days: int = Query(default=90, le=365)):
    """Assess capital flight risk for a country."""
    conn = get_db()
    return assess_country_flight_risk(conn, country_code, days)


@router.post("/capital-flight/scan")
def post_capital_flight_scan(days: int = Query(default=7, le=30)):
    """Scan recent economic events for capital flight patterns."""
    conn = get_db()
    results = scan_economic_events(conn, days)
    return {"total_detected": len(results), "signals": results}


@router.get("/capital-flight/signals/{signal_id}")
def get_single_signal(signal_id: str):
    """Get a single capital flight signal."""
    conn = get_db()
    item = get_signal(conn, signal_id)
    if not item:
        raise HTTPException(status_code=404, detail="Signal not found")
    return item


@router.put("/capital-flight/signals/{signal_id}")
def put_signal_status(signal_id: str, req: SignalStatusUpdate):
    """Update a signal's status."""
    conn = get_db()
    ok = update_signal_status(conn, signal_id, req.status)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid status or signal not found")
    return {"updated": True}

"""
System self-awareness — comprehensive introspection of Cerebro's
operational state beyond basic health checks.

Provides:
- Component health registry (ingestion pipelines, APIs, DB, etc.)
- Database metrics (table sizes, growth rates, disk usage)
- Pipeline status (last successful run, error rates)
- System vitals (event throughput, latency, queue depth)
- Diagnostic report generation
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

VALID_STATUSES = {"healthy", "degraded", "down", "unknown"}
VALID_COMPONENT_TYPES = {"ingestion", "processing", "intelligence", "api", "database"}


def register_component(
    conn,
    component_name: str,
    component_type: str | None = None,
    config: dict | None = None,
) -> str:
    """Register or update a system component."""
    existing = conn.execute(
        "SELECT id FROM system_components WHERE component_name = ?",
        (component_name,),
    ).fetchone()

    if existing:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE system_components SET component_type = ?, config = ?, updated_at = ? WHERE id = ?",
            (component_type, json.dumps(config) if config else None, now, existing["id"]),
        )
        conn.commit()
        return existing["id"]

    cid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO system_components
           (id, component_name, component_type, config)
           VALUES (?, ?, ?, ?)""",
        (cid, component_name, component_type, json.dumps(config) if config else None),
    )
    conn.commit()
    return cid


def heartbeat(conn, component_name: str, status: str = "healthy", metrics: dict | None = None) -> bool:
    """Record a heartbeat from a system component."""
    if status not in VALID_STATUSES:
        status = "unknown"

    now = datetime.now(timezone.utc).isoformat()
    result = conn.execute(
        """UPDATE system_components
           SET status = ?, last_heartbeat = ?, metrics = ?, updated_at = ?
           WHERE component_name = ?""",
        (status, now, json.dumps(metrics) if metrics else None, now, component_name),
    )
    conn.commit()
    return result.rowcount > 0


def report_error(conn, component_name: str, error_message: str) -> bool:
    """Report an error for a component."""
    now = datetime.now(timezone.utc).isoformat()
    result = conn.execute(
        """UPDATE system_components
           SET status = 'degraded', last_error = ?, updated_at = ?
           WHERE component_name = ?""",
        (error_message, now, component_name),
    )
    conn.commit()
    return result.rowcount > 0


def get_component(conn, component_name: str) -> dict | None:
    """Get a specific component's status."""
    row = conn.execute(
        "SELECT * FROM system_components WHERE component_name = ?",
        (component_name,),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["metrics"] = json.loads(d["metrics"]) if d["metrics"] else None
    d["config"] = json.loads(d["config"]) if d["config"] else None
    return d


def list_components(conn, status: str | None = None) -> list[dict]:
    """List all registered system components."""
    if status and status in VALID_STATUSES:
        rows = conn.execute(
            "SELECT * FROM system_components WHERE status = ? ORDER BY component_name",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM system_components ORDER BY component_name"
        ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["metrics"] = json.loads(d["metrics"]) if d["metrics"] else None
        d["config"] = json.loads(d["config"]) if d["config"] else None
        results.append(d)
    return results


def get_database_metrics(conn) -> dict:
    """Get comprehensive database metrics — table sizes, disk usage, etc."""
    tables = [
        "events", "entities", "entity_relations", "alerts", "vessels",
        "vessel_tracks", "flights", "briefs", "predictions", "fusion_signals",
        "risk_scores", "system_log", "source_ratings", "threat_assessments",
        "maritime_zones", "data_lineage", "proactive_alerts",
    ]

    table_counts = {}
    total_rows = 0
    for t in tables:
        try:
            cnt = conn.execute(f"SELECT COUNT(*) as c FROM {t}").fetchone()["c"]
            table_counts[t] = cnt
            total_rows += cnt
        except Exception:
            table_counts[t] = -1  # table doesn't exist yet

    # DB file size
    db_path = os.environ.get("CEREBRO_DB_PATH", "cerebro.db")
    db_size_bytes = 0
    try:
        db_size_bytes = os.path.getsize(db_path)
    except OSError:
        pass

    # Recent activity rate
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    recent_events = conn.execute(
        "SELECT COUNT(*) as c FROM events WHERE timestamp >= ?", (one_hour_ago,)
    ).fetchone()["c"]

    return {
        "total_rows": total_rows,
        "db_size_bytes": db_size_bytes,
        "db_size_mb": round(db_size_bytes / (1024 * 1024), 2),
        "table_counts": table_counts,
        "events_last_hour": recent_events,
    }


def generate_diagnostic_report(conn) -> dict:
    """Generate a comprehensive system diagnostic report."""
    components = list_components(conn)
    db_metrics = get_database_metrics(conn)

    # Component health summary
    health_summary = {"healthy": 0, "degraded": 0, "down": 0, "unknown": 0}
    for c in components:
        health_summary[c["status"]] = health_summary.get(c["status"], 0) + 1

    # Check for stale heartbeats (no heartbeat in 5 minutes)
    stale_threshold = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    stale_components = [
        c["component_name"] for c in components
        if c["last_heartbeat"] and c["last_heartbeat"] < stale_threshold
    ]

    # Recent errors from system_log
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    error_count = conn.execute(
        "SELECT COUNT(*) as c FROM system_log WHERE level = 'error' AND timestamp >= ?",
        (one_hour_ago,),
    ).fetchone()["c"]

    overall_status = "healthy"
    if health_summary.get("down", 0) > 0 or error_count > 10:
        overall_status = "degraded"
    if health_summary.get("down", 0) > 2:
        overall_status = "critical"

    return {
        "overall_status": overall_status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "component_health": health_summary,
        "total_components": len(components),
        "stale_components": stale_components,
        "recent_errors": error_count,
        "database": db_metrics,
        "components": components,
    }
